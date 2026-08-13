"""Read-only Streamlit interface for the synthetic care-coordination demo.

Run this only on the EC2 host through an SSM port-forward. It intentionally
uses the existing command-line workflows so the UI and terminal runs follow
the same bounded-context and evidence-validation rules.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import boto3
import psycopg2
import streamlit as st


APP_DIR = Path(__file__).resolve().parent
CONTEXT_SCRIPT = APP_DIR / "build_context.py"
BRIEF_SCRIPT = APP_DIR / "run_brief.py"


def get_connection():
    """Connect using the instance role and the RDS secret, never a password."""
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


@st.cache_data(ttl=60)
def list_patients():
    """Return only synthetic-patient fields needed by the selector."""
    connection = get_connection()
    try:
        with connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT patient_id, full_name, birth_date, gender
                FROM patients
                ORDER BY full_name, patient_id
                """
            )
            rows = cursor.fetchall()
    finally:
        connection.close()

    return [
        {
            "patient_id": patient_id,
            "full_name": display_name(full_name),
            "birth_date": str(birth_date) if birth_date else "Unknown",
            "gender": gender or "Unknown",
        }
        for patient_id, full_name, birth_date, gender in rows
    ]


def display_name(full_name):
    """Format the FHIR Patient.name JSON stored in the ``full_name`` column."""
    if not isinstance(full_name, list) or not full_name:
        return "Unknown patient"

    name = next(
        (item for item in full_name if item.get("use") == "official"),
        full_name[0],
    )
    if name.get("text"):
        return name["text"]

    parts = [*name.get("given", []), name.get("family")]
    return " ".join(part for part in parts if part) or "Unknown patient"


def run_script(command):
    """Run an existing workflow and show its actual error in the UI."""
    result = subprocess.run(
        command,
        cwd=APP_DIR,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or "Unknown script error"
        raise RuntimeError(message)
    return result.stdout.strip()


def build_context(patient_id):
    with tempfile.TemporaryDirectory() as temporary_directory:
        context_path = Path(temporary_directory) / "context.json"
        run_script(
            [
                sys.executable,
                str(CONTEXT_SCRIPT),
                "--patient-id",
                patient_id,
                "--output",
                str(context_path),
            ]
        )
        return json.loads(context_path.read_text(encoding="utf-8"))


def format_record(record):
    description = record.get("description") or record.get("encounter_type") or "No description"
    timestamp = (
        record.get("event_time")
        or record.get("start_at")
        or record.get("onset_at")
        or record.get("abatement_at")
        or record.get("authored_at")
        or "No date"
    )
    return f"**{description}**  \n{timestamp}  \n`{record['resource_id']}`"


def display_change_group(title, records):
    st.subheader(title)
    if not records:
        st.caption("None found in the comparison window.")
        return
    for record in records:
        st.markdown(format_record(record))


st.set_page_config(page_title="Care Coordination Demo", layout="wide")
st.title("Longitudinal Care-Coordination Agent")
st.caption(
    "Synthetic Synthea data only. Generated content supports human review and is not medical advice."
)

try:
    patients = list_patients()
except Exception as error:
    st.error(f"Unable to load patients from RDS: {error}")
    st.stop()

if not patients:
    st.warning("No patients are loaded yet. Run the FHIR loader before using the UI.")
    st.stop()

patient_by_id = {patient["patient_id"]: patient for patient in patients}
selected_id = st.selectbox(
    "Select a synthetic patient",
    options=list(patient_by_id),
    format_func=lambda patient_id: (
        f"{patient_by_id[patient_id]['full_name']} — {patient_id}"
    ),
)

if st.button("Load patient context", type="primary") or st.session_state.get("selected_id") != selected_id:
    try:
        st.session_state.context = build_context(selected_id)
        st.session_state.selected_id = selected_id
        st.session_state.pop("brief_result", None)
    except Exception as error:
        st.error(f"Unable to build context: {error}")

context = st.session_state.get("context")
if not context or st.session_state.get("selected_id") != selected_id:
    st.info("Select a patient, then choose **Load patient context**.")
    st.stop()

patient = context["patient"]
st.header("Patient context")
details = st.columns(4)
details[0].metric("Patient ID", patient["patient_id"])
details[1].metric("Birth date", str(patient.get("birth_date") or "Unknown"))
details[2].metric("Gender", patient.get("gender") or "Unknown")
details[3].metric("Prior note available", "Yes" if context["prior_note"] else "No")

changes = context["changes_since_prior_note"]
st.header("Verified changes since prior note")
st.caption(
    "These records are calculated from PostgreSQL before any model call. Empty groups are valid outcomes."
)
left, right = st.columns(2)
with left:
    display_change_group("New encounters", changes["new_encounters"])
    display_change_group("New conditions", changes["new_conditions"])
    display_change_group("New medication records", changes["new_medication_records"])
with right:
    display_change_group("Resolved conditions", changes["resolved_conditions"])
    display_change_group("Clinical events", changes["clinical_events"])

with st.expander("Current and prior notes"):
    st.markdown("#### Current note")
    st.caption(str(context["current_note"].get("note_date") or "No date"))
    st.text(context["current_note"]["note_text"])
    st.markdown("#### Prior note")
    if context["prior_note"]:
        st.caption(str(context["prior_note"].get("note_date") or "No date"))
        st.text(context["prior_note"]["note_text"])
    else:
        st.caption("No prior note is available.")

st.header("Care-coordination brief")
st.caption("This action invokes Bedrock and writes a validated artifact to processed S3 and RDS.")

if st.button("Generate evidence-backed brief"):
    if not os.environ.get("PROCESSED_BUCKET"):
        st.error("Set PROCESSED_BUCKET in the EC2 environment before generating a brief.")
    else:
        with st.spinner("Generating and validating brief..."):
            try:
                with tempfile.TemporaryDirectory() as temporary_directory:
                    context_path = Path(temporary_directory) / "context.json"
                    context_path.write_text(json.dumps(context, default=str), encoding="utf-8")
                    output = run_script(
                        [
                            sys.executable,
                            str(BRIEF_SCRIPT),
                            "--context",
                            str(context_path),
                        ]
                    )
                st.session_state.brief_result = json.loads(output)
            except Exception as error:
                st.error(f"Brief generation failed: {error}")

brief_result = st.session_state.get("brief_result")
if brief_result:
    st.success(f"Validated brief saved as `{brief_result['processed_output_s3_key']}`")
    st.json(brief_result)
