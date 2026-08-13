# Technical Documentation

## Purpose

This project is a human-review, longitudinal care-coordination prototype using
synthetic Synthea FHIR data. It produces evidence-backed summaries of changes
between clinical records. It does not diagnose, prescribe, triage, or create
autonomous tasks.

See [the architecture diagram](architecture.md) for the component map.

## Components and responsibilities

| Component | AWS resource or code | Responsibility | Connection |
| --- | --- | --- | --- |
| Development | Local machine and VS Code | Generate Synthea data and author code | Uploads FHIR Bundles to S3 |
| Source storage | `clinical-agent-raw-notes-mz` S3 bucket | Stores Synthea FHIR JSON Bundles under `synthea/fhir/` | EC2 reads objects through the S3 Gateway endpoint |
| Compute | `clinical-agent-host` EC2 | Runs Python ingestion and agent scripts | Uses its IAM role to access AWS services |
| Database | `clinical-agent-db` RDS PostgreSQL | Stores patient history, notes, events, agent runs, briefs, and evidence | Private connection from EC2 over TLS on port 5432 |
| Secret storage | AWS Secrets Manager | Stores the RDS database username and password | EC2 retrieves it at runtime; no password is stored in source code |
| Model service | Amazon Bedrock / Amazon Nova Micro | Converts bounded patient context into a structured review brief | EC2 calls the Converse API with `bedrock:InvokeModel` |
| Processed storage | Processed S3 bucket | Stores validated JSON brief artifacts | `run_brief.py` writes the artifact after validation |
| Administration | Systems Manager Session Manager | Provides a shell to EC2 without SSH keys or inbound access | EC2 SSM agent connects outbound to Systems Manager |

## Network and access boundaries

- `clinical-agent-vpc` contains one public subnet and one private subnet.
- EC2 is in the public subnet, has no inbound security-group rules, and is
  administered only through Session Manager.
- RDS is in the private subnet with public access disabled.
- `clinical-agent-db-sg` permits inbound PostgreSQL (`5432`) only when the
  source is `clinical-agent-ec2-sg`.
- There is no NAT Gateway. The S3 Gateway VPC endpoint provides private,
  no-NAT access from the VPC to S3.
- Bedrock, Secrets Manager, and Systems Manager are accessed through the
  EC2 instance's outbound AWS connectivity.

## IAM role

The EC2 instance profile uses `clinical-agent-ec2-role`. Its least-privilege
policy should grant only:

- `s3:ListBucket`, `s3:GetObject`, and required `s3:PutObject` access for the
  specific source and processed buckets.
- `secretsmanager:GetSecretValue` for the specific RDS credentials secret.
- `bedrock:InvokeModel` for the selected model, currently
  `arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-micro-v1:0`.
- The AWS-managed `AmazonSSMManagedInstanceCore` policy for Session Manager.

## Application workflow

1. `src/clinical-agent/load_fhir.py` downloads a FHIR Bundle from S3, parses
   supported FHIR resources, decodes available clinical-note text, and loads
   structured records into PostgreSQL.
2. `src/clinical-agent/build_context.py` queries PostgreSQL for one patient,
   their current and prior notes, recent encounters, active conditions and
   medications, and relevant clinical events. It writes a bounded JSON
   context file.
3. `src/clinical-agent/run_brief.py` sends only that bounded context to
   Bedrock. It requires structured JSON output and verifies every cited FHIR
   resource ID is present in the supplied context.
4. After validation, `run_brief.py` writes the artifact to the processed S3
   bucket and persists agent-run metadata, the generated brief, and its
   evidence references in PostgreSQL.

## PostgreSQL data model

The core ingestion tables are:

- `patients`
- `encounters`
- `conditions`
- `medications`
- `observations`
- `clinical_notes`
- `clinical_events`
- `ingestion_files`

The care-coordination migration adds auditability tables:

- `agent_runs` records each Bedrock invocation and its status.
- `follow_up_briefs` stores the validated structured brief.
- `brief_evidence` links each cited resource to its source S3 object.

Schema definitions are in `database/schema.sql` and
`database/002_add_care_coordination_tables.sql`.

## Runtime configuration

The EC2 session must define configuration before running scripts. Values shown
here are identifiers or endpoints, never database passwords:

```sh
export AWS_REGION="us-east-1"
export S3_BUCKET="clinical-agent-raw-notes-mz"
export S3_PREFIX="synthea/fhir/"
export DB_HOST="clinical-agent-db.cq50kywksxu7.us-east-1.rds.amazonaws.com"
export DB_PORT="5432"
export DB_NAME="clinical_agent"
export DB_SECRET_ARN="arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:..."
export PROCESSED_BUCKET="clinical-agent-processed-YOUR_SUFFIX"
export BEDROCK_MODEL_ID="amazon.nova-micro-v1:0"
```

Do not commit a real secret ARN, passwords, generated patient context, or
brief artifacts to a public repository.

## Current verification status

The following connections have been verified:

- EC2 can list and download FHIR Bundles from S3.
- EC2 can retrieve RDS credentials from Secrets Manager.
- EC2 can connect to the private RDS PostgreSQL instance.
- The FHIR loader populated relational tables, including clinical notes and
  events.
- The context builder produced bounded patient context.
- EC2 successfully invoked Bedrock Nova Micro.
- The brief-generation workflow returned and validated a structured brief.
