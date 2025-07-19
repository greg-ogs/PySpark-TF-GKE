FROM tensorflow/tensorflow:latest-gpu
LABEL authors="greg-ogs"

WORKDIR /app

COPY requirements.txt /app

RUN pip install -r requirements.txt

RUN pip install Flask --ignore-installed blinker

RUN apt-get update && apt-get install -y openjdk-17-jdk