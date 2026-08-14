resource "aws_db_subnet_group" "this" {
  name        = "${var.name_prefix}-db-subnets"
  description = "Private subnets for the clinical-agent RDS instance"
  subnet_ids  = var.private_subnet_ids

  tags = {
    Name = "${var.name_prefix}-db-subnets"
  }
}

resource "aws_db_instance" "this" {
  identifier = "${var.name_prefix}-db"

  engine         = "postgres"
  engine_version = var.database_engine_version
  instance_class = var.database_instance_class

  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = var.database_name
  username = var.database_username

  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.database_security_group_id]

  publicly_accessible     = false
  multi_az                = false
  backup_retention_period = 1
  apply_immediately       = true

  deletion_protection = false
  skip_final_snapshot = true

  tags = {
    Name = "${var.name_prefix}-db"
  }
}