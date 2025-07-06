# Bastion host service account
resource "google_service_account" "bastion_sa" {
  account_id   = "bastion-sa"
  display_name = "Service Account for GKE Bastion Host"
}

# Grant required roles to the bastion service account
resource "google_project_iam_member" "bastion_sa_roles" {
  for_each = toset([
    "roles/container.developer",   # Allows kubectl operations
    "roles/logging.viewer",        # View logs
    "roles/monitoring.viewer"     # View monitoring
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.bastion_sa.email}"
}

# Add storage.objects.viewer role to the bastion service account
resource "google_storage_bucket_iam_member" "bastion_sa_storage_viewer" {
  bucket = google_storage_bucket.datasets_bucket.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.bastion_sa.email}"
}

# Add storage.objects.create permission to the bastion service account
resource "google_storage_bucket_iam_member" "bastion_sa_storage_creator" {
  bucket = google_storage_bucket.datasets_bucket.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.bastion_sa.email}"
}

# Firewall rule to allow SSH access to the bastion host
resource "google_compute_firewall" "bastion_ssh" {
  name    = "allow-ssh-to-bastion"
  network = google_compute_network.gke_network.self_link

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  # Restrict SSH access to your IP or a range you control
  # Replace with your IP or range in CIDR notation
  source_ranges = ["0.0.0.0/0"]  # WARNING: Change this to your specific IP range in production
  target_tags   = ["bastion-host"]
}

# Bastion host instance
# Startup script
locals {
  startup_script_path = "/terraform/start-up.sh"
  startup_script_content = file(local.startup_script_path)
}

resource "google_compute_instance" "bastion" {
  name         = "gke-bastion"
  machine_type = "e2-medium"
  zone         = var.zone

  tags = ["bastion-host"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 10
    }
  }

  network_interface {
    network    = google_compute_network.gke_network.self_link # pointing to main network configuration
    subnetwork = google_compute_subnetwork.gke_subnet.self_link

    # Assign a public IP to the bastion
    access_config {
      // Ephemeral public IP
    }
  }

  service_account {
    email  = google_service_account.bastion_sa.email
    scopes = ["cloud-platform"]
  }

  # Apply the startup script to install gcloud, kubectl, and configure kubectl & Pyspark
  metadata = {
    startup-script = local.startup_script_content # this is where startup script file is passed.
  }

  # Make sure this instance depends on the cluster
  depends_on = [google_container_cluster.primary]
}
