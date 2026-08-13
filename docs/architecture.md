# Architecture Diagram

This diagram represents the currently implemented learning-project architecture
in `us-east-1`. All clinical data is synthetic Synthea data; no real patient
data is used.

```mermaid
flowchart TB
    DEV[Local development machine\nVS Code + Synthea]

    subgraph AWS[AWS account — us-east-1]
        S3RAW[(S3: clinical-agent-raw-notes-mz\nsynthea/fhir/*.json)]
        S3PROCESSED[(S3 processed-output bucket\nvalidated brief JSON)]
        SECRETS[Secrets Manager\nRDS username and password]
        BEDROCK[Amazon Bedrock\nAmazon Nova Micro]
        SSM_SERVICE[AWS Systems Manager]
        IAM[IAM: clinical-agent-ec2-role]

        subgraph VPC[clinical-agent-vpc]
            IGW[Internet Gateway]
            S3EP[S3 Gateway VPC endpoint]

            subgraph PUBLIC[Public subnet]
                EC2[EC2: clinical-agent-host\nAmazon Linux 2023]
                SSM[SSM Agent / Session Manager]
                LOADER[load_fhir.py]
                CONTEXT[build_context.py]
                BRIEF[run_brief.py]
            end

            subgraph PRIVATE[Private subnet]
                RDS[(RDS PostgreSQL: clinical-agent-db\nclinical_agent database)]
            end

            ECSG[clinical-agent-ec2-sg\nNo inbound rules]
            DBSG[clinical-agent-db-sg\nPostgreSQL 5432 from EC2 SG only]
        end
    end

    DEV -->|Upload Synthea FHIR Bundles| S3RAW
    SSM_SERVICE -->|outbound managed session| SSM
    IAM -->|instance profile| EC2
    IGW --> EC2

    EC2 --> S3EP -->|GetObject / ListBucket| S3RAW
    LOADER -->|parse FHIR and write relational records| RDS

    EC2 -->|GetSecretValue| SECRETS
    EC2 -->|TLS PostgreSQL, port 5432| RDS
    ECSG -->|allowed source security group| DBSG

    CONTEXT -->|retrieve bounded patient evidence| RDS
    CONTEXT -->|context JSON| BRIEF
    BRIEF -->|Converse API / InvokeModel| BEDROCK
    BRIEF -->|write validated brief JSON| S3PROCESSED
    BRIEF -->|persist runs, briefs, evidence| RDS
```

## Runtime data flow

```text
Synthea FHIR Bundle
  → S3 source bucket
  → EC2 loader
  → RDS PostgreSQL
  → context builder (one patient, one current note, selected prior evidence)
  → Bedrock model
  → evidence-validated care-coordination brief
  → processed S3 bucket + RDS audit tables
```

The EC2 instance has no inbound security-group rules. Administration occurs
through Systems Manager Session Manager, rather than SSH. The RDS instance is
private and accepts PostgreSQL connections only from the EC2 security group.
