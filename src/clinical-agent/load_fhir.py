'''
Unpacks FHIR data and loads into s3 bucket
'''

import argparse
import base64
import json
import os
import sys
from collections import Counter

import boto3
import psycopg2
from psycopg2.extras import Json

EVENT_RESOURCE_TYPES = {
    "DiagnosticReport",
    "Procedure",
    "CarePlan",
    "ServiceRequest",
    "Appointment",
    "Goal",
}

def get_secret():
    client = boto3.client(
        "secretsmanager",
        region_name=os.environ["AWS_REGION"],
    )
    response = client.get_secret_value(
        SecretId=os.environ["DB_SECRET_ARN"]
    )
    return json.loads(response["SecretString"])


def get_connection():
    secret = get_secret()

    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "clinical_agent"),
        user=secret["username"],
        password=secret["password"],
        sslmode="require",
        connect_timeout=10,
    )


def reference_id(reference):
    if not reference:
        return None

    value = reference.get("reference", "")

    if value.startswith("urn:uuid:"):
        return value.removeprefix("urn:uuid:")

    if "/" in value:
        return value.rsplit("/", 1)[-1]

    return value or None


def first_coding(concept):
    if not concept:
        return None, None, None

    coding = concept.get("coding", [])
    if not coding:
        return None, None, concept.get("text")

    first = coding[0]
    return first.get("system"), first.get("code"), first.get("display")


def first_resource_coding(resource, field="code"):
    return first_coding(resource.get(field))


def extension_value(resource, url_fragment):
    for extension in resource.get("extension", []):
        if url_fragment not in extension.get("url", ""):
            continue

        for nested in extension.get("extension", []):
            coding = nested.get("valueCoding")
            if coding:
                return coding.get("display") or coding.get("code")

            if "valueString" in nested:
                return nested["valueString"]

    return None


def decode_note(resource):
    for form in resource.get("presentedForm", []):
        encoded = form.get("data")

        if encoded:
            return base64.b64decode(encoded).decode(
                "utf-8",
                errors="replace",
            )

    return None


def value_json(resource):
    values = {
        key: value
        for key, value in resource.items()
        if key.startswith("value")
    }
    return values or None


def effective_time(resource):
    return (
        resource.get("effectiveDateTime")
        or resource.get("effectiveInstant")
        or resource.get("issued")
        or resource.get("effectivePeriod", {}).get("start")
    )


def encounter_time(resource, field):
    return resource.get("period", {}).get(field)


def upsert_patient(cursor, patient, source_key):
    cursor.execute(
        """
        INSERT INTO patients (
            patient_id, full_name, birth_date, gender, race, ethnicity,
            source_s3_key, raw_resource
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (patient_id) DO UPDATE SET
            full_name = EXCLUDED.full_name,
            birth_date = EXCLUDED.birth_date,
            gender = EXCLUDED.gender,
            race = EXCLUDED.race,
            ethnicity = EXCLUDED.ethnicity,
            source_s3_key = EXCLUDED.source_s3_key,
            raw_resource = EXCLUDED.raw_resource,
            loaded_at = NOW()
        """,
        (
            patient["id"],
            Json(patient.get("name", [])),
            patient.get("birthDate"),
            patient.get("gender"),
            extension_value(patient, "us-core-race"),
            extension_value(patient, "us-core-ethnicity"),
            source_key,
            Json(patient),
        ),
    )


def upsert_encounter(cursor, resource, patient_id, source_key):
    _, _, encounter_type = first_coding(
        (resource.get("type") or [{}])[0]
    )

    cursor.execute(
        """
        INSERT INTO encounters (
            encounter_id, patient_id, start_at, end_at,
            encounter_class, encounter_type, source_s3_key, raw_resource
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (encounter_id) DO UPDATE SET
            patient_id = EXCLUDED.patient_id,
            start_at = EXCLUDED.start_at,
            end_at = EXCLUDED.end_at,
            encounter_class = EXCLUDED.encounter_class,
            encounter_type = EXCLUDED.encounter_type,
            source_s3_key = EXCLUDED.source_s3_key,
            raw_resource = EXCLUDED.raw_resource
        """,
        (
            resource["id"],
            patient_id,
            encounter_time(resource, "start"),
            encounter_time(resource, "end"),
            resource.get("class", {}).get("code"),
            encounter_type,
            source_key,
            Json(resource),
        ),
    )


