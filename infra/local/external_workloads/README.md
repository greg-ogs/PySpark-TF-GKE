# First service: Run Spark driver outside Kubernetes using Docker Compose

This setup lets you run the Spark driver ("bastion") outside your local Kubernetes cluster, while executing against the Spark master and workers inside the cluster. The container includes Python deps and the MySQL JDBC driver.

---
## Prerequisites
- A running local Kubernetes cluster (e.g., kind) with:
  - Spark master/workers deployed (infra/local/local_spark manifests)
  - MySQL StatefulSet and Services deployed (infra/local/mysql-database)
- kubectl available and connected to your local cluster
- Docker installed and running

---
## 1) Port-forward services from the cluster
Open a terminal and keep it running:

PowerShell:

```
# Spark master: RPC and Web UI
kubectl port-forward svc/spark-master 7077:7077 8080:8080

# MySQL primary (or external service):
# If you applied mysql-services.yaml, you can use mysql-external
kubectl port-forward svc/mysql-external 3306:3306
```

This provides:
- Spark master RPC at localhost:7077
- Spark master UI at http://localhost:8080
- MySQL at localhost:3306

---
## 2) Bring up the external bastion container
From this directory:

```
docker compose up -d --build
```

This builds from ../local_spark/bastion.Dockerfile and starts a container that sleeps. It exposes:
- 7078: Spark driver port
- 7079: Spark block manager port

Environment defaults inside the container:
- SPARK_DRIVER_HOST=host.docker.internal
- SPARK_DRIVER_PORT=7078
- SPARK_BLOCKMGR_PORT=7079
- DB_HOST=host.docker.internal
- DB_PORT=3306

The repository's workloads directory is mounted read-only at /workloads.

---
## 3) Exec into the container and run the workload
Open a shell inside the container:

```
docker exec -it spark-bastion-external bash
```

Submit the job (inside the container):

```
spark-submit \
  --master ${SPARK_MASTER:-spark://host.docker.internal:7077} \
  --conf spark.driver.host=${SPARK_DRIVER_HOST:-host.docker.internal} \
  --conf spark.driver.bindAddress=0.0.0.0 \
  --conf spark.driver.port=${SPARK_DRIVER_PORT:-7078} \
  --conf spark.blockManager.port=${SPARK_BLOCKMGR_PORT:-7079} \
  --conf spark.ui.showConsoleProgress=false \
  /workloads/local_cluster_workloads/spark_retrieve_data_outside.py
```

If you need to override DB settings, set env vars before running:

```
export DB_HOST=host.docker.internal
export DB_PORT=3306
export DB_USER=root
export DB_PASSWORD=""
export DB_NAME=health_data
export DB_TABLE=health_disparities
```

---
## Notes
- Use host.docker.internal so the container can reach services port-forwarded on the host.
- Ensure port-forward terminals remain open during your run.
- You can view the Spark master UI at http://localhost:8080.

# Second service: Run TensorFlow coordinator outside Kubernetes using Docker Compose

To install metrics in the kubernetes cluster and use `kubectl top` command, run:

```
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl edit deployment metrics-server -n kube-system
```
And add `- --kubelet-insecure-tls` before image definition in the manifest.

The lve stream command is:
```
while ($true) { Clear-Host; kubectl top pods -n default; Start-Sleep -Seconds 2 }
```