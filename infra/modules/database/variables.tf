variable "name_prefix" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "database_security_group_id" {
  type = string
}

variable "database_name" {
  type = string
}

variable "database_username" {
  type = string
}

variable "database_engine_version" {
  type = string
}

variable "database_instance_class" {
  type = string
}