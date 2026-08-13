"""CLI entry point for patient-history chatbot evaluation."""

import argparse
import json
import os
import sys
from pathlib import Path

from .service import answer_question


def main():
    parser = argparse.ArgumentParser(
        description="Ask one evidence-cited question about bounded patient history."
    )
    parser.add_argument("--context", required=True, help="JSON output from build_context.py")
    parser.add_argument("--question", required=True, help="One patient-history question")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--model-id", default=os.environ.get("BEDROCK_MODEL_ID"))
    args = parser.parse_args()
    if not args.model_id:
        parser.error("Set --model-id or BEDROCK_MODEL_ID.")

    context = json.loads(Path(args.context).read_text(encoding="utf-8"))
    answer = answer_question(context, args.question, args.model_id, args.debug)
    print(json.dumps(answer, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status": "failed", "error": str(error)}), file=sys.stderr)
        raise SystemExit(1)
