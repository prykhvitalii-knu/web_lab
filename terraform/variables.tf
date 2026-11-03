variable "aws_region" {
  description = "AWS region for the application."
  type        = string
}

variable "environment" {
  description = "Short environment label used in resource names."
  type        = string
  default     = "demo"

  validation {
    condition     = can(regex("^[a-z0-9-]{2,12}$", var.environment))
    error_message = "environment must contain 2-12 lowercase letters, digits, or hyphens."
  }
}

variable "github_repository" {
  description = "GitHub owner/repository allowed to assume the deployment role."
  type        = string
  default     = "prykhvitalii-knu/web_lab"
}

variable "github_oidc_provider_arn" {
  description = "OIDC provider ARN created by terraform/bootstrap."
  type        = string
}

variable "terraform_state_bucket" {
  description = "Encrypted S3 bucket created by terraform/bootstrap for remote state."
  type        = string
}

variable "website_domain" {
  description = "Custom hostname for the static website, managed in Cloudflare DNS."
  type        = string
  default     = "akatosh.local-domain.party"
}

variable "enable_custom_domains" {
  description = "Attach the ACM-validated website and API hostnames after DNS validation."
  type        = bool
  default     = false
}
