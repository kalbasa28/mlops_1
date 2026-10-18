output "dvc_remote_url" {
  value = "gs://${google_storage_bucket.dvc_remote.name}"
}
