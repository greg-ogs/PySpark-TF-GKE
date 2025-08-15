from pyspark.sql import SparkSession
import logging
import os
import socket


class RetrieveDataFromMySQLOutside:
    def __init__(self):
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

        # Default DB connection parameters when running driver OUTSIDE the cluster
        # Expect MySQL to be port-forwarded to localhost:3306 on the HOST, and
        # the container to reach it via host.docker.internal
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
        Creates and returns a SparkSession configured for running driver outside K8s.
        """
        self.logger.info("Creating Spark session for external (outside K8s) driver...")
        try:
            # Master exposed via kubectl port-forward from the HOST
            master_url = os.environ.get("SPARK_MASTER", "spark://host.docker.internal:7077")

            # For executors to call back to the driver, we expose ports 7078/7079 on the HOST
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
                .load()

            self.logger.info("Data loaded successfully.")

            # Display schema and some data for verification
            df.printSchema()
            df.show(50)

            return df

        except Exception as e:
            self.logger.error(f"Error reading data from MySQL: {e}")
            raise

    @classmethod
    def main(cls):
        instance = cls()
        spark = None
        try:
            spark = instance.create_spark_session()
            instance.read_data_from_mysql(spark)
        except Exception as e:
            instance.logger.error(f"An error occurred: {e}")
        finally:
            if spark:
                spark.stop()
                instance.logger.info("Spark session stopped.")


if __name__ == "__main__":
    RetrieveDataFromMySQLOutside.main()
