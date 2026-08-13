# UI and Infrastructure Roadmap

## Purpose

This document defines the next two phases of the longitudinal
care-coordination agent:

1. Build a small, read-only Streamlit interface for demonstrating the
   evidence-backed brief workflow.
2. Later, create a CloudFormation template that can reproduce the
   infrastructure in a new environment.

The existing AWS environment remains the working learning environment. This
plan does **not** attempt to import, replace, or recreate its live resources.

All data remains synthetic Synthea data. The interface is a human-review aid;
it must not diagnose, prescribe, triage, or create autonomous tasks.

## Design decision

Build the UI before CloudFormation.

The UI makes the current end-to-end workflow visible and demonstrable. A
CloudFormation template is valuable afterward as a reproducibility and
infrastructure-as-code artifact, but retrofitting it onto manually created,
working resources would add avoidable risk and complexity.

## Phase 1: Streamlit demonstration UI

### Goal

Let a user select a synthetic patient, review the bounded source context, run
the brief generation workflow, and inspect the evidence supporting each
review item.

### User journey

```text
Choose patient
  → inspect timeline and latest note
  → inspect deterministic changes since prior note
  → generate an evidence-backed brief
  → inspect linked FHIR resource IDs and source details
```

### Initial screen scope

| Screen area | Content | Source |
| --- | --- | --- |
| Patient selection | Synthetic patient name, ID, birth date, gender | `patients` in RDS |
| Patient summary | Current note and prior note | `clinical_notes` in RDS |
| Longitudinal changes | New encounters, conditions, medication records, resolved conditions, and clinical events | `build_context.py` output from RDS |
| Generate brief | Explicit button; no automatic generation | `run_brief.py` workflow / Bedrock |
| Brief and evidence | Change summary, review items, confidence, and cited resource IDs | Generated brief plus RDS evidence records |

The initial UI is read-only except for the explicit **Generate brief** action.
It will not edit patient records, create tasks, send messages, or give medical
advice.

### Hosting and access

The Streamlit process runs on the existing `clinical-agent-host` EC2 instance.
It connects locally to the private RDS database using the same IAM role and
Secrets Manager retrieval approach as the Python scripts.

The browser accesses the UI only through an SSM port-forwarding session:

```text
Local browser → localhost:8501
  → SSM port-forwarding session
  → EC2 localhost:8501
  → private RDS / Bedrock / S3 as needed
```

This preserves the existing security design:

- No EC2 inbound security-group rule.
- No SSH key or SSH port.
- No public web endpoint.
- No load balancer, domain, or additional hosted application service.

### Application layout

```text
src/clinical-agent/
  app.py                 Streamlit user interface
  data_access.py         PostgreSQL read queries and patient selection
  build_context.py       Bounded evidence retrieval
  run_brief.py           Bedrock call, validation, and persistence
  load_fhir.py           S3 FHIR ingestion
```

`app.py` should call Python functions rather than shelling out to scripts. The
existing command-line scripts remain useful for testing and batch runs.

### Definition of done

- [ ] A Session Manager port-forward exposes the Streamlit page only on the
      developer's local machine.
- [ ] The page lists synthetic patients by readable name and ID.
- [ ] Selecting a patient shows current/prior notes and deterministic changes.
- [ ] The Generate brief action invokes the existing bounded-context workflow.
- [ ] The page renders the validated brief and its evidence IDs.
- [ ] No inbound EC2 security-group rule or public access was added.

## Phase 2: CloudFormation learning artifact

### Goal

Create an infrastructure-as-code template that can provision a **separate**
development environment with the same architectural shape.

It is not intended to adopt or replace the current manually created resources.

### Intended template scope

| Resource group | Planned CloudFormation responsibility |
| --- | --- |
| Network | VPC, one public subnet, one private subnet, internet gateway, route tables, and S3 Gateway endpoint |
| Security | EC2 and RDS security groups with PostgreSQL allowed only from the EC2 group |
| Compute | Amazon Linux EC2 instance and `clinical-agent-ec2-role` instance profile |
| Database | Single-AZ private RDS PostgreSQL instance, with a parameterized database name |
| Storage | Source and processed S3 buckets, with public access blocked and versioning on processed output |
| Permissions | Scoped role policy for buckets, the RDS credential secret, and the selected Bedrock model |

### Explicit non-goals

- No NAT Gateway.
- No Multi-AZ database.
- No public RDS access.
- No public UI deployment.
- No automatic Synthea data upload.
- No secret values embedded in the template.

### Parameters

The future template should request values such as:

- AWS Region (normally deployed in `us-east-1`)
- Resource-name prefix
- Allowed Bedrock model ID or model ARN
- DB name
- EC2 instance type
- Existing key/secret references only when required

### Definition of done

- [ ] `aws cloudformation validate-template` succeeds.
- [ ] The stack deploys to a new, clearly named learning environment.
- [ ] EC2 is manageable through Session Manager without SSH.
- [ ] EC2 can access only its scoped S3 buckets, the specific database secret,
      and the selected Bedrock model.
- [ ] RDS is private and reachable only from the stack's EC2 security group.
- [ ] Deleting the test stack is reviewed carefully, with retained data
      resources handled intentionally.

## Recommended implementation order

1. Refactor the existing script logic into reusable Python functions where
   needed.
2. Build and test the Streamlit UI locally on EC2 through SSM port forwarding.
3. Demonstrate multiple synthetic patient briefs, including a no-change case
   and an evidence-backed change case.
4. Document the final UI workflow in the README.
5. Create and validate a CloudFormation template for a separate environment.

## Cost and safety guardrails

- Keep EC2 and RDS sizes within the existing learning-project budget.
- Stop the EC2 instance when not actively using the UI; note that RDS and EBS
  still incur costs while provisioned.
- Maintain the no-NAT-Gateway design.
- Keep model calls user-triggered, bounded to one selected synthetic patient,
  and logged through `agent_runs`.
- Never store real clinical data, database passwords, or a real secret value
  in the repository or CloudFormation template.
