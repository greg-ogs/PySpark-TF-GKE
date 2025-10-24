"""
Created by greg-ogs
This script sets up a basic Spark session for local development and testing.
It can be used as a template for creating Spark applications.
"""

import pandas as pd
import numpy as np
from pyspark.sql import SparkSession
import os

try:
    # Create a SparkSession for local development
    spark = SparkSession.builder\
        .appName("Spark Workloads")\
        .config("spark.sql.shuffle.partitions", "2")\
        .config("spark.default.parallelism", "2")\
        .config("spark.sql.streaming.forceDeleteTempCheckpointDir", "True")\
        .master("local[2]")\
        .getOrCreate()
    
    # Print Spark version and application ID for verification
    print(f"Spark version: {spark.version}")
    print(f"Application ID: {spark.sparkContext.applicationId}")
    
    # Example: Create a simple DataFrame
    data = [("Alice", 34), ("Bob", 45), ("Charlie", 29)]
    columns = ["Name", "Age"]
    df = spark.createDataFrame(data, columns)
    
    # Show the DataFrame
    print("Sample DataFrame:")
    df.show()
    
    # Example: Perform a simple transformation
    print("DataFrame with age > 30:")
    df.filter(df.Age > 30).show()
    
except Exception as e:
    print(f"An error occurred: {str(e)}")

finally:
    # Clean up resources
    if 'spark' in locals():
        print("Stopping Spark session...")
        spark.stop()