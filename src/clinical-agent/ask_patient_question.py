"""Answer one bounded, evidence-cited patient-history question with Bedrock.

This command-line tool deliberately does not query RDS, access raw S3 FHIR
Bundles, alter records, or persist questions/answers. Its only clinical input
is the context JSON produced by build_context.py.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import boto3


SYSTEM_PROMPT = """You are a read-only patient-history retrieval assistant.
Use only the supplied bounded synthetic-patient context and answer only
factual questions about the selected patient's documented history inside its
specified history window.

Refuse requests for diagnosis, prognosis, treatment, medication or dosage
recommendations, triage, urgency, risk prediction, autonomous actions,
information about another patient, or unrelated information. A refusal should
briefly state that this tool retrieves documented history for human review and
cannot provide the requested advice or action.

If the question is in scope but cannot be answered from the supplied context,
return insufficient_evidence. Do not use medical knowledge to fill gaps.

Return JSON only, with exactly this shape:
{
  "response_type": "answer | refusal | insufficient_evidence",
  "answer": "plain-language response for a human reviewer",
  "evidence_resource_ids": ["FHIR resource ID"],
  "history_window_years": 5
}

For response_type answer, cite one or more IDs from
allowed_evidence_resource_ids and no other IDs. Never cite patient_id.
Keep answers concise. Cite no more than five representative evidence IDs; for
broader questions, summarize the documented pattern rather than listing every
matching record.
For refusal or insufficient_evidence, use an empty evidence_resource_ids list.
history_window_years must exactly equal the value in the supplied context."""

def repair_prompt(validation_error):
    return f"""Your previous response violated this validation rule:

{validation_error}

Return a corrected JSON response only, with exactly these keys:
response_type, answer, evidence_resource_ids, history_window_years.

For response_type "answer":
- Use no more than five evidence_resource_ids.
- Make the answer concise.
- Mention only facts supported by the IDs you retain.

