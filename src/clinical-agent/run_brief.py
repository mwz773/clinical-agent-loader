"""Generate and persist one human-review care-coordination brief with Bedrock.

The script accepts the bounded JSON created by ``build_context.py``. It never
sends a full patient chart to the model and rejects evidence that is not
present in that input context.
"""

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

import boto3
import psycopg2
from psycopg2.extras import Json


SYSTEM_PROMPT = """You are assisting a human care coordinator.
Use only the supplied context. Do not diagnose, prescribe, or create
autonomous tasks. Return JSON only, with this exact top-level shape:
{
  "change_summary": ["short factual change"],
  "review_items": [{
    "category": "care_coordination|medication|follow_up|data_quality|other",
    "summary": "short factual item for a human reviewer",
    "evidence_resource_ids": ["FHIR resource ID from the supplied context"],
    "confidence": "low|medium|high"
  }],
  "human_review_required": true
}
Every review item must cite at least one supplied evidence resource ID. If the
context is insufficient, say so as a data_quality review item with the note ID
as evidence. Do not include patient-identifying details beyond those already
needed to describe the evidence."""


def get_connection():
    secret = json.loads(
        boto3.client(
            "secretsmanager", region_name=os.environ["AWS_REGION"]
        ).get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    )
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "clinical_agent"),
        user=secret["username"],
        password=secret["password"],
        sslmode="require",
    )


def evidence_by_id(context):
    """Return the allowed evidence IDs and their lineage source keys."""
    evidence = {}
    for item in (context.get("current_note"), context.get("prior_note")):
        if item:
            evidence[item["resource_id"]] = item
    for key in (
        "recent_encounters",
        "active_conditions",
        "active_medications",
        "events_since_prior_note",
    ):
        for item in context.get(key, []):
            evidence[item["resource_id"]] = item

    for key in (
        "new_encounters",
        "new_conditions",
        "resolved_conditions",
        "new_medication_records",
        "clinical_events",
    ):
        for item in context.get("changes_since_prior_note", {}).get(key, []):
            evidence[item["resource_id"]] = item
    return evidence


def model_json(response):
    text = "".join(
        block["text"]
        for block in response["output"]["message"]["content"]
        if "text" in block
    ).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("Bedrock response was not valid JSON") from error


def validate_brief(brief, allowed_evidence):
    if set(brief) != {
        "change_summary",
        "review_items",
        "human_review_required",
    }:
        raise ValueError("Bedrock response has an unexpected top-level shape")
    if not isinstance(brief["change_summary"], list):
        raise ValueError("change_summary must be a list")
    if brief["human_review_required"] is not True:
        raise ValueError("human_review_required must be true")
    if not isinstance(brief["review_items"], list):
        raise ValueError("review_items must be a list")

    required = {"category", "summary", "evidence_resource_ids", "confidence"}
    for item in brief["review_items"]:
        if set(item) != required:
            raise ValueError("A review item has an unexpected shape")
        if item["confidence"] not in {"low", "medium", "high"}:
            raise ValueError("A review item has an invalid confidence value")
        ids = item["evidence_resource_ids"]
        if not ids or not isinstance(ids, list):
            raise ValueError("Every review item needs evidence")
        unsupported = set(ids) - set(allowed_evidence)
        if unsupported:
            raise ValueError(
                "Bedrock cited evidence outside the supplied context: "
                + ", ".join(sorted(unsupported))
            )


