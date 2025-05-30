FROM gcr.io/spark-operator/spark-py:v3.1.1
COPY spark.py /opt/spark/work-dir/
WORKDIR /opt/spark/work-dir