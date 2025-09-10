from pyspark.sql import SparkSession
import logging
import os
import socket

class CreateSparkSession:
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

        self.DB_CONFIG = {
            'host': 'host.docker.internal',
            'port': '3306',
            'user': 'root',
            'password': '',
            'database': 'health_data',
            'table': 'health_disparities'
        }

    def new_spark_session(self):
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
            return spark, self.logger, self.DB_CONFIG
        except Exception as e:
            self.logger.error(f"Error creating Spark session: {e}")
            raise