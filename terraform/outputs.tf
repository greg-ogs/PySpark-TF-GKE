# Cluster outputs
output "cluster_name" {
  description = "The name of the GKE cluster"
  value       = google_container_cluster.primary.name
}

output "cluster_location" {
  description = "The location (zone) of the GKE cluster"
  value       = google_container_cluster.primary.location
}

output "cluster_endpoint" {
  description = "The IP address of the Kubernetes master endpoint"
  value       = google_container_cluster.primary.endpoint
  sensitive   = true
}

output "cluster_ca_certificate" {
  description = "The public certificate of the cluster's certificate authority"
  value       = base64decode(google_container_cluster.primary.master_auth[0].cluster_ca_certificate)
  sensitive   = true
}

# Node pool outputs
output "spark_node_pool_name" {
  description = "Name of the Spark node pool"
  value       = google_container_node_pool.spark_nodes.name
}

# output "tensorflow_node_pool_name" {
#   description = "Name of the TensorFlow node pool"
#   value       = google_container_node_pool.tensorflow_nodes.name
# }

# Network outputs
output "vpc_name" {
  description = "The name of the VPC"
  value       = google_compute_network.gke_network.name
}

output "subnet_name" {
  description = "The name of the subnet"
  value       = google_compute_subnetwork.gke_subnet.name
}

# Service account outputs
output "service_account_email" {
  description = "The email of the service account used by the GKE nodes"
  value       = google_service_account.gke_sa.email
}

# Command to get cluster credentials
output "kubectl_command" {
  description = "Command to get kubectl credentials for the cluster"
  value       = "gcloud container clusters get-credentials ${google_container_cluster.primary.name} --zone ${google_container_cluster.primary.location} --project ${var.project_id}"
}