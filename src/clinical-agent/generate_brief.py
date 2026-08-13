import argparse
import json
import os
from datetime import datetime, timezone

import boto3


def collect_resource_ids(context):
    """Collect only IDs that the model is allowed to cite."""
    resource_ids = set()

    for key in ("current_note", "prior_note"):
        item = context.get(key)
        if item and item.get("resource_id"):
            resource_ids.add(item["resource_id"])

    for section in (
        "recent_encounters",
        "active_conditions",
        "active_medications",
        "events_since_prior_note",
    ):
        for item in context.get(section, []):
            if item.get("resource_id"):
                resource_ids.add(item["resource_id"])

    return resource_ids


def parse_model_json(text):
    """Accept plain JSON or JSON returned inside a Markdown code fence."""
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0].strip()

    return json.loads(cleaned)


def validate_brief(brief, context):
    required_fields = {
        "patient_id",
        "care_coordination_summary",
        "review_items",
        "human_review_required",
    }

    missing = required_fields - brief.keys()
    if missing:
        raise ValueError(f"Model response is missing required fields: {sorted(missing)}")

    if brief["patient_id"] != context["patient"]["patient_id"]:
        raise ValueError("Model response has an incorrect patient_id.")

    if not isinstance(brief["review_items"], list):
        raise ValueError("review_items must be a JSON list.")

    if brief["human_review_required"] is not True:
        raise ValueError("human_review_required must be true.")

    allowed_resource_ids = collect_resource_ids(context)

    for index, item in enumerate(brief["review_items"], start=1):
        required_item_fields = {"item", "reason", "evidence_resource_ids"}
        missing_item_fields = required_item_fields - item.keys()

        if missing_item_fields:
            raise ValueError(
                f"Review item {index} is missing: {sorted(missing_item_fields)}"
            )

        cited_ids = item["evidence_resource_ids"]

        if not isinstance(cited_ids, list) or not cited_ids:
            raise ValueError(
                f"Review item {index} must contain at least one evidence resource ID."
            )

        invalid_ids = set(cited_ids) - allowed_resource_ids
        if invalid_ids:
            raise ValueError(
                f"Review item {index} cited IDs not present in the context: "
                f"{sorted(invalid_ids)}"
            )

    return brief


parser = argparse.ArgumentParser(
    description="Generate a human-review care-coordination brief with Bedrock."
)
parser.add_argument("--context", required=True, help="Path to build_context JSON output.")
parser.add_argument(
    "--output",
    default="care_coordination_brief.json",
    help="Where to save the validated brief JSON.",
)
args = parser.parse_args()

with open(args.context, "r", encoding="utf-8") as file:
    context = json.load(file)

model_id = os.environ["BEDROCK_MODEL_ID"]
region = os.environ["AWS_REGION"]

instructions = """
You are a care-coordination support assistant.

Create a concise brief for a human care coordinator using ONLY the supplied
patient context. Do not diagnose, prescribe, triage, claim urgency, or create
autonomous tasks. Do not infer facts that are absent from the context.

Focus on meaningful changes between the current and prior documentation, plus
items that a human coordinator may want to review. If there is no meaningful
change, say that clearly and return an empty review_items array.

Every review item must cite one or more source resource IDs from the supplied
context. Never invent an ID.

Return JSON only, with exactly this shape:

{
  "patient_id": "string",
  "care_coordination_summary": "string",
  "review_items": [
    {
      "item": "string",
      "reason": "string",
      "evidence_resource_ids": ["FHIR resource ID"]
    }
  ],
  "human_review_required": true
}
""".strip()

client = boto3.client("bedrock-runtime", region_name=region)

response = client.converse(
    modelId=model_id,
    system=[{"text": instructions}],
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "text": (
                        "Create a care-coordination brief from this context:\n\n"
                        + json.dumps(context, indent=2)
                    )
                }
            ],
        }
    ],
    inferenceConfig={
        "maxTokens": 1000,
        "temperature": 0,
    },
)

model_text = response["output"]["message"]["content"][0]["text"]
brief = parse_model_json(model_text)
validated_brief = validate_brief(brief, context)

result = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "model_id": model_id,
    "source_context_file": args.context,
    "brief": validated_brief,
}

with open(args.output, "w", encoding="utf-8") as file:
    json.dump(result, file, indent=2)

print(f"Validated brief written to: {args.output}")
print(json.dumps(validated_brief, indent=2))