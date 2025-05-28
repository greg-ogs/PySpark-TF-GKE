from pyspark.sql import SparkSession
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.clustering import KMeans
from pyspark.sql.functions import col
import random

# 1. Create a SparkSession
spark = SparkSession.builder.appName("KMeansExample").getOrCreate()

# 2. Generate Synthetic Data
# Let's create data for 3 distinct clusters
data = []
num_points_per_cluster = 50
random.seed(42) # for reproducibility

# Cluster 1: around (1, 1)
for _ in range(num_points_per_cluster):
    data.append((random.gauss(1, 0.5), random.gauss(1, 0.5)))

# Cluster 2: around (5, 5)
for _ in range(num_points_per_cluster):
    data.append((random.gauss(5, 0.5), random.gauss(5, 0.5)))

# Cluster 3: around (1, 5)
for _ in range(num_points_per_cluster):
    data.append((random.gauss(1, 0.5), random.gauss(5, 0.5)))

# Create a DataFrame
columns = ["feature1", "feature2"]
df = spark.createDataFrame(data, columns)

print("--- Sample of Generated Data ---")
df.show(5)

# 3. Prepare Data for K-Means
# K-Means expects a single column containing a vector of features.
# We'll use VectorAssembler to combine "feature1" and "feature2".
assembler = VectorAssembler(
    inputCols=["feature1", "feature2"],
    outputCol="features"  # This is the conventional name
)

assembled_df = assembler.transform(df)

print("--- Data Assembled for K-Means ---")
assembled_df.select("feature1", "feature2", "features").show(5, truncate=False)

# 4. Instantiate and Train K-Means Model
# We know we generated data for 3 clusters, so we set k=3
k = 3
kmeans = KMeans().setK(k).setSeed(1) # setSeed for reproducibility of K-Means initialization

print(f"\n--- Training K-Means model with k={k} ---")
model = kmeans.fit(assembled_df)

# 5. Get Cluster Predictions
predictions = model.transform(assembled_df)

print("--- Data with Cluster Predictions ---")
predictions.select("feature1", "feature2", "features", "prediction").show(10)

# 6. Show Cluster Centers
print("--- Cluster Centers ---")
centers = model.clusterCenters()
for i, center in enumerate(centers):
    print(f"Center for Cluster {i}: {center}")

# 7. (Optional) Evaluate Clustering (Silhouette Score)
# For a more formal evaluation, you can use ClusteringEvaluator
# from pyspark.ml.evaluation import ClusteringEvaluator
# evaluator = ClusteringEvaluator()
# silhouette = evaluator.evaluate(predictions)
# print(f"\nSilhouette with squared euclidean distance = {silhouette}")

# 8. Stop SparkSession
spark.stop()