def insert_failed_run(connection, run_id, patient_id, note_id, model_id, latency_ms):
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO agent_runs
                    (run_id, patient_id, note_id, model_id, latency_ms, status)
                VALUES (%s, %s, %s, %s, %s, 'failed')
                """,
                (run_id, patient_id, note_id, model_id, latency_ms),
            )


def persist_brief(
    connection, run_id, context, model_id, brief, allowed_evidence, usage,
    latency_ms, output_key,
):
    evidence_ids = {
        resource_id
        for item in brief["review_items"]
        for resource_id in item["evidence_resource_ids"]
    }
    current_note = context["current_note"]
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO agent_runs
                    (run_id, patient_id, note_id, model_id, prompt_tokens,
                     completion_tokens, latency_ms, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'succeeded')
                """,
                (
                    run_id, context["patient"]["patient_id"],
                    current_note["resource_id"], model_id,
                    usage.get("inputTokens"), usage.get("outputTokens"), latency_ms,
                ),
            )
            cursor.execute(
                """
                INSERT INTO follow_up_briefs
                    (run_id, change_summary, review_items, processed_output_s3_key)
                VALUES (%s, %s, %s, %s)
                """,
                (run_id, Json(brief["change_summary"]), Json(brief["review_items"]), output_key),
            )
            for resource_id in evidence_ids:
                item = allowed_evidence[resource_id]
                cursor.execute(
                    """
                    INSERT INTO brief_evidence
                        (run_id, resource_type, resource_id, source_s3_key)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (run_id, item["resource_type"], resource_id, item["source_s3_key"]),
                )


def main():
    parser = argparse.ArgumentParser(
        description="Generate one evidence-backed care-coordination brief."
    )
    parser.add_argument("--context", required=True, help="Path from build_context.py")
    parser.add_argument(
        "--model-id", default=os.environ.get("BEDROCK_MODEL_ID"),
        help="Bedrock model ID (or set BEDROCK_MODEL_ID).",
    )
    parser.add_argument(
        "--processed-bucket", default=os.environ.get("PROCESSED_BUCKET"),
        help="S3 bucket for the generated JSON (or set PROCESSED_BUCKET).",
    )
    parser.add_argument("--output-prefix", default="briefs")
    args = parser.parse_args()
    if not args.model_id or not args.processed_bucket:
        parser.error("Set --model-id and --processed-bucket (or their environment variables).")

    context = json.loads(Path(args.context).read_text(encoding="utf-8"))
    if not context.get("patient", {}).get("patient_id") or not context.get("current_note"):
        raise SystemExit("Context must contain patient and current_note fields.")
    allowed_evidence = evidence_by_id(context)
    run_id = str(uuid.uuid4())
    started = time.monotonic()
    connection = get_connection()

    try:
        response = boto3.client(
            "bedrock-runtime", region_name=os.environ["AWS_REGION"]
        ).converse(
            modelId=args.model_id,
            system=[{"text": SYSTEM_PROMPT}],
            messages=[{
                "role": "user",
                "content": [{"text": json.dumps(context, default=str)}],
            }],
            inferenceConfig={"maxTokens": 1000, "temperature": 0},
        )
        latency_ms = round((time.monotonic() - started) * 1000)
        brief = model_json(response)
        validate_brief(brief, allowed_evidence)
        output_key = f"{args.output_prefix.strip('/')}/{run_id}.json"
        output = {
            "run_id": run_id,
            "model_id": args.model_id,
            "context": context,
            "brief": brief,
        }
        boto3.client("s3", region_name=os.environ["AWS_REGION"]).put_object(
            Bucket=args.processed_bucket,
            Key=output_key,
            Body=json.dumps(output, indent=2, default=str).encode("utf-8"),
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )
        persist_brief(
            connection, run_id, context, args.model_id, brief, allowed_evidence,
            response.get("usage", {}), latency_ms, output_key,
        )
    except Exception:
        latency_ms = round((time.monotonic() - started) * 1000)
        try:
            insert_failed_run(
                connection, run_id, context["patient"]["patient_id"],
                context["current_note"]["resource_id"], args.model_id, latency_ms,
            )
        except Exception:
            pass
        raise
    finally:
        connection.close()

    print(json.dumps({
        "run_id": run_id,
        "status": "succeeded",
        "processed_output_s3_key": output_key,
        "latency_ms": latency_ms,
        "usage": response.get("usage", {}),
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status": "failed", "error": str(error)}), file=sys.stderr)
        raise SystemExit(1)
