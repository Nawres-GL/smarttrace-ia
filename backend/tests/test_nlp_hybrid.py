"""Test SmartTrace's model/result handling without downloading CamemBERT."""
import sys
import types

from nlp.service import parse_draft


S = "Nous avons déplacé 230 plants du lot RO-54321/25 de la chambre 1 vers la serre 5."


def fake(monkeypatch, *, score, label="TRANSFERT", entity_score=0.07):
    def predict(text):
        return {"intent": label, "intent_score": score,
                "intent_alternatives": [{"label": label, "score": score}],
                "entities": [{"label": "ORIGIN", "text": "1", "start": 63,
                              "end": 64, "score": entity_score}]}
    monkeypatch.setitem(sys.modules, "nlp.transformer", types.SimpleNamespace(predict=predict))
    monkeypatch.setenv("NLP_MODE", "hybrid")


def test_low_score_does_not_override_clear_transfer(monkeypatch):
    fake(monkeypatch, score=0.42)
    draft = parse_draft(S)
    assert draft["action"] == "transfer"
    assert draft["fields"]["quantity"] == 230
    assert draft["fields"]["origin"] == "CHAMBRE-01"
    assert draft["fields"]["destination"] == "SERRE-05"
    assert any("faible" in w for w in draft["warnings"])


def test_high_score_wrong_entity_cannot_change_origin(monkeypatch):
    fake(monkeypatch, score=0.95, entity_score=0.99)
    draft = parse_draft(S)
    assert draft["fields"]["origin"] == "CHAMBRE-01"


def test_intent_conflict_blocks_draft(monkeypatch):
    fake(monkeypatch, score=0.98, label="PERTES")
    draft = parse_draft(S)
    assert draft["action"] is None
    assert any("Désaccord" in w for w in draft["warnings"])
