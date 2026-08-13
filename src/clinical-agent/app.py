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
CHAT_SCRIPT = APP_DIR / "ask_patient_question.py"


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


def build_context(patient_id, history_years):
    with tempfile.TemporaryDirectory() as temporary_directory:
        context_path = Path(temporary_directory) / "context.json"
        run_script(
            [
                sys.executable,
                str(CONTEXT_SCRIPT),
                "--patient-id",
                patient_id,
                "--history-years",
                str(history_years),
                "--output",
                str(context_path),
            ]
        )
        return json.loads(context_path.read_text(encoding="utf-8"))


def load_persisted_brief(output_key):
    """Read the exact validated artifact created by the current brief run."""
    response = boto3.client("s3", region_name=os.environ["AWS_REGION"]).get_object(
        Bucket=os.environ["PROCESSED_BUCKET"],
        Key=output_key,
    )
    artifact = json.loads(response["Body"].read().decode("utf-8"))
    return artifact["brief"]


def ask_patient_question(context, question):
    """Use the validated command-line chatbot with the current UI context."""
    with tempfile.TemporaryDirectory() as temporary_directory:
        context_path = Path(temporary_directory) / "context.json"
        context_path.write_text(json.dumps(context, default=str), encoding="utf-8")
        output = run_script(
            [
                sys.executable,
                str(CHAT_SCRIPT),
                "--context",
                str(context_path),
                "--question",
                question,
            ]
        )
    return json.loads(output)


def evidence_by_id(context):
    """Index only records supplied in the active bounded patient context."""
    records = {}
    for record in (context.get("current_note"), context.get("prior_note")):
        if record:
            records[record["resource_id"]] = record

    for section in (
        "recent_encounters",
        "active_conditions",
        "active_medications",
        "events_since_prior_note",
    ):
        for record in context.get(section, []):
            records[record["resource_id"]] = record

    for section in (
        "new_encounters",
        "new_conditions",
        "resolved_conditions",
        "new_medication_records",
        "clinical_events",
    ):
        for record in context.get("changes_since_prior_note", {}).get(section, []):
            records[record["resource_id"]] = record

    for record in context.get("longitudinal_timeline", {}).get("records", []):
        records[record["resource_id"]] = record
    return records


def render_evidence_controls(evidence_ids, key_prefix):
    """Show citations and allow a user to open one in the side inspector."""
    for index, resource_id in enumerate(evidence_ids):
        left, right = st.columns([5, 1])
        left.caption(f"Evidence: `{resource_id}`")
        if right.button("View", key=f"{key_prefix}-{index}-{resource_id}"):
            st.session_state.selected_evidence_id = resource_id
            st.rerun()


