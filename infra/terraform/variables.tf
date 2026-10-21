variable "project_id" {
  type        = string
  description = "GCP project id."
}

variable "billing_account" {
  type        = string
  description = "Billing account id (XXXXXX-XXXXXX-XXXXXX) for the budget alert."
}

variable "region" {
  type        = string
  default     = "us-central1"
  description = "GCS bucket region. US regions are inside the GCS free tier."
}

variable "github_repo" {
  type        = string
  default     = "malavnaik99/finfacts"
  description = "owner/repo allowed to impersonate the pipeline service account."
}

variable "budget_eur" {
  type        = number
  default     = 15
  description = "Monthly budget; alerts fire at EUR 5 and at this amount."
}

variable "bq_daily_query_limit_gb" {
  type        = number
  default     = 50
  description = "Hard daily cap on bytes BigQuery may scan for this project."
}
