FROM tensorflow/tensorflow

RUN apt-get update && \
    apt-get install -y openjdk-17-jdk-headless && \
    apt-get clean

#ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

# Install Python dependencies
RUN pip install pyspark==4.0.0

# Set the working directory
WORKDIR /app

# Copy the application code
COPY spark.py /app/

# Run the spark.py script when the container starts
CMD ["python", "spark.py"]