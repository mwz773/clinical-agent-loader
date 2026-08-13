"""Bedrock generation hook with a single JSON-format repair retry."""

import json
import os

from .prompt import SYSTEM_PROMPT, repair_prompt


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


def generate_answer(model_input, model_id, validate, debug=False):
    """Invoke Bedrock, validate output, then attempt one targeted repair."""
    import boto3

    client = boto3.client("bedrock-runtime", region_name=os.environ["AWS_REGION"])
    response = client.converse(
        modelId=model_id,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{
            "role": "user",
            "content": [{"text": json.dumps(model_input, default=str)}],
        }],
        inferenceConfig={"maxTokens": 600, "temperature": 0},
    )
    raw_response = model_text(response)
    try:
        return validate(parse_model_json(raw_response))
    except (ValueError, KeyError) as initial_error:
        repair_response = client.converse(
            modelId=model_id,
            system=[{"text": SYSTEM_PROMPT}],
            messages=[
                {"role": "user", "content": [{"text": json.dumps(model_input, default=str)}]},
                {"role": "assistant", "content": [{"text": raw_response}]},
                {"role": "user", "content": [{"text": repair_prompt(str(initial_error))}]},
            ],
            inferenceConfig={"maxTokens": 600, "temperature": 0},
        )
        repaired_response = model_text(repair_response)
        try:
            return validate(parse_model_json(repaired_response))
        except (ValueError, KeyError) as repair_error:
            if debug:
                raise ValueError(
                    "Initial model response:\n"
                    f"{raw_response}\nRepair model response:\n{repaired_response}\n"
                    "Bedrock response failed validation after one format-repair retry: "
                    f"{repair_error}"
                ) from initial_error
            raise ValueError(
                "Bedrock response failed validation after one format-repair retry: "
                f"{repair_error}"
            ) from initial_error
