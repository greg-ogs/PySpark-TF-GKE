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

# Allow master to communicate with nodes for kubectl exec/logs/cp
resource "google_compute_firewall" "master_to_nodes" {
  name    = "${var.vpc_name}-allow-master-to-nodes"
  network = google_compute_network.gke_network.self_link

  allow {
    protocol = "tcp"
    ports    = ["10250", "443"] # Kubelet and webhooks
  }

  source_ranges = [google_container_cluster.primary.private_cluster_config[0].master_ipv4_cidr_block]
  target_tags = ["spark-node", "gke-nodes"]
}