# Google Cloud provider configuration

provider "google" {
  project     = var.project_id
  credentials = file("/terraform/.gcp/credentials.json")
  region      = "us-central1"
}
#
# provider "google-beta" {
#   project = var.project_id
#   region  = var.region
# }