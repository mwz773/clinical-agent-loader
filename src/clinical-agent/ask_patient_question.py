"""Compatibility CLI wrapper for the modular patient-history chatbot."""

import json
import sys
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from patient_history_chatbot.cli import main  # noqa: E402


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status": "failed", "error": str(error)}), file=sys.stderr)
        raise SystemExit(1)
