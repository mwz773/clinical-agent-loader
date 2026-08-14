variable "aws_region" {
  description = "AWS Region for Terraform-managed resources."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short prefix used in Terraform resource names."
  type        = string
  default     = "clinical-agent"
}

variable "environment" {
  description = "Separate Terraform learning environment name."
  type        = string
  default     = "tf-dev"
}

variable "vpc_cidr" {
  description = "CIDR block for the separate Terraform learning VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for the single public subnet."
  type        = string
  default     = "10.20.1.0/24"
}

variable "private_subnet_cidr" {
  description = "CIDR block for the single private subnet."
  type        = string
  default     = "10.20.2.0/24"
}
