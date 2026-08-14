variable "name_prefix" {
  description = "Prefix used for security-group names and tags."
  type        = string
}

variable "vpc_id" {
  description = "VPC where security groups are created."
  type        = string
}