from pyspark.sql import SparkSession
from pyspark.sql.functions import col
import logging
import os
import socket

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MySQL connection parameters based on load_csv.py
DB_CONFIG = {
    # Use the internal Kubernetes service name for MySQL
    'host': 'mysql-read',
    'port': '3306',
    'user': 'root',
    'password': '',
    'database': 'health_data',
    'table': 'health_disparities'
}


def create_spark_session():
    """
    Creates and returns a SparkSession configured for Kubernetes.
    """
    logger.info("Creating Spark session for Kubernetes cluster...")
    try:
        # Determine the driver host using a stable Service DNS; fallback only if necessary
        driver_host = os.environ.get("SPARK_DRIVER_HOST", "spark-workload")
        # driver_host_ip = (
        #     os.environ.get("POD_IP")
        #     or os.environ.get("MY_POD_IP")
        #     or os.environ.get("SPARK_DRIVER_HOST_IP")
        #     or os.environ.get("SPARK_LOCAL_IP")
        # )
        # if not driver_host and not driver_host_ip:
        #     try:
        #         driver_host_ip = socket.gethostbyname(socket.gethostname())
        #     except Exception:
        #         driver_host_ip = "127.0.0.1"
        # if not driver_host:
        #     driver_host = driver_host_ip

        driver_port = os.environ.get("SPARK_DRIVER_PORT", "7078")
        blockmanager_port = os.environ.get("SPARK_BLOCKMGR_PORT", "7079")

        # Log DNS resolutions
        try:
            mysql_ip = socket.gethostbyname(DB_CONFIG['host'])
            logger.info(f"Resolved {DB_CONFIG['host']} to {mysql_ip}")
        except Exception as e:
            logger.warning(f"Could not resolve {DB_CONFIG['host']}: {e}")
        try:
            resolved_driver = socket.gethostbyname(driver_host) if driver_host else None
            if resolved_driver:
                logger.info(f"Resolved driver host {driver_host} to {resolved_driver}")
        except Exception as e:
            logger.warning(f"Could not resolve driver host {driver_host}: {e}")

        logger.info(f"Using driver_host={driver_host}, driver_port={driver_port}, blockManagerPort={blockmanager_port}")

        spark = SparkSession.builder \
            .appName("ReadMySQLDataOnK8s") \
            .master("spark://spark-master:7077") \
            .config("spark.driver.host", driver_host) \
            .config("spark.driver.bindAddress", "0.0.0.0") \
            .config("spark.driver.port", driver_port) \
            .config("spark.blockManager.port", blockmanager_port) \
            .getOrCreate()
        logger.info("Spark session created successfully.")
        return spark
    except Exception as e:
        logger.error(f"Error creating Spark session: {e}")
        raise


def read_data_from_mysql(spark):
    """
    Reads data from the specified MySQL table into a Spark DataFrame.
    """
    # Allow env overrides for DB config
    host = os.environ.get('DB_HOST', DB_CONFIG['host'])
    port = os.environ.get('DB_PORT', DB_CONFIG['port'])
    user = os.environ.get('DB_USER', DB_CONFIG['user'])
    password = os.environ.get('DB_PASSWORD', DB_CONFIG['password'])
    database = os.environ.get('DB_NAME', DB_CONFIG['database'])
    table = os.environ.get('DB_TABLE', DB_CONFIG['table'])

    logger.info(
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

        logger.info("Data loaded successfully.")

        # Display schema and some data for verification
        df.printSchema()
        df.show(50)

        return df

    except Exception as e:
        logger.error(f"Error reading data from MySQL: {e}")
        raise


def main():
    """
    Main function to execute the data retrieval process.
    """
    spark = None
    try:
        spark = create_spark_session()
        read_data_from_mysql(spark)
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        if spark:
            spark.stop()
            logger.info("=============================================================================================")
            logger.info("=============================================================================================")
            logger.info("=============================================================================================")
            logger.info("Spark session stopped.")
            logger.info("=============================================================================================")
            logger.info("=============================================================================================")
            logger.info("=============================================================================================")

if __name__ == "__main__":
    main()
