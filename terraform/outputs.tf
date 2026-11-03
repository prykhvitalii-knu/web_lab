output "api_base_url" {
  description = "HTTPS base URL for the FastAPI application."
  value = (
    var.enable_custom_domains
    ? "https://${local.api_domain}"
    : aws_apigatewayv2_api.api.api_endpoint
  )
}

output "website_url" {
  description = "HTTPS CloudFront URL for the static landing page."
  value = (
    var.enable_custom_domains
    ? "https://${var.website_domain}"
    : "https://${aws_cloudfront_distribution.website.domain_name}"
  )
}

output "website_dns_target" {
  description = "CloudFront target for the website CNAME record in Cloudflare."
  value       = aws_cloudfront_distribution.website.domain_name
}

output "api_dns_target" {
  description = "API Gateway target for the API CNAME record in Cloudflare."
  value = (
    var.enable_custom_domains
    ? aws_apigatewayv2_domain_name.api[0].domain_name_configuration[0].target_domain_name
    : null
  )
}

output "website_certificate_dns_validation" {
  description = "Create these DNS CNAME records in Cloudflare to validate the website certificate."
  value = [
    for option in aws_acm_certificate.website.domain_validation_options : {
      name  = option.resource_record_name
      type  = option.resource_record_type
      value = option.resource_record_value
    }
  ]
}

output "api_certificate_dns_validation" {
  description = "Create these DNS CNAME records in Cloudflare to validate the API certificate."
  value = [
    for option in aws_acm_certificate.api.domain_validation_options : {
      name  = option.resource_record_name
      type  = option.resource_record_type
      value = option.resource_record_value
    }
  ]
}

output "database_endpoint" {
  description = "Private RDS endpoint hostname used by the deployment secret writer."
  value       = aws_db_instance.database.address
}

output "database_port" {
  value = aws_db_instance.database.port
}

output "database_name" {
  value = aws_db_instance.database.db_name
}

output "database_master_secret_arn" {
  description = "RDS-managed master credential secret; the password is not stored in Terraform state."
  value       = aws_db_instance.database.master_user_secret[0].secret_arn
}

output "website_bucket" {
  value = aws_s3_bucket.website.id
}

output "uploads_bucket" {
  value = aws_s3_bucket.uploads.id
}

output "app_secret_arn" {
  description = "Secrets Manager ARN; the secret value is not stored in Terraform state."
  value       = aws_secretsmanager_secret.app_config.arn
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.website.id
}

output "github_actions_role_arn" {
  description = "IAM role ARN to set as the GitHub secret AWS_ROLE_ARN."
  value       = aws_iam_role.github_actions.arn
}
