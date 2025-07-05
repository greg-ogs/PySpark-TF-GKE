# Google Cloud Storage bucket for health data
resource "google_storage_bucket" "datasets_bucket" {
  name          = "${var.project_id}-datasets"
  location      = var.region
  force_destroy = true  # Allow terraform to destroy the bucket even if it contains objects

  # Optional: Configure versioning, lifecycle rules, etc. as needed
  versioning {
    enabled = true
  }

  # Optional: Set uniform bucket-level access
  uniform_bucket_level_access = true
}

# Add storage.objects.viewer role to the GKE service account
resource "google_storage_bucket_iam_member" "gke_sa_storage_viewer" {
  bucket = google_storage_bucket.datasets_bucket.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.gke_sa.email}"
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

# Output the bucket name for reference
output "datasets_bucket_name" {
  description = "The name of the GCS bucket for health data"
  value       = google_storage_bucket.datasets_bucket.name
}

# Output the bucket URL for reference
output "datasets_bucket_url" {
  description = "The URL of the GCS bucket for health data"
  value       = "gs://${google_storage_bucket.datasets_bucket.name}"
}
