resource "aws_security_group" "ec2" {
  name        = "${var.name_prefix}-ec2-sg"
  description = "EC2 security group: no inbound access."
  vpc_id      = var.vpc_id

  egress {
    description = "Allow outbound HTTPS and other required service traffic."
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-ec2-sg"
  }
}

resource "aws_security_group" "database" {
  name        = "${var.name_prefix}-db-sg"
  description = "PostgreSQL access only from the EC2 security group."
  vpc_id      = var.vpc_id

  ingress {
    description     = "PostgreSQL from Terraform-managed EC2 only."
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ec2.id]
  }

  egress {
    description = "Allow outbound traffic required by the managed database."
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-db-sg"
  }
}