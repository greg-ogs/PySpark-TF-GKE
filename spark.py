from pyspark.sql import SparkSession
import time

# Create a SparkSession
spark = SparkSession.builder.appName("MyPySparkApp").getOrCreate()

# Create a dummy RDD with a large number of partitions
# to encourage distribution across worker nodes.
data = range(1, 10000000) # 10 million numbers
rdd = spark.sparkContext.parallelize(data, 100) # 100 partitions

# A simple transformation and action
def process_partition(iterator):
    # Simulate some work
    time.sleep(2) # Sleep for 2 seconds to simulate work
    count = 0
    for _ in iterator:
        count += 1
    yield count

partition_counts = rdd.mapPartitions(process_partition).collect()

print(f"Counts per partition: {partition_counts}")
print(f"Total processed items: {sum(partition_counts)}")

# Stop the SparkSession
spark.stop()
