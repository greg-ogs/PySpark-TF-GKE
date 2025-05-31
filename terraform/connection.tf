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

# Bastion host VM
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
    network    = google_compute_network.gke_network.self_link
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

  # Install gcloud, kubectl, and configure kubectl
  metadata_startup_script = <<-EOF
    #!/bin/bash


    # Create a welcome message with instructions
    cat > /etc/motd <<EOL
    +=======================================================================+
    |                                                                       |
    |  Welcome to the GKE Bastion Host!                                     |
    |                                                                       |
    |  This machine is configured to access your private GKE cluster.       |
    |  You can use kubectl commands directly from here.                     |
    |                                                                       |
    |  Try: kubectl get nodes                                              |
    |                                                                       |
    +=======================================================================+
    EOL
  EOF

  # Make sure this instance depends on the cluster
  depends_on = [google_container_cluster.primary]
}

# Output the bastion host IP for easy access
output "bastion_ip" {
  description = "The public IP address of the bastion host"
  value       = google_compute_instance.bastion.network_interface[0].access_config[0].nat_ip
}

# Command to SSH into the bastion
output "ssh_command" {
  description = "Command to SSH into the bastion host"
  value       = "gcloud compute ssh gke-bastion --zone=${var.zone} --project=${var.project_id}"
}
