data "aws_partition" "current" {}

data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    effect = "Allow"

    actions = [
      "sts:AssumeRole"
    ]

    principals {
      type = "Service"

      identifiers = [
        "ec2.amazonaws.com"
      ]
    }
  }
}

resource "aws_iam_role" "ec2" {
  name               = "${var.name_prefix}-ec2-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
}

resource "aws_iam_instance_profile" "ec2" {
  name = "${var.name_prefix}-ec2-profile"
  role = aws_iam_role.ec2.name
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "application" {
  statement {
    sid    = "ListClinicalAgentBuckets"
    effect = "Allow"

    actions = [
      "s3:ListBucket"
    ]

    resources = [
      var.raw_bucket_arn,
      var.processed_bucket_arn
    ]
  }

  statement {
    sid    = "ReadSourceAndProcessedObjects"
    effect = "Allow"

    actions = [
      "s3:GetObject"
    ]

    resources = [
      "${var.raw_bucket_arn}/*",
      "${var.processed_bucket_arn}/*"
    ]
  }

  statement {
    sid    = "WriteProcessedBriefs"
    effect = "Allow"

    actions = [
      "s3:PutObject"
    ]

    resources = [
      "${var.processed_bucket_arn}/*"
    ]
  }

  statement {
    sid    = "InvokeConfiguredBedrockModel"
    effect = "Allow"

    actions = [
      "bedrock:InvokeModel"
    ]

    resources = [
      "arn:${data.aws_partition.current.partition}:bedrock:${var.aws_region}::foundation-model/${var.bedrock_model_id}"
    ]
  }
}

resource "aws_iam_role_policy" "application" {
  name   = "${var.name_prefix}-application-policy"
  role   = aws_iam_role.ec2.id
  policy = data.aws_iam_policy_document.application.json
}