# Run a Python Spark workload on a local Kubernetes cluster
Run a Python Spark driver on in a local kubernetes cluster
(using kind) and execute the workload on a Spark standalone cluster.

---

## Expose the Spark master to your local machine
It's possible to use NodePort Service for `spark-master`, but in kind the most reliable approach is port-forwarding.

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
## Build the images for the spark deployments
- Use **infra/general_spark/Dockerfile** for the **spark-master** and **spark-worker** deployments.
- Use **infra/general_spark/bastion.Dockerfile** for the **spark-workload** pod.
---
## Apply the manifests
Apply the manifests to your cluster:
- MySQL stateful-set.
  - `kubctl apply -f /infra/mysql-database/replica-primary.ymal`
  - `kubctl apply -f /infra/mysql-database/mysql-services.ymal` 
  - `kubctl apply -f /infra/mysql-database/mysql-statefulset.ymal` 
  > After the stateful-set is created and the pods are ready,
  > run a port forward ` kubectl port-forward svc/mysql-external 3306:3306` and the load_csv.py script to load 
  > a csv into the database. 
- Spark deployment
  - `kubectl apply -f /infra/general_spark/gcp-config.yaml`
  - `kubectl apply -f /infra/general_spark/spark-k8s-sa.yaml`
  - `kubectl apply -f /infra/general_spark/spark-master-service.yaml`
  - `kubectl apply -f /infra/general_spark/spark-master-deployment.yaml`
  - `kubectl apply -f /infra/general_spark/spark-worker-deployment.yaml`
- Spark-workload pod
  - `kubectl apply -f /infra/general_spark/spark-workload-service.yaml`
  - `kubectl apply -f /infra/general_spark/bastion_pod.yaml` 
---
## Command to run inside the bastion pod (spark-workload)

Run this inside the shell of the spark-workload pod to submit the job:

```
spark-submit \
  --master spark://spark-master:7077 \
  --conf spark.driver.host=spark-workload \
  --conf spark.driver.bindAddress=0.0.0.0 \
  --conf spark.driver.port=7078 \
  --conf spark.blockManager.port=7079 \
  /app/spark_workload_to_local_k8s.py
```

> Notes
>>  - These settings align with your spark-workload ClusterIP Service (driver 7078, block manager 7079) and your script’s defaults. Passing them via spark-submit ensures they match the Service DNS and ports.

>>  - Adjust the script path if your image places it elsewhere. Common path based on your repo layout is `/app/spark_checks/python_checks/spark_workload_to_local_k8s.py`. Use `ls` to verify.

>>  - If needed, you can override DB settings via environment variables before running the command inside the pod:
>>    - `export DB_HOST=mysql-read`
>>    - `export DB_PORT=3306`
>>    - `export DB_USER=root`
>>    - `export DB_PASSWORD=''` (or your password)
>>    - `export DB_NAME=health_data`
>>    - `export DB_TABLE=health_disparities`

### How to exec into the pod (from your workstation)

If in the image for the spark-worker pod (gregogs/spark:bastion_workloads) the COPY command for the python script is commented out, copy to the pod using kubectl cp:

```
kubectl cp .\spark_checks\python_checks\spark_workload_to_local_k8s.py default/spark-workload:/app/
```

For completeness, open a shell in the pod first, then run the command above:

```
kubectl exec -it spark-workload
```