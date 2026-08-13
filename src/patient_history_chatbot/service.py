"""Service orchestration for one bounded patient-history question."""

from .generation import generate_answer
from .input_guardrail import local_refusal, validate_context
from .output_guardrail import allowed_evidence_by_id, validate_response


def answer_question(context, question, model_id, debug=False):
    """Apply input, generation, and output hooks for one question."""
    history_years = validate_context(context)
    refusal = local_refusal(question, history_years)
    if refusal:
        return refusal

    allowed_evidence = allowed_evidence_by_id(context)
    model_input = {
        "question": question,
        "context": context,
        "required_history_window_years": history_years,
        "allowed_evidence_resource_ids": sorted(allowed_evidence),
    }
    return generate_answer(
        model_input=model_input,
        model_id=model_id,
        validate=lambda response: validate_response(response, context, allowed_evidence),
        debug=debug,
    )
