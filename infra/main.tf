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
  db_secret_arn        = module.database.master_user_secret_arn
}

module "compute" {
  source = "./modules/compute"

  name_prefix           = local.resource_prefix
  public_subnet_id      = module.network.public_subnet_id
  ec2_security_group_id = module.security.ec2_security_group_id
  instance_profile_name = module.iam.instance_profile_name
  instance_type         = var.ec2_instance_type
}

module "database" {
  source = "./modules/database"

  name_prefix                = local.resource_prefix
  private_subnet_ids         = module.network.private_subnet_ids
  database_security_group_id = module.security.database_security_group_id

  database_name           = var.database_name
  database_username       = var.database_username
  database_engine_version = var.database_engine_version
  database_instance_class = var.database_instance_class
}

