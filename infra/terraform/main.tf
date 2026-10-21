terraform {
  required_version = ">= 1.9"
  required_providers {
    google      = { source = "hashicorp/google", version = "~> 6.0" }
    google-beta = { source = "hashicorp/google-beta", version = "~> 6.0" }
  }
  # shortcut: local state (holds no secrets: no service-account keys exist); move to a GCS
  # backend if more than one person ever runs terraform.
}

provider "google" {
  project               = var.project_id
  region                = var.region
  user_project_override = true
  billing_project       = var.project_id
}

provider "google-beta" {
  project               = var.project_id
  region                = var.region
  user_project_override = true
  billing_project       = var.project_id
}

locals {
  apis = [
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "billingbudgets.googleapis.com",
    "serviceusage.googleapis.com",
  ]
  datasets = {
    raw   = "Flattened SEC parquet loaded from GCS (rebuilt daily by load jobs)."
    audit = "Write-audit-publish staging: every dbt model is built and tested here first."
    gold  = "Published, certified tables. Written only by `finfacts publish` after all tests pass."
    ops   = "Pipeline state and run log."
  }
}

resource "google_project_service" "apis" {
  for_each           = toset(local.apis)
  service            = each.value
  disable_on_destroy = false
}

# --- Storage: immutable bronze + flattened parquet -------------------------------------

resource "google_storage_bucket" "data" {
  name                        = "${var.project_id}-data"
  location                    = upper(var.region) # single US region: inside the GCS free tier
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  depends_on                  = [google_project_service.apis]
}

# --- BigQuery ---------------------------------------------------------------------------

resource "google_bigquery_dataset" "ds" {
  for_each                   = local.datasets
  dataset_id                 = each.key
  description                = each.value
  location                   = "US"
  delete_contents_on_destroy = false
  depends_on                 = [google_project_service.apis]
}

# Hard cap: BigQuery refuses queries once the project has scanned this much in a day.
resource "google_service_usage_consumer_quota_override" "bq_daily_query_bytes" {
  provider       = google-beta
  project        = var.project_id
  service        = "bigquery.googleapis.com"
  metric         = urlencode("bigquery.googleapis.com/quota/query/usage")
  limit          = urlencode("/d/project")
  override_value = tostring(var.bq_daily_query_limit_gb * 1024) # unit: MiB
  force          = true
  depends_on     = [google_project_service.apis]
}

# --- Pipeline identity: GitHub Actions via Workload Identity Federation (no keys) --------

resource "google_service_account" "pipeline" {
  account_id   = "finfacts-pipeline"
  display_name = "FinFacts pipeline (GitHub Actions)"
  depends_on   = [google_project_service.apis]
}

resource "google_project_iam_member" "pipeline_bq_jobs" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_bigquery_dataset_iam_member" "pipeline_bq_data" {
  for_each   = google_bigquery_dataset.ds
  dataset_id = each.value.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.pipeline.email}"
}

# Create + read only: without delete permission the pipeline cannot overwrite or remove
# an object, so bronze stays immutable by IAM, not just by convention.
resource "google_storage_bucket_iam_member" "pipeline_gcs" {
  for_each = toset(["roles/storage.objectCreator", "roles/storage.objectViewer"])
  bucket   = google_storage_bucket.data.name
  role     = each.value
  member   = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  depends_on                = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }
  # Only this repository's main branch can obtain credentials.
  attribute_condition = "assertion.repository == '${var.github_repo}' && assertion.ref == 'refs/heads/main'"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_impersonation" {
  service_account_id = google_service_account.pipeline.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}

# --- Cost guard: budget alerts (email to billing admins) ---------------------------------

data "google_project" "this" {}

resource "google_billing_budget" "monthly" {
  billing_account = var.billing_account
  display_name    = "FinFacts monthly budget"
  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }
  amount {
    specified_amount {
      currency_code = "EUR"
      units         = tostring(var.budget_eur)
    }
  }
  # Emails at EUR 5 (1/3 of 15) and EUR 15, actual spend; plus a forecast warning at EUR 15.
  threshold_rules { threshold_percent = 5 / var.budget_eur }
  threshold_rules { threshold_percent = 1.0 }
  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND"
  }
  depends_on = [google_project_service.apis]
}
