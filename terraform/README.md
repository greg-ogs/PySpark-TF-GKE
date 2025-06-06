# GKE Cluster for PySpark and TensorFlow

This Terraform configuration creates a Google Kubernetes Engine (GKE) cluster with two node pools:
1. A node pool for PySpark workloads (2 nodes)
2. A node pool for TensorFlow workloads (2 nodes)

## Architecture

The configuration creates the following resources:
- A VPC network and subnet with secondary IP ranges for pods and services
- A Cloud Router and NAT for the private GKE cluster
- Firewall rules for internal cluster communication
- A private GKE cluster with Workload Identity enabled
- A service account for the GKE nodes with appropriate IAM roles
- Two node pools with CPU-only machines:
    - PySpark node pool: 2 nodes with e2-standard-4 (4 vCPUs, 16GB memory)
    - TensorFlow node pool: 2 nodes with e2-standard-8 (8 vCPUs, 32GB memory)

## Prerequisites

- Google Cloud SDK installed and configured
- Terraform v1.0.0 or newer
- A Google Cloud project with the following APIs enabled:
    - Compute Engine API
    - Kubernetes Engine API
    - IAM API
    - Resource Manager API

## Usage

1. Initialize the Terraform configuration:
   ```
   terraform init
   ```

2. Create a `terraform.tfvars` file with your project ID:
   ```
   project_id = "your-project-id"
   ```

3. Review the execution plan:
   ```
   terraform plan
   ```

4. Apply the configuration:
   ```
   terraform apply
   ```

5. After the deployment is complete, you can get the kubectl credentials using the command provided in the outputs:
   ```
   gcloud container clusters get-credentials CLUSTER_NAME --zone ZONE --project PROJECT_ID
   ```

## Variables

| Name | Description | Default |
|------|-------------|---------|
| project_id | The GCP project ID | (required) |
| region | The GCP region for the resources | us-central1 |
| zone | The GCP zone for zonal resources | us-central1-a |
| vpc_name | Name of the VPC network | gke-network |
| subnet_name | Name of the subnet for GKE | gke-subnet |
| subnet_cidr | CIDR range for the subnet | 10.10.0.0/24 |
| pods_cidr | CIDR range for pods | 10.20.0.0/16 |
| services_cidr | CIDR range for services | 10.30.0.0/16 |
| cluster_name | Name of the GKE cluster | ml-cluster |
| pyspark_node_count | Number of nodes in the PySpark node pool | 2 |
| pyspark_machine_type | Machine type for PySpark nodes | e2-standard-4 |
| tensorflow_node_count | Number of nodes in the TensorFlow node pool | 2 |
| tensorflow_machine_type | Machine type for TensorFlow nodes | e2-standard-8 |

## Outputs

| Name | Description |
|------|-------------|
| cluster_name | The name of the GKE cluster |
| cluster_location | The location (zone) of the GKE cluster |
| cluster_endpoint | The IP address of the Kubernetes master endpoint |
| cluster_ca_certificate | The public certificate of the cluster's certificate authority |
| pyspark_node_pool_name | Name of the PySpark node pool |
| tensorflow_node_pool_name | Name of the TensorFlow node pool |
| vpc_name | The name of the VPC |
| subnet_name | The name of the subnet |
| service_account_email | The email of the service account used by the GKE nodes |
| kubectl_command | Command to get kubectl credentials for the cluster |

## Customization

You can customize the configuration by modifying the variables in `variables.tf` or by providing different values in your `terraform.tfvars` file.

# Running PySpark Applications on GKE Spark Cluster

This guide outlines the steps to submit a PySpark script to a Spark cluster deployed on Google Kubernetes Engine (GKE) and how to verify its execution and workload distribution.

## Prerequisites

1.  A provisioned GKE cluster with a Spark node pool.
2.  Spark master and worker deployments and services running in the cluster (e.g., using `spark-master-deployment.yaml`, `spark-master-service.yaml`, `spark-worker-deployment.yaml`).
3.  A bastion host VM (`gke-bastion`) configured with `gcloud` and `kubectl` to interact with the GKE cluster (as per `connection.tf`).
4.  Your PySpark script (e.g., `spark.py`) ready.

## Steps to Submit and Monitor Your PySpark Script

The primary method described here involves copying your script to the Spark master pod and executing it from there.

### 1. Access Your GKE Cluster via the Bastion Host

a.  **Get the SSH command for the bastion host:**
If you have Terraform installed and are in your project directory, run:
```bash
terraform output ssh_command
```
This will output a command similar to:
```bash
gcloud compute ssh gke-bastion --zone=<your-zone> --project=<your-project-id>
```

b.  **SSH into the bastion host:**
Execute the command obtained in the previous step.

c.  **Verify `kubectl` access:**
Once on the bastion host, confirm `kubectl` is configured and can communicate with your cluster:
```bash
kubectl get nodes
```
You should see a list of your cluster nodes.

