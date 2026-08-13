"""Deterministic, no-model-spend input checks for chatbot questions."""


def validate_context(context):
    """Return the active history window or raise for an invalid context."""
    history_years = context.get("longitudinal_timeline", {}).get("history_years")
    if not context.get("patient", {}).get("patient_id") or not history_years:
        raise ValueError("Context must include patient data and a longitudinal timeline.")
    return history_years


def local_refusal(question, history_years):
    """Return a safe refusal for clear policy violations, otherwise None."""
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
