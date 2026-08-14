variable "name_prefix" {
  type = string
}

variable "raw_bucket_arn" {
  type = string
}

variable "processed_bucket_arn" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "bedrock_model_id" {
  type    = string
  default = "amazon.nova-micro-v1:0"
}