def upsert_condition(
    cursor,
    resource,
    patient_id,
    encounter_ids,
    source_key,
):
    system, code, description = first_resource_coding(resource)

    encounter_id = reference_id(resource.get("encounter"))
    if encounter_id not in encounter_ids:
        encounter_id = None

    cursor.execute(
        """
        INSERT INTO conditions (
            condition_id, patient_id, encounter_id, code_system, code,
            description, clinical_status, onset_at, abatement_at,
            source_s3_key, raw_resource
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (condition_id) DO UPDATE SET
            patient_id = EXCLUDED.patient_id,
            encounter_id = EXCLUDED.encounter_id,
            code_system = EXCLUDED.code_system,
            code = EXCLUDED.code,
            description = EXCLUDED.description,
            clinical_status = EXCLUDED.clinical_status,
            onset_at = EXCLUDED.onset_at,
            abatement_at = EXCLUDED.abatement_at,
            source_s3_key = EXCLUDED.source_s3_key,
            raw_resource = EXCLUDED.raw_resource
        """,
        (
            resource["id"],
            patient_id,
            encounter_id,
            system,
            code,
            description,
            first_coding(
                resource.get("clinicalStatus")
            )[1],
            resource.get("onsetDateTime")
            or resource.get("onsetPeriod", {}).get("start"),
            resource.get("abatementDateTime")
            or resource.get("abatementPeriod", {}).get("start"),
            source_key,
            Json(resource),
        ),
    )


def upsert_medication(
    cursor,
    resource,
    patient_id,
    encounter_ids,
    source_key,
):
    system, code, description = first_resource_coding(
        resource,
        "medicationCodeableConcept",
    )

    encounter_id = reference_id(resource.get("encounter"))
    if encounter_id not in encounter_ids:
        encounter_id = None

    cursor.execute(
        """
        INSERT INTO medications (
            medication_request_id, patient_id, encounter_id, code_system,
            code, description, status, intent, authored_at,
            source_s3_key, raw_resource
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (medication_request_id) DO UPDATE SET
            patient_id = EXCLUDED.patient_id,
            encounter_id = EXCLUDED.encounter_id,
            code_system = EXCLUDED.code_system,
            code = EXCLUDED.code,
            description = EXCLUDED.description,
            status = EXCLUDED.status,
            intent = EXCLUDED.intent,
            authored_at = EXCLUDED.authored_at,
            source_s3_key = EXCLUDED.source_s3_key,
            raw_resource = EXCLUDED.raw_resource
        """,
        (
            resource["id"],
            patient_id,
            encounter_id,
            system,
            code,
            description,
            resource.get("status"),
            resource.get("intent"),
            resource.get("authoredOn"),
            source_key,
            Json(resource),
        ),
    )


def upsert_observation(
    cursor,
    resource,
    patient_id,
    encounter_ids,
    source_key,
):
    system, code, description = first_resource_coding(resource)

    encounter_id = reference_id(resource.get("encounter"))
    if encounter_id not in encounter_ids:
        encounter_id = None

    cursor.execute(
        """
        INSERT INTO observations (
            observation_id, patient_id, encounter_id, code_system, code,
            description, status, observed_at, value_json,
            source_s3_key, raw_resource
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (observation_id) DO UPDATE SET
            patient_id = EXCLUDED.patient_id,
            encounter_id = EXCLUDED.encounter_id,
            code_system = EXCLUDED.code_system,
            code = EXCLUDED.code,
            description = EXCLUDED.description,
            status = EXCLUDED.status,
            observed_at = EXCLUDED.observed_at,
            value_json = EXCLUDED.value_json,
            source_s3_key = EXCLUDED.source_s3_key,
            raw_resource = EXCLUDED.raw_resource
        """,
        (
            resource["id"],
            patient_id,
            encounter_id,
            system,
            code,
            description,
            resource.get("status"),
            effective_time(resource),
            Json(value_json(resource)) if value_json(resource) else None,
            source_key,
            Json(resource),
        ),
    )


