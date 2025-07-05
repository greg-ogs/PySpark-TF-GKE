"""
K-Means Clustering Model for Health Data Analysis
This script builds a K-Means clustering model using the health.csv dataset and a Spark Kubernetes cluster.
It performs the following steps:
1. Loads and explores the health.csv dataset
2. Preprocesses the data, focusing on 'measure_name' for clustering
3. Creates and trains a K-Means clustering model
4. Evaluates the model
The script is designed to run on a Kubernetes cluster with Spark.
"""

from pyspark.sql import SparkSession
from pyspark.ml.feature import VectorAssembler, StringIndexer, OneHotEncoder
from pyspark.ml.clustering import KMeans
from pyspark.ml.evaluation import ClusteringEvaluator
from pyspark.ml import Pipeline
from pyspark.sql.functions import col, isnan, when, count
import os

# Create a SparkSession with Kubernetes configuration
# - spark:latest: Docker image for Spark
# - default: Kubernetes namespace (ensure this matches your cluster's namespace)
# - k8s://https://kubernetes.default.svc: Kubernetes master URL
# - master: Spark master service name (name: spark-master, port: 7077) for predeployed Spark manifests
spark = SparkSession.builder \
    .appName("HealthKMeansClassification") \
    .config("spark.kubernetes.container.image", "spark:latest") \
    .config("spark.kubernetes.namespace", "default") \
    .getOrCreate()
    # .config("spark.master", "spark://spark-master:7077") \


try:
    # Step 1: Data Loading and Exploration
    # ====================================

    # Load the health.csv dataset from GCS bucket with header and schema inference
    print("Loading health dataset from GCS bucket...")
    # Get project ID from environment variable
    project_id = os.getenv("GCP_PROJECT_ID")
    if not project_id:
        raise ValueError("GCP_PROJECT_ID environment variable is not set")

    # Use the GCS path format: gs://bucket-name/file-path
    bucket_name = f"{project_id}-datasets"
    gcs_path = f"gs://{bucket_name}/health.csv"

    health_df = spark.read.csv(gcs_path, header=True, inferSchema=True)

    # Print the schema to understand the data types of each column
    print("Dataset Schema:")
    health_df.printSchema()

    # Show a sample of the data to get a feel for the content
    print("Sample Data:")
    health_df.show(5)

    # Count the number of rows to understand the dataset size
    row_count = health_df.count()
    print(f"Total number of rows: {row_count}")

    # Step 2: Data Cleaning and Feature Engineering for K-Means
    # =======================================================

    # Check for missing values in 'measure_name'
    print("Checking for missing values in 'measure_name'...")
    null_measure_name_count = health_df.filter(col("measure_name").isNull()).count()
    print(f"Column 'measure_name' has {null_measure_name_count} missing values")

    # Filter out rows where 'measure_name' is null, as it's our clustering target
    health_df = health_df.filter(col("measure_name").isNotNull())
    print(f"Rows after filtering out missing 'measure_name' values: {health_df.count()}")

    # For K-Means, we need numerical features. 'measure_name' is categorical.
    # We will use StringIndexer and OneHotEncoder to convert it.
    stages = []

    # StringIndexer: Converts 'measure_name' to numerical indices
    indexer = StringIndexer(inputCol="measure_name", outputCol="measure_name_index", handleInvalid="keep")
    stages.append(indexer)

    # OneHotEncoder: Converts numerical indices to one-hot encoded vectors
    encoder = OneHotEncoder(inputCol="measure_name_index", outputCol="measure_name_vec")
    stages.append(encoder)

    # Add other relevant numeric columns to the feature list
    # You might need to select additional numeric columns from your dataset
    # For this example, let's assume 'value', 'lower_ci', 'upper_ci' are relevant numerical features
    numeric_cols = ["value", "lower_ci", "upper_ci"]

    # Handle missing values in numeric columns by filling with mean
    for col_name in numeric_cols:
        if col_name in health_df.columns:
            mean_val = health_df.select(col_name).filter(~isnan(col(col_name)) & col(col_name).isNotNull()).agg({col_name: "avg"}).collect()[0][0]
            health_df = health_df.withColumn(col_name, when(col(col_name).isNull() | isnan(col(col_name)), mean_val).otherwise(col(col_name)))

    feature_cols = ["measure_name_vec"] + numeric_cols

    # VectorAssembler: Combines all feature columns into a single vector column
    assembler = VectorAssembler(inputCols=feature_cols, outputCol="features", handleInvalid="keep")
    stages.append(assembler)

    # Create and apply the pipeline
    pipeline = Pipeline(stages=stages)
    print("Applying feature engineering pipeline...")
    pipeline_model = pipeline.fit(health_df)
    transformed_df = pipeline_model.transform(health_df)

    # Select only the features column for clustering
    dataset = transformed_df.select("features")

    # Step 3: K-Means Model Training
    # ===============================

    # Define the K-Means model
    # You might need to experiment with the 'k' parameter (number of clusters)
    kmeans = KMeans().setK(5).setSeed(1) # Example: 5 clusters, set a seed for reproducibility

    # Train the K-Means model
    print("Training K-Means model...")
    model = kmeans.fit(dataset)

    # Make predictions (assign clusters)
    predictions = model.transform(dataset)

    # Show a sample of the predictions
    print("Sample Predictions (Cluster Assignments):")
    predictions.select("features", "prediction").show(5)

    # Print the cluster centers
    print("Cluster Centers:")
    for center in model.clusterCenters():
        print(center)

    # Step 4: Model Evaluation
    # ========================

    # Evaluate clustering by computing Silhouette score
    # Silhouette score measures how similar an object is to its own cluster compared to other clusters.
    # A higher Silhouette score indicates better-defined clusters.
    evaluator = ClusteringEvaluator()

    silhouette = evaluator.evaluate(predictions)
    print(f"Silhouette with squared Euclidean distance = {silhouette}")

    # Step 5: Save Model (Optional)
    # =============================
    # You can save the trained K-Means model and pipeline if needed for future use
    model_path = "health_kmeans_model"
    pipeline_path = "health_kmeans_pipeline"
    print(f"Saving K-Means model to {model_path}")
    model.save(model_path)
    print(f"Saving K-Means pipeline to {pipeline_path}")
    pipeline_model.save(pipeline_path)

except Exception as e:
    print(f"An error occurred: {str(e)}")

finally:
    # Step 6: Cleanup
    # ==============
    print("===========================================================================================================")
    print("===========================================================================================================")
    print("===========================================================================================================")
    print("Stopping Spark session...")
    print("===========================================================================================================")
    print("===========================================================================================================")
    print("===========================================================================================================")
    spark.stop()
