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