def format_record(record):
    description = record.get("description") or record.get("encounter_type") or "No description"
    timestamp = (
        record.get("occurred_at")
        or record.get("event_time")
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
history_years = st.selectbox(
    "History window",
    options=[1, 3, 5, 10],
    index=2,
    format_func=lambda years: f"Last {years} years",
)

if st.button("Load patient context", type="primary") or (
    st.session_state.get("selected_id") != selected_id
    or st.session_state.get("history_years") != history_years
):
    try:
        st.session_state.context = build_context(selected_id, history_years)
        st.session_state.selected_id = selected_id
        st.session_state.history_years = history_years
        st.session_state.pop("brief_result", None)
        st.session_state.chat_messages = []
        st.session_state.pop("selected_evidence_id", None)
    except Exception as error:
        st.error(f"Unable to build context: {error}")

context = st.session_state.get("context")
if (
    not context
    or st.session_state.get("selected_id") != selected_id
    or st.session_state.get("history_years") != history_years
):
    st.info("Select a patient, then choose **Load patient context**.")
    st.stop()

patient = context["patient"]
context_evidence = evidence_by_id(context)

with st.sidebar:
    st.header("Evidence inspector")
    st.caption("Select **View** beside a citation to inspect its bounded source record.")
    selected_evidence_id = st.session_state.get("selected_evidence_id")
    selected_record = context_evidence.get(selected_evidence_id)
    if not selected_record:
        st.info("No evidence record selected.")
    else:
        st.subheader(selected_record.get("resource_type", "FHIR record"))
        st.caption(f"Resource ID: `{selected_evidence_id}`")
        if selected_record.get("source_s3_key"):
            st.caption(f"Source: `{selected_record['source_s3_key']}`")
        if selected_record.get("note_text"):
            st.text_area(
                "Decoded clinical note",
                selected_record["note_text"],
                height=320,
                disabled=True,
            )
        with st.expander("Record fields", expanded=not selected_record.get("note_text")):
            st.json(selected_record)
        if st.button("Clear selected record"):
            st.session_state.pop("selected_evidence_id", None)
            st.rerun()

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

timeline = context["longitudinal_timeline"]
with st.expander(f"Longitudinal timeline — last {timeline['history_years']} years"):
    st.caption(
        "Dated FHIR records are shown newest first. The model may use them as "
        "historical context, but must still cite their resource IDs."
    )
    if not timeline["records"]:
        st.caption("No dated records were found in this time window.")
    for record in timeline["records"]:
        st.markdown(
            f"**{record['resource_type']} — "
            f"{record.get('description') or 'No description'}**  \n"
            f"{record.get('occurred_at') or 'No date'}  \n"
            f"`{record['resource_id']}`"
        )

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
                if not output:
                    raise RuntimeError(
                        "run_brief.py completed without returning run metadata. "
                        "Verify the deployed script is the complete current version."
                    )
                run_metadata = json.loads(output)
                if "processed_output_s3_key" not in run_metadata:
                    raise RuntimeError(
                        "run_brief.py returned unexpected metadata: "
                        + json.dumps(run_metadata)
                    )
                st.session_state.brief_result = {
                    "metadata": run_metadata,
                    "brief": load_persisted_brief(
                        run_metadata["processed_output_s3_key"]
                    ),
                }
            except Exception as error:
                st.error(f"Brief generation failed: {error}")

brief_result = st.session_state.get("brief_result")
if brief_result:
    metadata = brief_result["metadata"]
    brief = brief_result["brief"]
    st.success(f"Validated brief saved as `{metadata['processed_output_s3_key']}`")

    st.subheader("Change summary")
    if brief["change_summary"]:
        for change in brief["change_summary"]:
            st.markdown(f"- {change}")
    else:
        st.caption("No material change was identified in the supplied context.")

    st.subheader("Review items")
    if not brief["review_items"]:
        st.caption("No review items were generated. Human review is still required.")
    for item in brief["review_items"]:
        with st.container(border=True):
            st.markdown(f"**{item['category'].replace('_', ' ').title()}**")
            st.write(item["summary"])
            st.caption(
                f"Confidence: {item['confidence']}"
            )
            render_evidence_controls(
                item["evidence_resource_ids"],
                f"brief-{metadata['run_id']}",
            )

    with st.expander("Run metadata"):
        st.json(metadata)

st.header("Patient-history chat")
st.caption(
    "Answers are limited to this selected synthetic patient's loaded "
    f"{timeline['history_years']}-year context. The tool does not diagnose, "
    "recommend treatment, assess urgency, or take actions."
)

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

for message_index, message in enumerate(st.session_state.chat_messages):
    with st.chat_message(message["role"]):
        st.write(message["content"])
        if message["role"] == "assistant" and message.get("evidence_ids"):
            render_evidence_controls(
                message["evidence_ids"],
                f"chat-{message_index}",
            )

question = st.chat_input("Ask about documented patient history in this time window")
if question:
    st.session_state.chat_messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("Searching bounded patient history..."):
            try:
                answer = ask_patient_question(context, question)
                st.write(answer["answer"])
                if answer["evidence_resource_ids"]:
                    render_evidence_controls(
                        answer["evidence_resource_ids"],
                        f"new-chat-{len(st.session_state.chat_messages)}",
                    )
                st.session_state.chat_messages.append(
                    {
                        "role": "assistant",
                        "content": answer["answer"],
                        "evidence_ids": answer["evidence_resource_ids"],
                    }
                )
            except Exception as error:
                st.error(f"Unable to answer patient-history question: {error}")
