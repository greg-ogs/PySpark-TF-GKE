FROM spark:latest

LABEL authors="greg-ogs"
# gregogs/spark:bastion_workloads
# docker image rm gregogs/spark:bastion_workloads ; docker build --no-cache -f .\infra\local\local_spark\bastion\bastion.Dockerfile -t gregogs/spark:bastion_workloads .\infra\local\local_spark\
# Image for bastion pod used to submit Spark jobs inside the cluster

WORKDIR /app

COPY ./bastion/requirements.txt /app/requirements.txt

USER root

RUN pip install -r /app/requirements.txt \
 && mkdir -p /opt/spark/jars

USER spark
# MySQL JDBC driver for JDBC reads
COPY ./jars/mysql-connector-j-8.4.0.jar /opt/spark/jars/

# Optionally copy the workload script into the image; uncomment if you want it embedded.
# COPY ../../spark_checks/python_checks/spark_workload_to_local_k8s.py /opt/spark/spark_workload_to_local_k8s.py

# Keep the pod alive; exec into it to run spark-submit manually when needed
CMD ["bash", "-lc", "sleep infinity"]
