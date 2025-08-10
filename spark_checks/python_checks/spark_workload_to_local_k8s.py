from pyspark.sql import SparkSession
from pyspark.sql.functions import col
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MySQL connection parameters
DB_CONFIG = {
    'host': 'localhost',
    'port': '3306',
    'user': 'root',
    'password': '',
    'database': 'health_data',
    'table': 'health_disparities'
}


def create_spark_session():
    """
    Creates and returns a SparkSession with the necessary MySQL connector.
    """
    logger.info("Creating Spark session...")
    try:
        spark = SparkSession.builder \
            .appName("ReadMySQLData") \
            .config("spark.jars", "/opt/spark/jars/mysql-connector-j-8.4.0.jar") \
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
    logger.info(
        f"Connecting to MySQL database '{DB_CONFIG['database']}' on '{DB_CONFIG['host']}:{DB_CONFIG['port']}'...")
    try:
        jdbc_url = f"jdbc:mysql://{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"

        df = spark.read \
            .format("jdbc") \
            .option("url", jdbc_url) \
            .option("dbtable", DB_CONFIG['table']) \
            .option("user", DB_CONFIG['user']) \
            .option("password", DB_CONFIG['password']) \
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
            logger.info("Spark session stopped.")


if __name__ == "__main__":
    main()