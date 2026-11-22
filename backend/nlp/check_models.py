"""Local model smoke test: run python -m nlp.check_models from backend/."""
from __future__ import annotations
import json
from pathlib import Path
from dotenv import load_dotenv
from nlp.transformer import load_models, predict
from nlp.service import parse_draft

SENTENCE = "Nous avons déplacé 230 plants du lot RO-54321/25 de la chambre 1 vers la serre 5."


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    load_models()
    neural = predict(SENTENCE)
    hybrid = parse_draft(SENTENCE)
    print("CamemBERT:", json.dumps(neural, ensure_ascii=False, indent=2))
    print("SmartTrace draft:", json.dumps(hybrid, ensure_ascii=False, indent=2))
    print("IMPORTANT: no MongoDB write; human confirmation required.")


if __name__ == "__main__":
    main()
