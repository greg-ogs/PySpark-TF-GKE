FROM spark:latest

LABEL authors="greg-ogs"
# gregogs/spark:custom-with-jdbc

WORKDIR /app

COPY ./requirements.txt /app

USER root

RUN pip install -r requirements.txt

USER spark

COPY ./jars/mysql-connector-j-8.4.0.jar /opt/spark/jars/
