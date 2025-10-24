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
4.  Your PySpark script (e.g., `main.py`) ready.

## Bastion instance requirements
1.  **Install Spark on the Bastion VM:** Download and configure a compatible Spark version on the `gke-bastion` VM.
2.  **Ensure Script is on Bastion:** Your `main.py` must be accessible on the bastion.

This method requires an extra Spark installation on the bastion but can be useful for certain workflows.

## Steps to Submit Your PySpark Script

The primary method described here involves copying your script to the `gke_bastion` instance and executing it from there.

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
Once in the bastion host, confirm `kubectl` is configured and can communicate with your cluster:
```bash
terraform output kubectl_command
```
Execute the command obtained in the previous step and then execute
```bash
kubectl get nodes
```
You should see a list of your cluster nodes.

### 2. Identify the Kubernetes Service IP for the Spark Master deployment

a.  Use the label defined in your Spark master deployment (`app: spark-master`) to find the pod name:
```bash
kubectl get services
```

### 3. Copy Your PySpark Script to the gke_bastion Instance

If your `main.py` (or another script) is on your local machine, you'll first need to copy it to the bastion host. You can use `gcloud compute scp`:
```bash
# From your local machine, not the bastion
gcloud compute scp /path/to/your/local/spark.py <your-bastion-user>@gke-bastion:/tmp/spark.py --zone=<your-zone> --project=<your-project-id>
```
Replace placeholders accordingly. 
`/tmp/main.py` is a suggested path on the bastion.

### 4. Upload your dataset to google storage bucket
Use the `upload_dataset.sh` to upload your dataset to google storage bucket. Edit the script to match the actual dataset name.
```bash
bash ./upload_dataset.sh
```
> At the end, a config map with the project id will be created as a variable holder for the gcs-connector in the submit command.

## Using Workload Identity with Spark for GCS Access

This project uses GKE Workload Identity to allow Spark pods to access Google Cloud Storage (GCS) without requiring service account keys. Here's how it works:

### 1. Understanding Workload Identity

Workload Identity is a GKE feature that allows Kubernetes service accounts to act as Google service accounts. This means:

- Pods can access GCP resources using the permissions of the bound Google service account
- No need to download or manage service account keys
- More secure and manageable authentication

### 2. Setup Components

The following components are set up for Workload Identity:

1. **GKE Cluster Configuration**: Workload Identity is enabled on the cluster with `workload_pool = "${var.project_id}.svc.id.goog"`
2. **Kubernetes Service Account**: A service account named `spark-sa` is created in the Kubernetes cluster
3. **IAM Binding**: The Kubernetes service account is bound to the GKE service account with the role `roles/iam.workloadIdentityUser`
4. **Storage Permissions**: The GKE service account has `roles/storage.objectViewer` permission on the GCS bucket

### 3. Applying Workload Identity Configuration

After deploying the infrastructure with Terraform, run the provided script to apply the Workload Identity configuration:

```bash
bash ./config.sh
```

This script:
- Creates the Kubernetes service account with the proper annotation.
- Applies the ConfigMap with the project ID as variable holder for the gcs-connector in the submit command.
- Restarts the Spark deployments to pick up the new service account.

### 4. Running Spark Jobs with GCS Access

Once Workload Identity is configured, you can run Spark jobs that access GCS without additional authentication:

```bash
spark-submit \
    --master spark://<load balancer service ip>:7077 \
    --deploy-mode client \
    --name health-kmeans-job-standalone \
    --packages com.google.cloud.bigdataoss:gcs-connector:hadoop3-2.2.2 \
    --conf spark.hadoop.fs.gs.impl=com.google.cloud.hadoop.fs.gcs.GoogleHadoopFileSystem \ 
    --conf spark.hadoop.fs.AbstractFileSystem.gs.impl=com.google.cloud.hadoop.fs.gcs.GoogleHadoopFS main.py
```

The Spark pods will automatically use the GKE service account's permissions to access GCS.
