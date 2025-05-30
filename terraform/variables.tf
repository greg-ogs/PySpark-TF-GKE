# Project variables
variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The GCP region for the resources"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "The GCP zone for zonal resources"
  type        = string
  default     = "us-central1-a"
}

# Network variables
variable "vpc_name" {
  description = "Name of the VPC network"
  type        = string
  default     = "gke-network"
}

variable "subnet_name" {
  description = "Name of the subnet for GKE"
  type        = string
  default     = "gke-subnet"
}

variable "subnet_cidr" {
  description = "CIDR range for the subnet"
  type        = string
  default     = "10.10.0.0/24"
}

variable "pods_cidr" {
  description = "CIDR range for pods"
  type        = string
  default     = "10.20.0.0/16"
}

variable "services_cidr" {
  description = "CIDR range for services"
  type        = string
  default     = "10.30.0.0/16"
}

# GKE cluster variables
variable "cluster_name" {
  description = "Name of the GKE cluster"
  type        = string
  default     = "ml-cluster"
}

# Node pool variables
variable "spark_node_count" {
  description = "Number of nodes in the Spark node pool"
  type        = number
  default     = 2
}

variable "spark_machine_type" {
  description = "Machine type for Spark nodes"
  type        = string
  default     = "e2-standard-4"  # 4 vCPUs, 16GB memory
}

variable "tensorflow_node_count" {
  description = "Number of nodes in the TensorFlow node pool"
  type        = number
  default     = 2
}

variable "tensorflow_machine_type" {
  description = "Machine type for TensorFlow nodes"
  type        = string
  default     = "e2-standard-8"  # 8 vCPUs, 32GB memory
}