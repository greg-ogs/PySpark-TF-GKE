from pyspark.sql import SparkSession
import logging
import os
import socket
# for k_means
from pyspark.ml.feature import VectorAssembler, StringIndexer, OneHotEncoder
from pyspark.ml.clustering import KMeans
from pyspark.ml.evaluation import ClusteringEvaluator
from pyspark.ml import Pipeline
from pyspark.sql.functions import isnan, when
from pyspark.sql.functions import col

class RetrieveDataFromMySQLOutside:
    def __init__(self):
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

        # Default DB connection parameters when running driver OUTSIDE the cluster
        # Expect service endpoint to route traffic to the MySQL container, and allow
        # the container to reach it via host.docker.internal in the same network.
        self.DB_CONFIG = {
            'host': 'host.docker.internal',
            'port': '3306',
            'user': 'root',
            'password': '',
            'database': 'health_data',
            'table': 'health_disparities'
        }

    def create_spark_session(self):
        """
        Creates and returns a SparkSession configured for running a driver outside K8s.
        """
        self.logger.info("Creating Spark session for external (outside K8s) driver...")
        try:
            # Master endpoint exposed by K8s service.
            master_url = os.environ.get("SPARK_MASTER", "spark://host.docker.internal:7077")

            # For executors to call back to the driver, we expose ports 7078/7079
            # and advertise a reachable address. By default, use host.docker.internal.
            driver_host = os.environ.get("SPARK_DRIVER_HOST", "host.docker.internal")
            driver_port = os.environ.get("SPARK_DRIVER_PORT", "7078")
            blockmanager_port = os.environ.get("SPARK_BLOCKMGR_PORT", "7079")

            # Log DNS resolutions
            try:
                mysql_ip = socket.gethostbyname(self.DB_CONFIG['host'])
                self.logger.info(f"Resolved {self.DB_CONFIG['host']} to {mysql_ip}")
            except Exception as e:
                self.logger.warning(f"Could not resolve {self.DB_CONFIG['host']}: {e}")
            try:
                resolved_driver = socket.gethostbyname(driver_host) if driver_host else None
                if resolved_driver:
                    self.logger.info(f"Resolved driver host {driver_host} to {resolved_driver}")
            except Exception as e:
                self.logger.warning(f"Could not resolve driver host {driver_host}: {e}")

            self.logger.info(
                f"Using master={master_url}, driver_host={driver_host}, "
                f"driver_port={driver_port}, blockManagerPort={blockmanager_port}"
            )

            # For parallelism can also use:
            #     # For default number of partitions for RDD operations and as a fallback when Spark cannot infer a better
            #     parallelism.
            #     .config("spark.default.parallelism", "16") \
            #     # To control the number of reduce/shuffle partitions for DataFrame/SQL/ML stages.
            #     .config("spark.sql.shuffle.partitions", "16") \

            spark = SparkSession.builder \
                .appName("ReadMySQLDataOutsideK8s") \
                .master(master_url) \
                .config("spark.driver.host", driver_host) \
                .config("spark.driver.bindAddress", "0.0.0.0") \
                .config("spark.driver.port", driver_port) \
                .config("spark.blockManager.port", blockmanager_port) \
                .getOrCreate()
            self.logger.info("Spark session created successfully.")
            return spark
        except Exception as e:
            self.logger.error(f"Error creating Spark session: {e}")
            raise

    def read_data_from_mysql(self, spark):
        """
        Reads data from the specified MySQL table into a Spark DataFrame.
        """
        # Allow env overrides for DB config
        host = os.environ.get('DB_HOST', self.DB_CONFIG['host'])
        port = os.environ.get('DB_PORT', self.DB_CONFIG['port'])
        user = os.environ.get('DB_USER', self.DB_CONFIG['user'])
        password = os.environ.get('DB_PASSWORD', self.DB_CONFIG['password'])
        database = os.environ.get('DB_NAME', self.DB_CONFIG['database'])
        table = os.environ.get('DB_TABLE', self.DB_CONFIG['table'])

        self.logger.info(
            f"Connecting to MySQL database '{database}' on '{host}:{port}'...")
        try:
            jdbc_url = f"jdbc:mysql://{host}:{port}/{database}"

            df = spark.read \
                .format("jdbc") \
                .option("url", jdbc_url) \
                .option("dbtable", table) \
                .option("user", user) \
                .option("password", password) \
                .option("driver", "com.mysql.cj.jdbc.Driver") \
                .option("partitionColumn", "id") \
                .option("lowerBound", "1") \
                .option("upperBound", "1000000") \
                .option("numPartitions", "16") \
                    .load()

            self.logger.info("Data loaded successfully.")

            # Display schema and some data for verification
            df.printSchema()
            df.show(50)

            return df

        except Exception as e:
            self.logger.error(f"Error reading data from MySQL: {e}")
            raise

    @staticmethod
    def k_means(input_df):
        # If partitioned, read doesn't work use:
        # df = df.repartition(16)

        print("Checking for missing values in 'measure_name'...")
        null_measure_name_count = input_df.filter(col("measure_name").isNull()).count()
        print(f"Column 'measure_name' has {null_measure_name_count} missing values")

        # Filter out rows where 'measure_name' is null, as it's our clustering target
        input_df = input_df.filter(col("measure_name").isNotNull())
        print(f"Rows after filtering out missing 'measure_name' values: {input_df.count()}")

        # Use StringIndexer and OneHotEncoder to convert it in numerical features for "measure_name".
        stages = []

        # StringIndexer: Converts 'measure_name' to numerical indices
        indexer = StringIndexer(inputCol="measure_name", outputCol="measure_name_index", handleInvalid="keep")
        stages.append(indexer)

        # OneHotEncoder: Converts numerical indices to one-hot encoded vectors
        encoder = OneHotEncoder(inputCol="measure_name_index", outputCol="measure_name_vec")
        stages.append(encoder)

        # Add other relevant numeric columns to the feature list
        numeric_cols = ["value", "lower_ci", "upper_ci"]

        # Handle missing values in numeric columns by filling with mean
        for col_name in numeric_cols:
            if col_name in input_df.columns:
                mean_val = input_df.select(col_name).filter(~isnan(col(col_name)) & col(col_name).isNotNull()).agg(
                    {col_name: "avg"}).collect()[0][0]
                input_df = input_df.withColumn(col_name,
                                               when(col(col_name).isNull() | isnan(col(col_name)), mean_val).otherwise(
                                                   col(col_name)))

        feature_cols = ["measure_name_vec"] + numeric_cols

        # VectorAssembler: Combines all feature columns into a single vector column
        assembler = VectorAssembler(inputCols=feature_cols, outputCol="features", handleInvalid="keep")
        stages.append(assembler)

        # Create and apply the pipeline
        pipeline = Pipeline(stages=stages)
        print("Applying feature engineering pipeline...")
        pipeline_model = pipeline.fit(input_df)
        transformed_df = pipeline_model.transform(input_df)

        # Select only the feature column for clustering
        dataset = transformed_df.select("features")

        # K-Means Model Training
        # ===============================

        # Define the K-Means model
        # You might need to experiment with the 'k' parameter (number of clusters)
        kmeans = KMeans().setK(5).setSeed(1)

        # Train the K-Means model
        print("Training K-Means model...")
        model = kmeans.fit(dataset)

        # Save Model
        # =============================
        # You can save the trained K-Means model and pipeline if needed for future use.
        # To avoid failures when executors cannot write to the local filesystem path, saving is
        # disabled by default.
        # Enable by setting environment variable SAVE_MODELS=true and, optionally,
        # set MODEL_OUTPUT_DIR to a directory that exists and is writable on all executors (e.g.,
        # /opt/spark/work/models in the provided Docker spark:bastion_workloads image).
        save_models = os.environ.get("SAVE_MODELS", "true").lower() in ("1", "true", "yes", "y")
        if save_models:
            base_dir = os.environ.get("MODEL_OUTPUT_DIR", "/opt/spark/work-dir/models")
            model_path = os.path.join(base_dir, "health_kmeans_model")
            pipeline_path = os.path.join(base_dir, "health_kmeans_pipeline")
            print(f"Saving K-Means model to {model_path}")
            model.save(model_path)
            print(f"Saving K-Means pipeline to {pipeline_path}")
            pipeline_model.save(pipeline_path)
        else:
            print("Skipping model save (set SAVE_MODELS=true to enable).")

    @classmethod
    def main(cls):
        instance = cls()
        spark = None
        try:
            spark = instance.create_spark_session()
            retrieve_dataframe = instance.read_data_from_mysql(spark)
            instance.k_means(retrieve_dataframe)
        except Exception as e:
            instance.logger.error(f"An error occurred: {e}")
        finally:
            if spark:
                spark.stop()
                instance.logger.info("================================================================================")
                instance.logger.info("================================================================================")
                instance.logger.info("================================================================================")
                instance.logger.info("Spark session stopped.")
                instance.logger.info("================================================================================")
                instance.logger.info("================================================================================")
                instance.logger.info("================================================================================")


if __name__ == "__main__":
    RetrieveDataFromMySQLOutside.main()
