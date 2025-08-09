### Goal
Run your Python Spark driver on your local Windows machine and execute the workload on a Spark standalone cluster running inside your local kind Kubernetes cluster.

This requires:
- The driver can reach the Spark master service (port 7077)
- Executors (pods) can connect back to your driver on fixed, reachable ports
- Your script uses `spark://...` standalone master, not Spark-on-Kubernetes configs

---

### Expose the Spark master to your local machine
You already have a NodePort Service for `spark-master`, but in kind the most reliable approach is port-forwarding.

- In a terminal, run and keep it open:

```powershell
kubectl port-forward svc/spark-master 7077:7077 8080:8080
```

This provides:
- Master RPC: `localhost:7077`
- Web UI: http://localhost:8080

Alternative (NodePort):
- Get the nodePort assigned to 7077:

```powershell
kubectl get svc spark-master -o jsonpath="{.spec.ports[?(@.port==7077)].nodePort}"
```

- Use `spark://127.0.0.1:<nodePort>` if your kind cluster was created with extraPortMappings. Otherwise, use port-forwarding.

---

### Configure driver so executors can call back
Executors run inside pods and must connect back to your driver. On Windows with Docker Desktop, pods can reach `host.docker.internal`. Fix driver ports so you can open them in the firewall.

Set these Spark configs in your script (or with `spark-submit`):
- `spark.driver.host = host.docker.internal`
- `spark.driver.bindAddress = 0.0.0.0`
- `spark.driver.port = 20020`
- `spark.blockManager.port = 20021`

Open these ports in Windows Firewall (one-time):

```powershell
New-NetFirewallRule -DisplayName "SparkDriver20020" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 20020
New-NetFirewallRule -DisplayName "SparkDriver20021" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 20021
```

---

### Update your Python script (run driver outside the cluster)
Replace the SparkSession builder in `spark_checks\python_checks\spark_workload_to_k8s.py` with this:

```python
from pyspark.sql import SparkSession
import os

# Master exposed via port-forward: kubectl port-forward svc/spark-master 7077:7077
master_url = os.getenv("SPARK_MASTER_URL", "spark://localhost:7077")

spark = (
    SparkSession.builder
    .appName("HealthKMeansClassification")
    .master(master_url)
    # Allow executors (pods) to connect back to this driver running on Windows host
    .config("spark.driver.host", os.getenv("SPARK_DRIVER_HOST", "host.docker.internal"))
    .config("spark.driver.bindAddress", os.getenv("SPARK_DRIVER_BIND_ADDRESS", "0.0.0.0"))
    .config("spark.driver.port", os.getenv("SPARK_DRIVER_PORT", "20020"))
    .config("spark.blockManager.port", os.getenv("SPARK_BLOCKMGR_PORT", "20021"))
    .getOrCreate()
)
```

Adjust your data source to avoid GCS by default and only use it when explicitly enabled:

```python
import os

use_gcs = os.getenv("USE_GCS", "false").lower() == "true"
project_id = os.getenv("GCP_PROJECT_ID")

if use_gcs and project_id:
    bucket_name = f"{project_id}-datasets"
    data_path = f"gs://{bucket_name}/health.csv"
    print(f"Loading from GCS: {data_path}")
else:
    # Use local file path; ensure file:/// URL form
    data_path = os.getenv("HEALTH_CSV_PATH", "file:///C:/data/health.csv")
    print(f"Loading from local path: {data_path}")
```

Ensure any save paths are local file URLs too:

```python
model_dir = os.getenv("MODEL_DIR", "file:///C:/tmp/health_kmeans_model")
pipeline_dir = os.getenv("PIPELINE_DIR", "file:///C:/tmp/health_kmeans_pipeline")
```

Remove any `spark.kubernetes.*` configs from the script. They are for Spark-on-Kubernetes submission mode, not for a pre-deployed standalone master.

---

### Run sequence on Windows (PowerShell)
1) Ensure cluster resources are up:
```powershell
kubectl apply -f infra\general_spark\spark-k8s-sa.yaml
kubectl apply -f infra\general_spark\gcp-config.yaml
kubectl apply -f infra\general_spark\spark-master-deployment.yaml
kubectl apply -f infra\general_spark\spark-master-service.yaml
kubectl apply -f infra\general_spark\spark-worker-deployment.yaml
kubectl rollout status deploy/spark-master
kubectl rollout status deploy/spark-worker
```

2) Port-forward the master:
```powershell
kubectl port-forward svc/spark-master 7077:7077 8080:8080
```

3) Open firewall for driver callback ports (first time only):
```powershell
New-NetFirewallRule -DisplayName "SparkDriver20020" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 20020
New-NetFirewallRule -DisplayName "SparkDriver20021" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 20021
```

4) Run your script locally with appropriate env vars:
```powershell
$env:SPARK_MASTER_URL = "spark://localhost:7077"
$env:SPARK_DRIVER_HOST = "host.docker.internal"
$env:SPARK_DRIVER_PORT = "20020"
$env:SPARK_BLOCKMGR_PORT = "20021"
$env:HEALTH_CSV_PATH = "file:///C:/data/health.csv"  # adjust path
python C:\Users\grego\GitHub\PySpark-TF-GKE\spark_checks\python_checks\spark_workload_to_k8s.py
```

5) Monitor
- Spark Master UI: http://localhost:8080
- Worker logs: `kubectl logs -f deploy/spark-worker`

---

### Optional: use spark-submit instead
If you have a local Spark installation matching the cluster version, you can submit via CLI instead of building the session in code:

```powershell
<SPARK_HOME>\bin\spark-submit `
  --master spark://localhost:7077 `
  --conf spark.driver.host=host.docker.internal `
  --conf spark.driver.bindAddress=0.0.0.0 `
  --conf spark.driver.port=20020 `
  --conf spark.blockManager.port=20021 `
  C:\Users\grego\GitHub\PySpark-TF-GKE\spark_checks\python_checks\spark_workload_to_k8s.py
```

---

### Common pitfalls and fixes
- Executors cannot connect to driver:
  - Ensure `SPARK_DRIVER_HOST=host.docker.internal` and firewall allows ports 20020/20021
  - Keep ports fixed via `spark.driver.port` and `spark.blockManager.port`

- Driver cannot reach master:
  - Keep the port-forward running; use `SPARK_MASTER_URL=spark://localhost:7077`

- health.csv not found:
  - Use a `file:///` URL to a path accessible by your local Python process (driver)

---

### Summary
- Expose master via `kubectl port-forward` and point the driver to `spark://localhost:7077`
- Configure driver callback: `driver.host=host.docker.internal`, bind to `0.0.0.0`, fix ports 20020/20021
- Default to local file paths; keep GCS optional
- Remove `spark.kubernetes.*` settings from the script

With these changes, you will run the script on your machine while the executors run inside your kind cluster and process the workload.