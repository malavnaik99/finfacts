output "bucket" {
  value = google_storage_bucket.data.name
}

output "pipeline_service_account" {
  value = google_service_account.pipeline.email
}

# Put these two values into the GitHub repo variables GCP_SA and GCP_WIF_PROVIDER.
output "workload_identity_provider" {
  value = google_iam_workload_identity_pool_provider.github.name
}
