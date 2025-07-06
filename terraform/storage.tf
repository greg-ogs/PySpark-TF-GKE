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
