output "vpc_id" {
  description = "ID of the Terraform-managed learning VPC."
  value       = module.network.vpc_id
}

output "public_subnet_id" {
  description = "ID of the public subnet."
  value       = module.network.public_subnet_id
}

output "private_subnet_id" {
  description = "ID of the private subnet."
  value       = module.network.private_subnet_id
}

output "availability_zone" {
  description = "Single Availability Zone used by this learning stack."
  value       = module.network.availability_zone
}

output "ec2_security_group_id" {
  description = "Security group ID for the future EC2 host."
  value       = module.security.ec2_security_group_id
}

output "database_security_group_id" {
  description = "Security group ID for the future RDS instance."
  value       = module.security.database_security_group_id
}

output "raw_bucket_name" {
  description = "Terraform-managed source FHIR bucket name."
  value       = module.storage.raw_bucket_name
}

output "processed_bucket_name" {
  description = "Terraform-managed processed-output bucket name."
  value       = module.storage.processed_bucket_name
}


output "ec2_instance_profile_name" {
  description = "Instance profile for the future EC2 host."
  value       = module.iam.instance_profile_name
}

output "private_subnet_ids" {
  description = "Private subnets used by the future RDS DB subnet group."
  value       = module.network.private_subnet_ids
}

output "database_endpoint" {
  description = "Private hostname for the Terraform-managed RDS database."
  value       = module.database.endpoint
}

output "database_port" {
  value = module.database.port
}

output "database_name" {
  value = module.database.database_name
}

output "database_secret_arn" {
  description = "Secrets Manager ARN containing the RDS master credentials."
  value       = module.database.master_user_secret_arn
}

output "ec2_instance_id" {
  description = "Instance ID for Session Manager connections."
  value       = module.compute.instance_id
}

output "ec2_private_ip" {
  value = module.compute.private_ip
}