# Portfolio-Ready Prototype Plan

## Current deployment

The project is already deployed as a private AWS prototype:

```text
Streamlit on EC2 -> private RDS PostgreSQL
                 -> S3 source and processed-output buckets
                 -> Bedrock through a least-privilege IAM role
```

The UI is accessed through AWS Systems Manager port forwarding rather than a public inbound port. This is the appropriate demonstration setup for a healthcare-adjacent learning project using synthetic data.

Do not make the Streamlit application public yet. A public deployment would require additional work such as authentication, HTTPS, access controls, and a more complete security review.

## Finished prototype scope

The final prototype should demonstrate the following end-to-end workflow:

- Load synthetic Synthea FHIR bundles from S3 into a normalized PostgreSQL database on RDS.
- Build a bounded, multi-year patient-history context from the relational data.
- Generate a Bedrock care-coordination brief for human review, with evidence resource IDs.
- Let a clinician ask bounded questions about documented patient history.
- Refuse diagnosis, prescribing, triage, treatment advice, and unrelated requests.
- Inspect cited evidence records in the Streamlit interface.
- Provision the AWS learning environment with modular Terraform.

Avoid adding major features unless they strengthen this specific story.

## Final polish checklist

### Product and safety

- [ ] Confirm the Streamlit patient selector, timeline, brief generation, evidence inspector, and chat all work in the Terraform environment.
- [ ] Confirm a history question returns only evidence from the selected patient and configured history window.
- [ ] Confirm prescribing, diagnosis, treatment, and triage questions receive an appropriate refusal.
- [ ] Keep the synthetic-data and human-review disclaimers visible in the UI and README.

### Evaluation and monitoring

- [ ] Create a small, repeatable evaluation set of 10-15 questions.
- [ ] Include factual history retrieval, evidence citations, out-of-scope questions, medical-advice refusals, and insufficient-evidence cases.
- [ ] Record the expected response type and, where applicable, expected evidence resource IDs.
- [ ] Add CloudWatch logging and a lightweight evaluation-results record before claiming CloudWatch evaluation monitoring on a resume.

### Code and infrastructure

- [ ] Commit the Streamlit duplicate-evidence-button-key fix.
- [ ] Commit the `verify_connection.py` update that reads host, port, and database name from environment variables.
- [ ] Keep Terraform state, `.tfvars`, `.env.sh`, and secrets out of Git.
- [ ] Run `terraform fmt -recursive`, `terraform validate`, and `terraform plan` before the final infrastructure commit.
- [ ] Retire the original manually created AWS resources after confirming the Terraform stack is fully functional.

### GitHub presentation

- [ ] Add a one-sentence problem statement to the README.
- [ ] Add the architecture diagram and a concise data-flow explanation.
- [ ] Add screenshots of the timeline, generated brief, evidence inspector, and a safe refusal.
- [ ] Link a short demo video from the README.
- [ ] Document the project limitations: synthetic data only, no clinical decision-making, and human review required.

## Demo video plan

Record a two-to-three minute screen recording using the private SSM-forwarded deployment. The video should show the working system, not implementation details alone.

| Time | Demonstration |
| --- | --- |
| 0:00 | State the problem: longitudinal patient records are difficult to review quickly. |
| 0:20 | Show the architecture: S3 to EC2 to RDS to bounded context to Bedrock to Streamlit. |
| 0:45 | Select a synthetic patient and build a five-year context. |
| 1:15 | Generate a care-coordination brief and open its evidence records. |
| 1:50 | Ask a factual patient-history question and show cited evidence. |
| 2:10 | Ask for a prescription or diagnosis and show the refusal boundary. |
| 2:30 | Briefly show the Terraform modules and private, no-inbound AWS design. |
| 2:50 | Close with limitations: synthetic data and human review required. |

## Suggested portfolio assets

Use these assets alongside GitHub rather than operating a public clinical application:

- A polished README with the architecture diagram and setup overview.
- A two-to-three minute demo video.
- Three or four screenshots: patient timeline, brief, evidence inspector, and refusal behavior.
- A short LinkedIn post describing the technical problem, safety boundary, and architecture.

## Recommendation

Prioritize evaluation tests, CloudWatch monitoring, documentation, screenshots, and the demo video before considering a public deployment. The private deployed demonstration is sufficient and safer for a portfolio prototype.
