"""Evidence allow-list construction and response validation."""


def allowed_evidence_by_id(context):
    """Return only resource IDs supplied in the active bounded context."""
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

    for section in (
        "new_encounters",
        "new_conditions",
        "resolved_conditions",
        "new_medication_records",
        "clinical_events",
    ):
        for item in context.get("changes_since_prior_note", {}).get(section, []):
            evidence[item["resource_id"]] = item

    for item in context.get("longitudinal_timeline", {}).get("records", []):
        evidence[item["resource_id"]] = item

    return evidence


def validate_response(response, context, allowed_evidence):
    """Reject malformed, out-of-window, or unsupported model responses."""
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