Do not add Markdown, explanation, or any other keys."""

def local_refusal(question, history_years):
    """Reject clear out-of-scope requests before a model call.

    The model still receives the full policy for ambiguous questions. This
    lightweight check makes the explicit safety cases deterministic and avoids
    spending a Bedrock invocation on a request the tool cannot answer.
    """
    normalized = question.lower()
    blocked_phrases = (
        "diagnose",
        "diagnosis",
        "prognosis",
        "what should i prescribe",
        "what should they take",
        "what medication should",
        "what dosage",
        "should i take",
        "is this urgent",
        "is this an emergency",
        "emergency guidance",
        "schedule a",
        "book a",
        "create a referral",
        "send a message",
        "compare this patient to",
    )
    if any(phrase in normalized for phrase in blocked_phrases):
        return {
            "response_type": "refusal",
            "answer": (
                "This tool retrieves and summarizes documented patient history "
                "for human review. It cannot provide clinical advice, diagnosis, "
                "treatment recommendations, triage, or take actions."
            ),
            "evidence_resource_ids": [],
            "history_window_years": history_years,
        }
    return None


def allowed_evidence_by_id(context):
    """Build the same allow-list used by brief generation."""
    evidence = {}

    for item in (context.get("current_note"), context.get("prior_note")):
        if item:
            evidence[item["resource_id"]] = item

    for section in (
        "recent_encounters",
        "active_conditions",
        "active_medications",
        "events_since_prior_note",
    ):
        for item in context.get(section, []):
            evidence[item["resource_id"]] = item

    changes = context.get("changes_since_prior_note", {})
    for section in (
        "new_encounters",
        "new_conditions",
        "resolved_conditions",
        "new_medication_records",
        "clinical_events",
    ):
        for item in changes.get(section, []):
            evidence[item["resource_id"]] = item

    for item in context.get("longitudinal_timeline", {}).get("records", []):
        evidence[item["resource_id"]] = item

    return evidence


def model_text(response):
    return "".join(
        block["text"]
        for block in response["output"]["message"]["content"]
        if "text" in block
    ).strip()


def parse_model_json(text):
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("Bedrock response was not valid JSON.") from error


def validate_response(response, context, allowed_evidence):
    required_fields = {
        "response_type",
        "answer",
        "evidence_resource_ids",
        "history_window_years",
    }
    if set(response) != required_fields:
        raise ValueError("Bedrock response has an unexpected JSON shape.")

    response_type = response["response_type"]
    if response_type not in {"answer", "refusal", "insufficient_evidence"}:
        raise ValueError("Bedrock response has an invalid response_type.")

    if not isinstance(response["answer"], str) or not response["answer"].strip():
        raise ValueError("Bedrock response must contain a non-empty answer.")

    history_years = context.get("longitudinal_timeline", {}).get("history_years")
    if response["history_window_years"] != history_years:
        raise ValueError("Bedrock response used an incorrect history window.")

    evidence_ids = response["evidence_resource_ids"]
    if not isinstance(evidence_ids, list):
        raise ValueError("evidence_resource_ids must be a JSON list.")

    if response_type == "answer" and not evidence_ids:
        raise ValueError("An evidence-cited answer requires at least one resource ID.")
    if len(evidence_ids) > 5:
        raise ValueError("An answer cannot cite more than five resource IDs.")
    if response_type != "answer" and evidence_ids:
        raise ValueError("Refusal and insufficient-evidence responses cannot cite IDs.")

    unsupported = set(evidence_ids) - set(allowed_evidence)
    if unsupported:
        raise ValueError(
            "Bedrock cited evidence outside the supplied context: "
            + ", ".join(sorted(unsupported))
        )

    return response


def main():
    parser = argparse.ArgumentParser(
        description="Ask one evidence-cited question about bounded patient history."
    )
    parser.add_argument("--context", required=True, help="JSON output from build_context.py")
    parser.add_argument("--question", required=True, help="One patient-history question")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print a raw Bedrock response to stderr if validation fails.",
    )
    parser.add_argument(
        "--model-id",
        default=os.environ.get("BEDROCK_MODEL_ID"),
        help="Bedrock model ID (or set BEDROCK_MODEL_ID).",
    )
    args = parser.parse_args()

    if not args.model_id:
        parser.error("Set --model-id or BEDROCK_MODEL_ID.")

    context = json.loads(Path(args.context).read_text(encoding="utf-8"))
    history_years = context.get("longitudinal_timeline", {}).get("history_years")
    if not context.get("patient", {}).get("patient_id") or not history_years:
        raise SystemExit("Context must include patient data and a longitudinal timeline.")

    refusal = local_refusal(args.question, history_years)
    if refusal:
        print(json.dumps(refusal, indent=2))
        return

    allowed_evidence = allowed_evidence_by_id(context)
    model_input = {
        "question": args.question,
        "context": context,
        "allowed_evidence_resource_ids": sorted(allowed_evidence),
    }

    client = boto3.client("bedrock-runtime", region_name=os.environ["AWS_REGION"])
    response = client.converse(
        modelId=args.model_id,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{
            "role": "user",
            "content": [{"text": json.dumps(model_input, default=str)}],
        }],
        inferenceConfig={"maxTokens": 600, "temperature": 0},
    )

    raw_response = model_text(response)
    try:
        answer = validate_response(
            parse_model_json(raw_response), context, allowed_evidence
        )
    except (ValueError, KeyError) as initial_error:
        repair_response = client.converse(
            modelId=args.model_id,
            system=[{"text": SYSTEM_PROMPT}],
            messages=[
                {
                    "role": "user",
                    "content": [{"text": json.dumps(model_input, default=str)}],
                },
                {
                    "role": "assistant",
                    "content": [{"text": raw_response}],
                },
                {
                    "role": "user",
                    "content": [{"text": repair_prompt(str(initial_error))}],
                },
            ],
            inferenceConfig={"maxTokens": 600, "temperature": 0},
        )
        repaired_response = model_text(repair_response)
        try:
            answer = validate_response(
                parse_model_json(repaired_response), context, allowed_evidence
            )
        except (ValueError, KeyError) as repair_error:
            if args.debug:
                print(f"Initial model response:\n{raw_response}", file=sys.stderr)
                print(f"Repair model response:\n{repaired_response}", file=sys.stderr)
            raise ValueError(
                "Bedrock response failed validation after one format-repair retry: "
                f"{repair_error}"
            ) from initial_error
    print(json.dumps(answer, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status": "failed", "error": str(error)}), file=sys.stderr)
        raise SystemExit(1)
