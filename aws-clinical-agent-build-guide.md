# Build Guide: Longitudinal Care-Coordination Agent (Console-First)

Companion to `aws-clinical-agent-design-doc.md`. You've already done account hygiene (MFA, admin user, budget, credits) — this picks up from there.

**How to use this doc:** work top to bottom. Each phase has a "Definition of Done" — don't move to the next phase until you can check every box. Region: pick **one** region for everything (`us-east-1` is a safe default — widest Bedrock model availability) and stay in it throughout; resources in different regions can't talk to each other without extra networking you don't need yet.

---

## Phase 1 — Networking (VPC)

**Console path:** VPC → "Create VPC" → choose **"VPC and more"** (the wizard), not the bare VPC option — it creates subnets, route tables, and an internet gateway together and is much less error-prone for a first pass.

Settings:
- Name: `clinical-agent-vpc`
- IPv4 CIDR: `10.0.0.0/16`
- Number of AZs: **1** (you don't need multi-AZ yet)
- Public subnets: **1**
- Private subnets: **1**
- NAT gateways: **None** ← important, this is the ~$33/month item you're skipping
- VPC endpoints: select **S3 Gateway** if the wizard offers it; if not, add it manually afterward (VPC → Endpoints → Create endpoint → service `com.amazonaws.<region>.s3`, type Gateway, associate it with your private route table)

After creation, go to **Security Groups** and create two:
- `clinical-agent-ec2-sg`: **no inbound rules at all**, default outbound (all traffic allowed) — SSM doesn't need inbound.
- `clinical-agent-db-sg`: inbound rule for PostgreSQL (port 5432), source = `clinical-agent-ec2-sg` (reference the security group, not an IP range).

### Definition of Done
- [ X] VPC with one public and one private subnet exists
- [ X] No NAT Gateway was created (check VPC → NAT Gateways — should be empty)
- [ X] S3 Gateway endpoint attached to the private subnet's route table
- [ X] Two security groups created as above

---

## Phase 2 — S3 Buckets

Console path: S3 → Create bucket. Create three (bucket names must be globally unique, so suffix with your initials or a random string):

- `clinical-agent-raw-notes-<suffix>` — source Synthea FHIR Bundles, including embedded notes
- `clinical-agent-processed-<suffix>` — evidence-backed care-coordination briefs
- `clinical-agent-logs-<suffix>` (optional — CloudWatch covers most of this, skip if you want fewer resources)

Settings for each: default encryption (SSE-S3, already on by default), block all public access (leave the default "on"). Enable **versioning** on the `processed` bucket only (Properties tab → Versioning → Enable).

### Definition of Done
- [X ] Two or three buckets exist, all with public access blocked
- [ X] Versioning enabled on the processed-output bucket

---

## Phase 3 — IAM Role for EC2

Do this before launching EC2 so the role exists to attach at launch time.

Console path: IAM → Roles → Create role → Trusted entity: **AWS service** → Use case: **EC2**.

Attach these policies:
- `AmazonSSMManagedInstanceCore` (AWS managed — enables Session Manager access, no SSH needed)

Then create a **custom inline policy** (don't use `s3:*` or `*` resources) scoped to:
- `s3:GetObject`, `s3:PutObject`, `s3:ListBucket` on your three bucket ARNs (and `/*` for object-level actions)
- `secretsmanager:GetSecretValue` on the specific secret ARN (you'll create the secret in Phase 5 — you can add this statement now with a placeholder and edit it after, or come back to this step then)
- `bedrock:InvokeModel` on the specific model ARN(s) you plan to use (e.g., `arn:aws:bedrock:<region>::foundation-model/anthropic.claude-3-5-haiku-*`)

Name the role `clinical-agent-ec2-role`.

### Definition of Done
- [ X ] Role exists with SSM managed policy + your scoped custom policy
- [ ] No policy uses `"Resource": "*"` except where AWS requires it (SSM's managed policy does — that's fine, it's AWS's policy, not yours)

---

## Phase 4 — RDS PostgreSQL

Console path: RDS → Create database.

Settings:
- Engine: PostgreSQL
- Templates: **Free tier**
- DB instance identifier: `clinical-agent-db`
- Master username/password: let RDS auto-generate and manage via Secrets Manager — there's a checkbox **"Manage master user password in Secrets Manager"** during creation. Check it. This gets you a real Secrets Manager secret for free as a side effect of DB creation, which covers most of Phase 5 automatically.
- Instance class: `db.t3.micro`
- Storage: 20GB, gp2 (free-tier default)
- Connectivity: choose your VPC, **private subnet only**, "Public access: No"
- VPC security group: choose the existing `clinical-agent-db-sg`, remove the default one it tries to create
- Multi-AZ: **No**
- Initial database name: `clinical_agent`

Creation takes several minutes. Once available, note the endpoint hostname from the DB's console page — you'll need it in the agent's connection config (retrieved alongside the Secrets Manager credentials, not hardcoded).

### Definition of Done
- [X ] DB status is "Available"
- [ ] Public access is "No"
- [X ] Multi-AZ is "No" — confirm this explicitly, it's the easiest box to accidentally check
- [ ] A Secrets Manager secret now exists containing the DB credentials

---

## Phase 5 — Secrets Manager (confirm/finish)

If you used the auto-managed-password checkbox in Phase 4, go to Secrets Manager and find the secret (named something like `rds!db-...`). Note its ARN.

Go back to the IAM role from Phase 3 and update the `secretsmanager:GetSecretValue` statement's `Resource` to this real ARN.

If you'd rather create the secret manually instead (more explicit learning rep): Secrets Manager → Store a new secret → "Credentials for RDS database" → select your DB instance → let it associate automatically → name it `clinical-agent/db-credentials`.

### Definition of Done
- [ X ] Secret exists and its ARN is in the EC2 role's IAM policy (not a wildcard)
- [ X ] You can view the secret value in the console and it matches your DB

---

## Phase 6 — EC2 Instance

Console path: EC2 → Launch instance.

Settings:
- Name: `clinical-agent-host`
- AMI: Amazon Linux 2023
- Instance type: `t3.micro`
- Key pair: **"Proceed without a key pair"** — you're using SSM, no SSH key needed
- Network: your VPC, **public subnet**, auto-assign public IP: **Enable**
- Security group: select the existing `clinical-agent-ec2-sg` (no inbound rules)
- Advanced details → IAM instance profile: `clinical-agent-ec2-role`
- Storage: default 8GB gp3 is fine (well under free-tier 30GB)

Launch it. After a minute or two, go to **Systems Manager → Session Manager → Start session**, select the instance — you should get a shell with no SSH key involved. If it doesn't appear as a valid target, wait another minute (the SSM agent needs to check in) or verify the IAM role attached correctly.

Once connected, install what you need for the agent (Python 3, pip, boto3, psycopg2, git):
```bash
sudo dnf install -y python3 python3-pip git
pip3 install boto3 psycopg2-binary
```

### Definition of Done
- [ X] Instance is running
- [ X] You can open a Session Manager shell with no SSH key
- [X ] `python3 -c "import boto3; print(boto3.client('sts').get_caller_identity())"` returns your account/role identity from inside the instance (confirms the IAM role is attached and working)

---

## Phase 7 — Synthea Data

Generate synthetic patients locally (on your laptop, not EC2 — Synthea is a Java tool and easier to run where you can inspect output before uploading):

```bash
git clone https://github.com/synthetichealth/synthea.git
cd synthea
./run_synthea -p 200 Illinois   # generates ~200 synthetic patients
```

The project uses **FHIR Bundles as the source of truth**, not CSV. With the default US Core FHIR export enabled, Synthea embeds plain-text notes in `DiagnosticReport.presentedForm[].data` and exports the related structured timeline in the same Bundle. The standalone note export is optional and uses `exporter.clinical_note.export=true` (not `exporter.notes.enabled`).

- Upload the `output/fhir/` directory to the source bucket. Preserve the `fhir/` prefix so the loader can retain the original S3 key as lineage metadata:
```bash
aws s3 cp output/fhir/ s3://clinical-agent-raw-notes-<suffix>/synthea/fhir/ --recursive
```

### Definition of Done
- [ ] One FHIR Bundle is loaded into patient, encounter, condition, medication, observation, and clinical-note tables
- [X ] Source FHIR Bundles are visible in the S3 source bucket
- [ ] The decoded clinical note and its patient timeline can be joined by patient ID

---

## Phase 8 — Bedrock Access

Console path: Bedrock → Model access → request access to **Anthropic Claude 3.5 Haiku** (or the current Haiku-family model available in your region). Approval is usually near-instant for on-demand access.

Sanity check from the EC2 instance:
```python
import boto3, json
client = boto3.client("bedrock-runtime", region_name="us-east-1")
resp = client.invoke_model(
    modelId="anthropic.claude-3-5-haiku-20241022-v1:0",
    body=json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "Say hello in one sentence."}]
    })
)
print(json.loads(resp["body"].read()))
```

### Definition of Done
- [ ] Model access shows "Access granted" in the console
- [ ] The test call above returns a response with no IAM/permission errors (this confirms Phase 3's Bedrock policy statement is correct)

---

## Phase 9 — The Agent Pipeline

This is the actual application code — worth its own focused session rather than cramming it into this infra checklist. The agent is a **human-review care-coordination tool**, not a diagnostic or autonomous workflow engine. For each selected note it should:

1. Generate a `run_id` (UUID) at the start.
2. Look up the decoded note and the patient ID from RDS; retain the source S3 key for lineage.
3. Retrieve a bounded context: the prior note plus relevant recent encounters, conditions, medications, observations, and clinical events. Do not send the whole chart by default.
4. Build a prompt instructing the model to return **strict JSON**: `{"change_summary": [...], "review_items": [{"category": "...", "summary": "...", "evidence_resource_ids": ["..."], "confidence": "low|medium|high"}], "human_review_required": true}`.
5. Call Bedrock and validate both the JSON structure and that every evidence ID belongs to the retrieved context. Reject or flag unsupported claims.
6. Write the resulting brief to the `processed` S3 bucket, keyed by `run_id`.
7. Insert rows into `agent_runs`, `follow_up_briefs`, and `brief_evidence`, including model token counts and measured latency.
8. Emit a structured JSON log line with the same `run_id`.

Come back to this checklist once you're ready to build it — happy to help write this code when you get there.

### Definition of Done
- [ ] Running the script against one note produces an `agent_runs` row, a `follow_up_briefs` row, evidence rows, and a processed JSON file sharing the same `run_id`
- [ ] Every generated review item cites one or more retrieved FHIR resource IDs
- [ ] You can re-run it against the full batch without manual intervention

---

## Phase 10 — Observability

Console path:
- CloudWatch → Log groups → create `/clinical-agent/app` (or let your logging library create it automatically via `boto3`'s `watchtower` or the CloudWatch agent).
- CloudWatch → Alarms → create one on a custom metric you emit (e.g., error count) in addition to the billing alarm you already have.
- (Optional) enable **X-Ray** by installing the X-Ray SDK for Python (`pip3 install aws-xray-sdk`) and wrapping the four pipeline steps as subsegments — gives you a trace map for free (100k traces/month always-free).

### Definition of Done
- [ ] Agent log lines are visible in CloudWatch Logs, filterable by `run_id`
- [ ] At least one non-billing alarm exists
- [ ] (Optional) X-Ray trace map shows the four pipeline steps for at least one run

---

## Phase 11 — Aurora Side-Quest (Terraform)

This is the one phase where I'd switch tools, specifically because reliable teardown matters more than console familiarity here. A minimal Terraform config:

```hcl
resource "aws_rds_cluster" "aurora" {
  cluster_identifier     = "clinical-agent-aurora"
  engine                 = "aurora-postgresql"
  engine_mode            = "provisioned"
  master_username        = "postgres"
  manage_master_user_password = true
  db_subnet_group_name   = aws_db_subnet_group.private.name
  vpc_security_group_ids = [data.aws_security_group.db.id]
  serverlessv2_scaling_configuration {
    min_capacity = 0.5
    max_capacity = 1
  }
  skip_final_snapshot = true
}

resource "aws_rds_cluster_instance" "aurora_instance" {
  cluster_identifier = aws_rds_cluster.aurora.id
  instance_class      = "db.serverless"
  engine              = aws_rds_cluster.aurora.engine
}
```
(You'll need to add `data`/`resource` blocks referencing your existing VPC/subnet/security group — ask if you want the full working config with those wired in.)

Explore it, connect to it, confirm it behaves like your RDS instance conceptually, then:
```bash
terraform destroy
```
one command, no console hunting, cluster gone.

### Definition of Done
- [ ] Aurora cluster created and reachable
- [ ] `terraform destroy` confirmed the cluster and instance are gone (check the console to be sure)

---

## Phase 12 — Teardown Runbook (keep this updated as you build)

When you're done working for the day/week, or done with the project entirely:

1. Stop (don't necessarily terminate, if you want to resume) the EC2 instance.
2. If done for good: terminate EC2, delete the RDS instance (uncheck "create final snapshot" if you don't need one — snapshots cost storage too), delete the Secrets Manager secret (accept the recovery window), empty and delete the S3 buckets, delete the VPC (this cleans up subnets/route tables/security groups/endpoint together).
3. Double check: VPC console → NAT Gateways (should be none, but confirm), Elastic IPs (release any unattached ones), EBS Volumes (delete any orphaned ones not attached to a terminated instance).
4. Check Cost Explorer a day later to confirm charges dropped to near-zero.

---

## Suggested order of attack for your first session

Phases 1 → 2 → 3 → 4 → 5 → 6, in that order, since each one's output (VPC, buckets, role, DB, secret) is a prerequisite for the next. That's realistically a half-day of console work the first time through, since almost everything is unfamiliar. Phases 7–10 (data, Bedrock, the actual agent code, observability) are a good second session. Phase 11 (Aurora/Terraform) is best done as its own short, focused session near the end so you don't leave it running by accident while attention is elsewhere.
