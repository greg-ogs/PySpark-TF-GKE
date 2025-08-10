# Use a Spark base image
FROM spark:latest

# Set a working directory
WORKDIR /app

# Download the MySQL JDBC connector and place it in the Spark jars directory
# This version (8.4.0) matches the MySQL server image version.
COPY jars/mysql-connector-j-8.4.0.jar /opt/spark/jars/
# Copy the Python script into the container
COPY spark_workload_to_local_k8s.py .

# Set the default command to run the Spark script
CMD ["/opt/spark/bin/spark-submit", "spark_workload_to_local_k8s.py"]