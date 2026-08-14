locals {
  resource_prefix = "${var.project_name}-${var.environment}"
}

module "network" {
  source = "./modules/network"

  name_prefix                   = local.resource_prefix
  vpc_cidr                      = var.vpc_cidr
  public_subnet_cidr            = var.public_subnet_cidr
  private_subnet_cidr           = var.private_subnet_cidr
  private_subnet_secondary_cidr = var.private_subnet_secondary_cidr
}

module "security" {
  source = "./modules/security"

  name_prefix = local.resource_prefix
  vpc_id      = module.network.vpc_id
}


module "storage" {
  source = "./modules/storage"

  name_prefix = local.resource_prefix
}

module "iam" {
  source = "./modules/iam"

  name_prefix          = local.resource_prefix
  raw_bucket_arn       = module.storage.raw_bucket_arn
  processed_bucket_arn = module.storage.processed_bucket_arn
  aws_region           = var.aws_region
  bedrock_model_id     = var.bedrock_model_id
}