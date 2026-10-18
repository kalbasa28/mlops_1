provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_project_service" "storage" {
  service            = "storage.googleapis.com"
  disable_on_destroy = false
}

resource "google_storage_bucket" "dvc_remote" {
  name                        = "${var.project_id}-dvc"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  depends_on = [google_project_service.storage]
}

resource "google_project_service" "iam" {
  service            = "iam.googleapis.com"
  disable_on_destroy = false
}

resource "google_service_account" "dvc_reader" {
  account_id   = "dvc-reader"
  display_name = "DVC remote read-only (training Job in kind)"

  depends_on = [google_project_service.iam]
}

resource "google_storage_bucket_iam_member" "dvc_reader_can_read" {
  bucket = google_storage_bucket.dvc_remote.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.dvc_reader.email}"
}
