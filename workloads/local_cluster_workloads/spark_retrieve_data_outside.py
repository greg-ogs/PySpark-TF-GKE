from pyspark.sql import SparkSession
import logging
import os
import socket
# for k_means
from pyspark.ml.feature import VectorAssembler, StringIndexer, OneHotEncoder
from pyspark.ml.clustering import KMeans, KMeansModel
from pyspark.ml import Pipeline, PipelineModel
from pyspark.sql.functions import isnan, when
from pyspark.sql.functions import col

class RetrieveDataFromMySQLOutside:
    def __init__(self):
        # Configure logging
        logging.basicConfig(
            level=logging.ERROR ,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        logging.getLogger("urllib3").setLevel(logging.ERROR)
        logging.getLogger("botocore").setLevel(logging.ERROR)
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)

        self.logger.propagate = False

        if not self.logger.handlers:
            self.logger.addHandler(handler)

        # Initialize in-memory models (set during k_means)
        self.pipeline_model = None
        self.kmeans_model = None

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
            spark.sparkContext.setLogLevel("ERROR")
            self.logger.info("Set Spark log level to ERROR to suppress Spark INFO/WARN logs.")
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
            df.show(5)

            return df

        except Exception as e:
            self.logger.error(f"Error reading data from MySQL: {e}")
            raise

    def k_means(self, input_df):
        # If partitioned, read doesn't work use:
        # df = df.repartition(16)

        self.logger.info("Checking for missing values in 'measure_name'...")
        null_measure_name_count = input_df.filter(col("measure_name").isNull()).count()
        self.logger.info(f"Column 'measure_name' has {null_measure_name_count} missing values")

        # Filter out rows where 'measure_name' is null, as it's our clustering target
        input_df = input_df.filter(col("measure_name").isNotNull())
        self.logger.info(f"Rows after filtering out missing 'measure_name' values: {input_df.count()}")

        # Use StringIndexer and OneHotEncoder to convert it in numerical features for "measure_name".
        stages = []

        # StringIndexer: Converts 'measure_name' string values to numerical indices
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

        # Increase the weight of 'measure_name' by repeating its one-hot vector in the features.
        # Repeating a vector m times increases its contribution to squared distance by ~m in Euclidean space.
        # Configure repeats via env var MEASURE_NAME_WEIGHT (default: 5). Values <1 are clamped to 1.
        try:
            repeats = int(os.environ.get("MEASURE_NAME_WEIGHT", "5"))
        except Exception:
            repeats = 5
        if repeats < 1:
            repeats = 1
        self.logger.info(f"Applying measure_name weight by repeating measure_name_vec {repeats} time(s)")

        feature_cols = (["measure_name_vec"] * repeats) + numeric_cols

        # VectorAssembler: Combines all feature columns into a single vector column
        assembler = VectorAssembler(inputCols=feature_cols, outputCol="features", handleInvalid="keep")
        stages.append(assembler)

        # Create and apply the pipeline
        pipeline = Pipeline(stages=stages)
        self.logger.info("Applying feature engineering pipeline...")
        pipeline_model = pipeline.fit(input_df)
        transformed_df = pipeline_model.transform(input_df)

        # Select only the feature column for clustering
        dataset = transformed_df.select("features")

        # K-Means Model Training
        # ===============================

        # Define the K-Means model
        kmeans = KMeans().setK(25).setSeed(1).setMaxIter(1000)

        # Train the K-Means model
        self.logger.info("Training K-Means model...")
        model = kmeans.fit(dataset)

        # Store models in memory for later inference
        self.pipeline_model = pipeline_model
        self.kmeans_model = model

        # Save Model (disabled - using in-memory models instead)
        # =============================
        # The model and pipeline are kept in memory on self.kmeans_model and self.pipeline_model.
        # If persistence is desired in the future, re-enable the block below.
        # Kubernetes save requires updates with a persistent volume in the cluster reachable from the bastion driver or
        # updates to use a bucket and upload the model.
        # save_models = os.environ.get("SAVE_MODELS", "true").lower() in ("1", "true", "yes", "y")
        # if save_models:
        #     base_dir = os.environ.get("MODEL_OUTPUT_DIR", "/opt/spark/work-dir/models")
        #     model_path = os.path.join(base_dir, "health_kmeans_model")
        #     pipeline_path = os.path.join(base_dir, "health_kmeans_pipeline")
        #     self.logger.info(f"Saving K-Means model to {model_path}")
        #     model.save(model_path)
        #     self.logger.info(f"Saving K-Means pipeline to {pipeline_path}")
        #     pipeline_model.save(pipeline_path)
        # else:
        #     self.logger.info("Skipping model save (set SAVE_MODELS=true to enable).")

    def _get_model_paths(self):
        base_dir = os.environ.get("MODEL_OUTPUT_DIR", "/opt/spark/work-dir/models")
        p_model_path = os.path.join(base_dir, "health_kmeans_model")
        p_pipeline_path = os.path.join(base_dir, "health_kmeans_pipeline")
        return p_model_path, p_pipeline_path

    def load_models(self):
        pr_model_path, pr_pipeline_path = self._get_model_paths()
        self.logger.info(f"Loading K-Means model from {pr_model_path}")
        self.logger.info(f"Loading Pipeline model from {pr_pipeline_path}")
        try:
            pr_pipeline_model = PipelineModel.load(pr_pipeline_path)
            self.logger.info(pr_pipeline_model)
        except Exception as e:
            self.logger.error(f"Error loading Pipeline model: {e}")
            raise
        try:
            pr_kmeans_model = KMeansModel.load(pr_model_path)
            self.logger.info(pr_kmeans_model)
        except Exception as e:
            self.logger.error(f"Error loading KMeans model: {e}")
            raise
        return pr_pipeline_model, pr_kmeans_model

    def infer_single_row(self, spark: SparkSession, entry_str: str = "Able-Bodied", entry_num: int = 0):
        # Hardcoded single row input matching training feature schema
        # Chooses a plausible measure_name that likely exists in the dataset
        data = [(entry_str, entry_num, entry_num + 7, entry_num + 5 )]
        columns = ["measure_name", "value", "lower_ci", "upper_ci"]
        input_df = spark.createDataFrame(data, columns)

        # Use in-memory models produced by k_means instead of loading from the disk
        if not self.pipeline_model or not self.kmeans_model:
            raise RuntimeError("In-memory models not available. Ensure k_means() has been executed before inference.")

        # Apply the same feature engineering pipeline and then the KMeans model
        features_df = self.pipeline_model.transform(input_df)
        predictions_df = self.kmeans_model.transform(features_df)

        prediction_row = predictions_df.select("prediction").first()
        self.logger.info(f"Full prediction row data: {prediction_row}")
        prediction = int(prediction_row["prediction"]) if prediction_row is not None else None
        self.logger.info(f"Single-row inference prediction: {prediction}")

        # predictions_df.select("measure_name", "value", "lower_ci", "upper_ci", "prediction").show(truncate=False)
        return prediction, predictions_df

    @classmethod
    def main(cls):
        instance = cls()
        spark = None
        try:
            spark = instance.create_spark_session()
            retrieve_dataframe = instance.read_data_from_mysql(spark)
            instance.k_means(retrieve_dataframe)

            # Optionally run single-row inference using the saved model/pipeline
            run_inference = os.environ.get("RUN_INFERENCE", "true").lower() in ("1", "true", "yes", "y")
            if run_inference:
                try:
                    data_strings = ["Able-Bodied", "Asthma", "Avoided Care Due to Cost", "Cancer", "Cardiovascular Diseases", "Child Poverty", "Premature Death"]
                    data_ints = [0, 10, 20, 30, 40, 50, 60]
                    for label, num in zip(data_strings, data_ints):
                        prediction, _ = (instance.infer_single_row(spark, entry_str=label, entry_num=num))
                    # instance.logger.info(f"KMeans single-row inference completed. Prediction: {prediction}")
                except Exception as ie:
                    instance.logger.warning(f"Single-row inference skipped due to error: {ie}")
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
