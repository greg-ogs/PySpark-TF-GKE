# Google Cloud provider configuration

provider "google" {
  project     = var.project_id
  # credentials = file("/terraform/.gcp/credentials.json") # Consider using GOOGLE_APPLICATION_CREDENTIALS env var instead
  region      = var.region
}
#
# provider "google-beta" {
#   project = var.project_id
#   region  = var.region
# }