def upsert_note(
    cursor,
    resource,
    patient_id,
    encounter_ids,
    source_key,
):
    note_text = decode_note(resource)

    if not note_text:
        return False

    encounter_id = reference_id(resource.get("encounter"))
    if encounter_id not in encounter_ids:
        encounter_id = None

    cursor.execute(
        """
        INSERT INTO clinical_notes (
            note_id, patient_id, encounter_id, note_date, note_text,
            source_s3_key, raw_resource
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (note_id) DO UPDATE SET
            patient_id = EXCLUDED.patient_id,
            encounter_id = EXCLUDED.encounter_id,
            note_date = EXCLUDED.note_date,
            note_text = EXCLUDED.note_text,
            source_s3_key = EXCLUDED.source_s3_key,
            raw_resource = EXCLUDED.raw_resource
        """,
        (
            resource["id"],
            patient_id,
            encounter_id,
            effective_time(resource),
            note_text,
            source_key,
            Json(resource),
        ),
    )
    return True


def event_time(resource):
    candidates = [
        resource.get("effectiveDateTime"),
        resource.get("effectiveInstant"),
        resource.get("issued"),
        resource.get("authoredOn"),
        resource.get("performedDateTime"),
        resource.get("start"),
        resource.get("created"),
        resource.get("period", {}).get("start"),
        resource.get("effectivePeriod", {}).get("start"),
        resource.get("performedPeriod", {}).get("start"),
        resource.get("occurrencePeriod", {}).get("start"),
    ]

    return next((value for value in candidates if value), None)


def event_coding(resource):
    for field in ("code", "category", "serviceType"):
        concept = resource.get(field)

        if isinstance(concept, list):
            concept = concept[0] if concept else None

        system, code, description = first_coding(concept)

        if system or code or description:
            return system, code, description

    return (
        None,
        None,
        resource.get("description") or resource.get("title"),
    )


def upsert_clinical_event(
    cursor,
    resource,
    patient_id,
    encounter_ids,
    source_key,
):
    system, code, description = event_coding(resource)

    encounter_id = reference_id(resource.get("encounter"))
    if encounter_id not in encounter_ids:
        encounter_id = None

    cursor.execute(
        """
        INSERT INTO clinical_events (
            event_id, patient_id, encounter_id, resource_type,
            event_time, status, code_system, code, description,
            source_s3_key, raw_resource
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (event_id) DO UPDATE SET
            patient_id = EXCLUDED.patient_id,
            encounter_id = EXCLUDED.encounter_id,
            resource_type = EXCLUDED.resource_type,
            event_time = EXCLUDED.event_time,
            status = EXCLUDED.status,
            code_system = EXCLUDED.code_system,
            code = EXCLUDED.code,
            description = EXCLUDED.description,
            source_s3_key = EXCLUDED.source_s3_key,
            raw_resource = EXCLUDED.raw_resource
        """,
        (
            resource["id"],
            patient_id,
            encounter_id,
            resource["resourceType"],
            event_time(resource),
            resource.get("status") or resource.get("lifecycleStatus"),
            system,
            code,
            description,
            source_key,
            Json(resource),
        ),
    )

def mark_file(cursor, source_key, etag, status, patient_id, counts, error=None):
    cursor.execute(
        """
        INSERT INTO ingestion_files (
            source_s3_key, source_etag, status, patient_id,
            resource_counts, error_message, loaded_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (source_s3_key) DO UPDATE SET
            source_etag = EXCLUDED.source_etag,
            status = EXCLUDED.status,
            patient_id = EXCLUDED.patient_id,
            resource_counts = EXCLUDED.resource_counts,
            error_message = EXCLUDED.error_message,
            loaded_at = NOW()
        """,
        (
            source_key,
            etag,
            status,
            patient_id,
            Json(dict(counts)),
            error,
        ),
    )


