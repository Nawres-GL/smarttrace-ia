"""Load exported Colab CamemBERT models locally. Inference only; no DB writes.

Run from backend/; model folders must already exist under backend/models/.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from nlp.rules import ACTION


def _folder(key: str, default: str) -> Path:
    path = Path(os.getenv(key, default)).expanduser().resolve()
    if not (path.is_dir() and (path / "config.json").is_file()):
        raise FileNotFoundError(f"Missing exported NLP model directory: {path}")
    if not any((path / name).is_file() for name in ("model.safetensors", "pytorch_model.bin")):
        raise FileNotFoundError(f"Missing model weights in: {path}")
    return path


@lru_cache(maxsize=1)
def load_models():
    """Load once per FastAPI process. -1 selects CPU; 0 selects first CUDA GPU."""
    from transformers import pipeline

    intent_dir = _folder("NLP_INTENT_MODEL_DIR", "models/nlp-intent")
    entity_dir = _folder("NLP_ENTITY_MODEL_DIR", "models/nlp-entities")
    device = int(os.getenv("NLP_DEVICE", "-1"))

    classifier = pipeline(
        task="text-classification",
        model=str(intent_dir), tokenizer=str(intent_dir),
        device=device, model_kwargs={"local_files_only": True},
    )
    tagger = pipeline(
        task="token-classification",
        model=str(entity_dir), tokenizer=str(entity_dir),
        aggregation_strategy="simple", device=device,
        model_kwargs={"local_files_only": True},
    )
    return classifier, tagger


def predict(text: str) -> dict:
    """Raw predictions with scores and original-text spans (never a saved event)."""
    classifier, tagger = load_models()
    all_scores = classifier(text, top_k=None, truncation=True, max_length=256)
    ranked = sorted(all_scores, key=lambda x: float(x["score"]), reverse=True)
    if not ranked:
        raise ValueError("Intent classifier returned no labels")

    best = ranked[0]
    intent = best["label"]
    if intent not in ACTION and intent != "HORS_SUJET":
        raise ValueError(f"Unexpected intent label: {intent}")

    spans = []
    for item in tagger(text):
        start, end = int(item["start"]), int(item["end"])
        if not (0 <= start < end <= len(text)):
            continue
        spans.append({
            "label": item["entity_group"],
            "text": text[start:end], "start": start, "end": end,
            "score": round(float(item["score"]), 4),
        })
    return {
        "intent": intent,
        "intent_score": round(float(best["score"]), 4),
        "intent_alternatives": [
            {"label": r["label"], "score": round(float(r["score"]), 4)}
            for r in ranked[:3]
        ],
        "entities": spans,
    }
