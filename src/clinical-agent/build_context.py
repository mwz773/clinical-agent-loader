'''
Creates small, structured context containing only information
needed to compare one note with what came before it

This is the JSON fed into Bedrock
'''

import argparse
import json
import os
from pathlib import Path

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor


def get_connection():
    secret = json.loads(
        boto3.client(
            "secretsmanager",
            region_name=os.environ["AWS_REGION"],
        ).get_secret_value(
            SecretId=os.environ["DB_SECRET_ARN"]
        )["SecretString"]
    )

    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ["DB_NAME"],
        user=secret["username"],
        password=secret["password"],
        sslmode="require",
    )


def fetch_one(cursor, query, values):
    cursor.execute(query, values)
    return cursor.fetchone()


def fetch_all(cursor, query, values):
    cursor.execute(query, values)
    return cursor.fetchall()


def main():
    parser = argparse.ArgumentParser(
        description="Build bounded RAG context for one clinical note."
    )
    parser.add_argument("--patient-id", required=True)
    parser.add_argument(
        "--note-id",
        help="Optional. Defaults to the patient's most recent note.",
    )
    parser.add_argument(
        "--output",
        default="care_coordination_context.json",
    )
    args = parser.parse_args()

    connection = get_connection()

    with connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        patient = fetch_one(
            cursor,
            """
            SELECT patient_id, birth_date, gender, race, ethnicity
            FROM patients
            WHERE patient_id = %s
            """,
            (args.patient_id,),
        )

        if not patient:
            raise SystemExit(f"Patient not found: {args.patient_id}")

        if args.note_id:
            current_note = fetch_one(
                cursor,
                """
                SELECT note_id, note_date, note_text, source_s3_key
                FROM clinical_notes
                WHERE patient_id = %s AND note_id = %s
                """,
                (args.patient_id, args.note_id),
            )
        else:
            current_note = fetch_one(
                cursor,
                """
                SELECT note_id, note_date, note_text, source_s3_key
                FROM clinical_notes
                WHERE patient_id = %s
                ORDER BY note_date DESC, note_id DESC
                LIMIT 1
                """,
                (args.patient_id,),
            )

        if not current_note:
            raise SystemExit("Clinical note not found.")

        prior_note = fetch_one(
            cursor,
            """
            SELECT note_id, note_date, note_text, source_s3_key
            FROM clinical_notes
            WHERE patient_id = %s
              AND (
                  note_date < %s
                  OR (note_date = %s AND note_id < %s)
              )
            ORDER BY note_date DESC, note_id DESC
            LIMIT 1
            """,
            (
                args.patient_id,
                current_note["note_date"],
                current_note["note_date"],
                current_note["note_id"],
            ),
        )

        encounters = fetch_all(
            cursor,
            """
            SELECT
                encounter_id AS resource_id,
                'Encounter' AS resource_type,
                start_at,
                end_at,
                encounter_class,
                encounter_type,
                source_s3_key
            FROM encounters
            WHERE patient_id = %s AND start_at <= %s
            ORDER BY start_at DESC
            LIMIT 5
            """,
            (args.patient_id, current_note["note_date"]),
        )

        active_conditions = fetch_all(
            cursor,
            """
            SELECT
                condition_id AS resource_id,
                'Condition' AS resource_type,
                code,
                description,
                clinical_status,
                onset_at,
                source_s3_key
            FROM conditions
            WHERE patient_id = %s
              AND (onset_at IS NULL OR onset_at <= %s)
              AND (abatement_at IS NULL OR abatement_at >= %s)
            ORDER BY onset_at DESC NULLS LAST
            LIMIT 10
            """,
            (
                args.patient_id,
                current_note["note_date"],
                current_note["note_date"],
            ),
        )

        active_medications = fetch_all(
            cursor,
            """
            SELECT
                medication_request_id AS resource_id,
                'MedicationRequest' AS resource_type,
                code,
                description,
                status,
                authored_at,
                source_s3_key
            FROM medications
            WHERE patient_id = %s
              AND status = 'active'
              AND (authored_at IS NULL OR authored_at <= %s)
            ORDER BY authored_at DESC NULLS LAST
            LIMIT 10
            """,
            (args.patient_id, current_note["note_date"]),
        )

        if prior_note:
            comparison_values = (
                args.patient_id,
                prior_note["note_date"],
                current_note["note_date"],
            )

            events = fetch_all(
                cursor,
                """
                SELECT
                    event_id AS resource_id,
                    resource_type,
                    event_time,
                    status,
                    code,
                    description,
                    source_s3_key
                FROM clinical_events
                WHERE patient_id = %s
                  AND event_time > %s
                  AND event_time <= %s
                ORDER BY event_time DESC
                LIMIT 20
                """,
                comparison_values,
            )

            new_encounters = fetch_all(
                cursor,
                """
                SELECT
                    encounter_id AS resource_id,
                    'Encounter' AS resource_type,
                    start_at,
                    end_at,
                    encounter_class,
                    encounter_type,
                    source_s3_key
                FROM encounters
                WHERE patient_id = %s
                  AND start_at > %s
                  AND start_at <= %s
                ORDER BY start_at DESC
                LIMIT 10
                """,
                comparison_values,
            )

            new_conditions = fetch_all(
                cursor,
                """
                SELECT
                    condition_id AS resource_id,
                    'Condition' AS resource_type,
                    onset_at,
                    clinical_status,
                    code,
                    description,
                    source_s3_key
                FROM conditions
                WHERE patient_id = %s
                  AND onset_at > %s
                  AND onset_at <= %s
                ORDER BY onset_at DESC
                LIMIT 10
                """,
                comparison_values,
            )

            resolved_conditions = fetch_all(
                cursor,
                """
                SELECT
                    condition_id AS resource_id,
                    'Condition' AS resource_type,
                    abatement_at,
                    clinical_status,
                    code,
                    description,
                    source_s3_key
                FROM conditions
                WHERE patient_id = %s
                  AND abatement_at > %s
                  AND abatement_at <= %s
                ORDER BY abatement_at DESC
                LIMIT 10
                """,
                comparison_values,
            )

            new_medication_records = fetch_all(
                cursor,
                """
                SELECT
                    medication_request_id AS resource_id,
                    'MedicationRequest' AS resource_type,
                    authored_at,
                    status,
                    code,
                    description,
                    source_s3_key
                FROM medications
                WHERE patient_id = %s
                  AND authored_at > %s
                  AND authored_at <= %s
                ORDER BY authored_at DESC
                LIMIT 10
                """,
                comparison_values,
            )
        else:
            events = []
            new_encounters = []
            new_conditions = []
            resolved_conditions = []
            new_medication_records = []

    connection.close()

    context = {
        "purpose": (
            "Human-review care-coordination brief. "
            "Do not diagnose, prescribe, or create autonomous tasks."
        ),
        "patient": patient,
        "current_note": {
            "resource_id": current_note["note_id"],
            "resource_type": "DiagnosticReport",
            "note_date": current_note["note_date"],
            "note_text": current_note["note_text"],
            "source_s3_key": current_note["source_s3_key"],
        },
        "prior_note": (
            {
                "resource_id": prior_note["note_id"],
                "resource_type": "DiagnosticReport",
                "note_date": prior_note["note_date"],
                "note_text": prior_note["note_text"],
                "source_s3_key": prior_note["source_s3_key"],
            }
            if prior_note
            else None
        ),
        "recent_encounters": encounters,
        "active_conditions": active_conditions,
        "active_medications": active_medications,
        "events_since_prior_note": events,
        "changes_since_prior_note": {
        "comparison_available": prior_note is not None,
        "comparison_start": (
            prior_note["note_date"] if prior_note else None
        ),
        "comparison_end": current_note["note_date"],
        "new_encounters": new_encounters,
        "new_conditions": new_conditions,
        "resolved_conditions": resolved_conditions,
        "new_medication_records": new_medication_records,
        "clinical_events": events,
        },
    }

    output = Path(args.output)
    output.write_text(
        json.dumps(context, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"Wrote bounded context: {output}")
    print(f"Current note: {current_note['note_id']}")
    print(f"Prior note found: {bool(prior_note)}")
    print(f"Events since prior note: {len(events)}")
    print(f"New encounters: {len(new_encounters)}")
    print(f"New conditions: {len(new_conditions)}")
    print(f"Resolved conditions: {len(resolved_conditions)}")
    print(f"New medication records: {len(new_medication_records)}")

if __name__ == "__main__":
    main()
