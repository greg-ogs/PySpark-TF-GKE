FROM spark:latest

LABEL authors="greg-ogs"
# gregogs/spark:custom-with-jdbc
# docker image rm gregogs/spark:custom-with-jdbc ; docker build -no-cache -t gregogs/spark:custom-with-jdbc .\infra\general_spark\

WORKDIR /app

COPY ./requirements.txt /app

USER root

RUN pip install -r requirements.txt

USER spark

COPY ./jars/mysql-connector-j-8.4.0.jar /opt/spark/jars/