### 2. Identify the Spark Master Pod

a.  Use the label defined in your Spark master deployment (`app: spark-master`) to find the pod name:
```bash
kubectl get pods -l app=spark-master
```
Output will be similar to:
```
NAME                            READY   STATUS    RESTARTS   AGE
spark-master-7f7f6f78f7-abcde   1/1     Running   0          1h
```
Note down the full name of the Spark master pod (e.g., `spark-master-7f7f6f78f7-abcde`).

### 3. Copy Your PySpark Script to the Spark Master Pod

a.  **Ensure your script is on the bastion host:**
If your `spark.py` (or other script) is on your local machine, you'll first need to copy it to the bastion host. You can use `gcloud compute scp`:
```bash
# From your local machine, not the bastion
gcloud compute scp /path/to/your/local/spark.py <your-bastion-user>@gke-bastion:/tmp/spark.py --zone=<your-zone> --project=<your-project-id>
```
Replace placeholders accordingly. `/tmp/spark.py` is a suggested path on the bastion.

b.  **Copy the script from the bastion to the Spark master pod:**
From the bastion host's terminal:
```bash
kubectl cp /tmp/spark.py <spark-master-pod-name>:/opt/spark/work-dir/spark.py
```
Replace `/tmp/spark.py` with the path to your script on the bastion and `<spark-master-pod-name>` with the name you identified. `/opt/spark/work-dir/` is a common writable directory within the official Spark Docker images.

### 4. Execute the PySpark Script Inside the Master Pod

a.  **Access the Spark master pod's shell:**
```bash
kubectl exec -it <spark-master-pod-name> -- /bin/bash
```

b.  **Run `spark-submit`:**
Once inside the master pod's shell, navigate to the directory where you copied the script (if needed) and use `spark-submit`:
```bash
/opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  /opt/spark/work-dir/spark.py
```
*   `--master spark://spark-master:7077`: This uses the Kubernetes service name (`spark-master`) and port (`7077`) defined in your `spark-master-service.yaml`.
*   `/opt/spark/work-dir/spark.py`: Path to your script inside the pod.

### 5. Check Workload Distribution and Script Output

a.  **Direct Script Output:**
The output of your `spark.py` script (e.g., `print` statements) will appear directly in the terminal of the Spark master pod where you ran `spark-submit`. For the example `spark.py`, you'll see:
```
Counts per partition: [100000, 100000, ..., 100000]
Total processed items: 10000000
```

b.  **Spark Web UI:**
*   **Set up port forwarding (from the bastion host):**
    Open a *new* terminal window for the bastion host (or use a terminal multiplexer like `tmux` or `screen`) and run:
```bash
kubectl port-forward svc/spark-master 8080:8080
```
This forwards local port `8080` on your bastion to the Spark master UI port `8080` in the cluster. Keep this command running.
*   **Access the UI:**
    If your bastion host has a graphical environment and a browser, open `http://localhost:8080`.
    If your bastion is headless, you might need to set up an SSH tunnel from your local machine to the bastion:
```bash
# From your local machine
ssh -L 8080:localhost:8080 <your-bastion-user>@<bastion-external-ip>
```
Then, on your local machine, open `http://localhost:8080` in a web browser.
*   **Explore the UI:** You'll see your application listed. Click on its name ("MyPySparkApp" for the example script) to view stages, tasks, and the distribution of work across executors (your Spark workers).

c.  **Worker Pod Logs:**
*   **Get worker pod names:**
```bash
kubectl get pods -l app=spark-worker
```
*   **Check logs for a specific worker or stream from all:**
```bash
# Logs for a specific worker
kubectl logs <spark-worker-pod-name> -c spark-worker

          # Follow (stream) logs from all worker pods
          kubectl logs -f -l app=spark-worker -c spark-worker
          ```
          Look for messages indicating task execution.

## Alternative: Submitting from the Bastion VM as a Client

You can also run `spark-submit` directly from the bastion VM if you install Spark tools on it.

1.  **Install Spark on the Bastion VM:** Download and configure a compatible Spark version on the `gke-bastion` VM.
2.  **Ensure Script is on Bastion:** Your `spark.py` must be accessible on the bastion.
3.  **Port-Forward Spark Master Service:**
    ```bash
    # On the bastion VM, keep this running
    kubectl port-forward svc/spark-master 7077:7077
    ```
4.  **Submit the Job from Bastion:**
    ```bash
    # On the bastion VM, in another terminal
    # Replace /path/to/your/bastion/spark/bin/spark-submit and /path/to/your/spark.py
    /path/to/your/bastion/spark/bin/spark-submit \
      --master spark://localhost:7077 \
      /path/to/your/spark.py
    ```
This method requires an extra Spark installation on the bastion but can be useful for certain workflows. The `kubectl exec` method is generally simpler for interacting with Spark running entirely within Kubernetes.