infra/
  versions.tf       Terraform and AWS provider requirements
  provider.tf       AWS region and default tags
  variables.tf      Project prefix, environment, CIDR, model ARN, etc.
  main.tf           Composes modules/resources
  outputs.tf        VPC ID, RDS endpoint, bucket names, instance ID
  terraform.tfvars.example

  modules/
    network/        VPC, subnets, route tables, IGW, S3 endpoint
    security/       EC2/RDS security groups
    storage/        Source and processed buckets
    iam/            EC2 role and scoped policies
    database/       Private single-AZ RDS PostgreSQL
    compute/        EC2 instance and instance profile




 | Module | Resources it manages |
|---|---|
| `network` | VPC, public/private subnets, route tables, internet gateway, S3 Gateway endpoint |
| `security` | EC2 and RDS security groups; PostgreSQL access only from the EC2 security group |
| `storage` | Source FHIR and processed-brief S3 buckets, public-access blocks, encryption, processed-bucket versioning |
| `iam` | EC2 role/instance profile and scoped permissions for S3, Secrets Manager, Bedrock, and SSM |
| `database` | Private single-AZ RDS PostgreSQL instance, subnet group, managed master password in Secrets Manager |
| `compute` | EC2 instance, Amazon Linux AMI lookup, instance profile, security group, and EBS settings |
| `observability` *(later)* | CloudWatch log groups, billing alarm, and chatbot/brief evaluation metrics |
| `app` *(later, optional)* | A deployment mechanism for the Streamlit application—likely still EC2-based for this project |


The root infra/main.tf connects them:
network
  → security
    → database
    → compute
      → application