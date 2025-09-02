import os

class RetrieveDataFromMySQLOutside:
    def __init__(self, logger, DB, spark):
        self.DB_CONFIG = DB
        self.spark = spark
        self.logger = logger

    def read_data_from_mysql(self):
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

            df = self.spark.read \
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
