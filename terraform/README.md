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