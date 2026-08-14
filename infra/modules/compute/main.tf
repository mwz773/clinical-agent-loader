data "aws_ssm_parameter" "amazon_linux_2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_instance" "this" {
  ami           = data.aws_ssm_parameter.amazon_linux_2023_ami.value
  instance_type = var.instance_type

  subnet_id                   = var.public_subnet_id
  vpc_security_group_ids      = [var.ec2_security_group_id]
  iam_instance_profile        = var.instance_profile_name
  associate_public_ip_address = true

  metadata_options {
    http_tokens = "required"
  }

  root_block_device {
    volume_size           = 8
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  tags = {
    Name = "${var.name_prefix}-host"
  }
}