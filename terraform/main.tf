# Network resources
resource "google_compute_network" "gke_network" {
  name                    = var.vpc_name
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "gke_subnet" {
  name          = var.subnet_name
  region        = var.region
  network       = google_compute_network.gke_network.self_link
  ip_cidr_range = var.subnet_cidr

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = var.pods_cidr
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = var.services_cidr
  }
}

# Router and NAT for private cluster
resource "google_compute_router" "router" {
  name    = "${var.cluster_name}-router"
  region  = var.region
  network = google_compute_network.gke_network.self_link
}

resource "google_compute_router_nat" "nat" {
  name                               = "${var.cluster_name}-nat"
  router                             = google_compute_router.router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

# Firewall rule for internal cluster communication
resource "google_compute_firewall" "internal_communication" {
  name    = "${var.vpc_name}-allow-internal"
  network = google_compute_network.gke_network.self_link

  allow {
    protocol = "all"
  }

  source_ranges = [
    var.subnet_cidr,
    var.pods_cidr,
    var.services_cidr
  ]
}

# GKE Cluster
resource "google_container_cluster" "primary" {
  name     = var.cluster_name
  location = var.zone

  # We can't create a cluster with no node pool defined, but we want to only use
  # separately managed node pools. So we create the smallest possible default
  # node pool and immediately delete it.
  remove_default_node_pool = true
  initial_node_count       = 1

  network    = google_compute_network.gke_network.self_link
  subnetwork = google_compute_subnetwork.gke_subnet.self_link

  # Enable private cluster
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }

  # Configure IP allocation
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  # Enable workload identity
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Disable autoscaling
  cluster_autoscaling {
    enabled = false
  }

  # Disable deletion protection
  deletion_protection = false
}

# Service account for GKE nodes
resource "google_service_account" "gke_sa" {
  account_id   = "${var.cluster_name}-sa"
  display_name = "GKE Service Account for ${var.cluster_name}"
}

# Grant required roles to the service account
resource "google_project_iam_member" "gke_sa_roles" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/monitoring.viewer",
    "roles/stackdriver.resourceMetadata.writer"
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.gke_sa.email}"
}

# PySpark Node Pool
resource "google_container_node_pool" "pyspark_nodes" {
  name       = "pyspark-pool"
  location   = var.zone
  cluster    = google_container_cluster.primary.name
  node_count = var.pyspark_node_count

  node_config {
    machine_type = var.pyspark_machine_type

    # Google recommends custom service accounts with minimal permissions
    # that are specific to the workloads running within the cluster
    service_account = google_service_account.gke_sa.email

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    labels = {
      workload = "pyspark"
    }

    taint {
      key    = "workload"
      value  = "pyspark"
      effect = "NO_SCHEDULE"
    }

    # Enable workload identity on the node pool
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
}

# TensorFlow Node Pool
resource "google_container_node_pool" "tensorflow_nodes" {
  name       = "tensorflow-pool"
  location   = var.zone
  cluster    = google_container_cluster.primary.name
  node_count = var.tensorflow_node_count

  node_config {
    machine_type = var.tensorflow_machine_type

    # Google recommends custom service accounts with minimal permissions
    # that are specific to the workloads running within the cluster
    service_account = google_service_account.gke_sa.email

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    labels = {
      workload = "tensorflow"
    }

    taint {
      key    = "workload"
      value  = "tensorflow"
      effect = "NO_SCHEDULE"
    }

    # Enable workload identity on the node pool
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
}