def load_bundle(connection, source_key, body, etag, force=False):
    bundle = json.loads(body)
    resources = [
        entry["resource"]
        for entry in bundle.get("entry", [])
        if "resource" in entry
    ]

    patients = [
        resource
        for resource in resources
        if resource.get("resourceType") == "Patient"
    ]

    counts = Counter(
        resource.get("resourceType", "Unknown")
        for resource in resources
    )

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT source_etag, status FROM ingestion_files "
            "WHERE source_s3_key = %s",
            (source_key,),
        )
        previous = cursor.fetchone()

    if (
        previous
        and previous[0] == etag
        and previous[1] == "loaded"
        and not force
    ):
        print(f"Skipped already-loaded file: {source_key}")
        return "skipped"

    if not patients:
        with connection:
            with connection.cursor() as cursor:
                mark_file(
                    cursor,
                    source_key,
                    etag,
                    "skipped",
                    None,
                    counts,
                )
        print(f"Skipped non-patient bundle: {source_key}")
        return "skipped"

    patient = patients[0]
    patient_id = patient["id"]
    encounter_ids = {
        resource["id"]
        for resource in resources
        if resource.get("resourceType") == "Encounter"
        and resource.get("id")
    }

    try:
        with connection:
            with connection.cursor() as cursor:
                upsert_patient(cursor, patient, source_key)

                for resource in resources:
                    resource_type = resource.get("resourceType")

                    if resource_type == "Encounter" and resource.get("id"):
                        upsert_encounter(
                            cursor,
                            resource,
                            patient_id,
                            source_key,
                        )

                for resource in resources:
                    resource_type = resource.get("resourceType")

                    if not resource.get("id"):
                        continue

                    if resource_type == "Condition":
                        upsert_condition(
                            cursor,
                            resource,
                            patient_id,
                            encounter_ids,
                            source_key,
                        )
                    elif resource_type == "MedicationRequest":
                        upsert_medication(
                            cursor,
                            resource,
                            patient_id,
                            encounter_ids,
                            source_key,
                        )
                    elif resource_type == "Observation":
                        upsert_observation(
                            cursor,
                            resource,
                            patient_id,
                            encounter_ids,
                            source_key,
                        )
                    elif resource_type == "DiagnosticReport":
                        upsert_note(
                            cursor,
                            resource,
                            patient_id,
                            encounter_ids,
                            source_key,
                        )
                        upsert_clinical_event(
                            cursor,
                            resource,
                            patient_id,
                            encounter_ids,
                            source_key,
                        )
                    elif resource_type in EVENT_RESOURCE_TYPES:
                        upsert_clinical_event(
                            cursor,
                            resource,
                            patient_id,
                            encounter_ids,
                            source_key,
                        )
                mark_file(
                    cursor,
                    source_key,
                    etag,
                    "loaded",
                    patient_id,
                    counts,
                )

        print(f"Loaded patient {patient_id}: {source_key}")
        return "loaded"

    except Exception as error:
        connection.rollback()

        with connection:
            with connection.cursor() as cursor:
                mark_file(
                    cursor,
                    source_key,
                    etag,
                    "failed",
                    patient_id,
                    counts,
                    str(error)[:1000],
                )

        raise


def list_s3_keys(s3, bucket, prefix):
    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            key = item["Key"]

            if key.endswith(".json"):
                yield key


def main():
    parser = argparse.ArgumentParser(
        description="Load Synthea FHIR Bundles from S3 into PostgreSQL."
    )
    parser.add_argument(
        "--s3-key",
        help="Load exactly one S3 object key.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Load every JSON object under S3_PREFIX.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reload files even if the same S3 ETag was already loaded.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of files to load with --all.",
    )
    args = parser.parse_args()

    if bool(args.s3_key) == bool(args.all):
        parser.error("Use exactly one of --s3-key or --all.")

    bucket = os.environ["S3_BUCKET"]
    prefix = os.environ.get("S3_PREFIX", "")
    region = os.environ["AWS_REGION"]

    s3 = boto3.client("s3", region_name=region)
    connection = get_connection()

    keys = [args.s3_key] if args.s3_key else list_s3_keys(
        s3,
        bucket,
        prefix,
    )

    results = Counter()

    try:
        for index, source_key in enumerate(keys, start=1):
            if args.limit and index > args.limit:
                break

            response = s3.get_object(
                Bucket=bucket,
                Key=source_key,
            )

            body = response["Body"].read().decode("utf-8")
            etag = response["ETag"].strip('"')

            try:
                result = load_bundle(
                    connection,
                    source_key,
                    body,
                    etag,
                    force=args.force,
                )
                results[result] += 1
            except Exception as error:
                results["failed"] += 1
                print(
                    f"Failed to load {source_key}: {error}",
                    file=sys.stderr,
                )

    finally:
        connection.close()

    print(f"Finished: {dict(results)}")


if __name__ == "__main__":
    main()