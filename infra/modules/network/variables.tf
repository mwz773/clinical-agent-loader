variable "name_prefix" {
  description = "Prefix used for resource names and Name tags."
  type        = string
}

variable "vpc_cidr" {
  description = "IPv4 CIDR block for the VPC."
  type        = string
}

variable "public_subnet_cidr" {
  description = "IPv4 CIDR block for the public subnet."
  type        = string
}

variable "private_subnet_cidr" {
  description = "IPv4 CIDR block for the private subnet."
  type        = string
}

variable "private_subnet_secondary_cidr" {
  description = "IPv4 CIDR block for the second private subnet."
  type        = string
}