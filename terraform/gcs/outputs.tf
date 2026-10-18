output "dvc_remote_url" {
  value = "gs://${google_storage_bucket.dvc_remote.name}"
}

output "dvc_reader_email" {
  value = google_service_account.dvc_reader.email
}
