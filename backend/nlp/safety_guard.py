"""Conservative text safety flags for SmartTrace draft creation.

This is a *review gate*, not an action parser and NOT a proof of safety.
It must run BEFORE any form can be accepted; FastAPI permissions and stock
validation remain authoritative. False positives intentionally ask for review.
"""
from __future__ import annotations
import re
import unicodedata


def normalize(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s.lower())
                   if unicodedata.category(c) != 'Mn').replace('’', "'")

OPERATION_STEMS = {
    'TRANSFERT': r'\b(?:transfer\w*|deplac\w*|mouv(?:ement|oir))\b',
    'SEMIS': r'\b(?:semer|semis|ensemenc\w*)\b',
    'GERMINATION': r'\b(?:germin\w*|levee|lever|pouss\w*)\b',
    'PERTES': r'\b(?:pertes?|perd\w*|detruit\w*|detruir\w*)\b',
    'INTERVENTION': r'\b(?:traitement\w*|traiter|appliqu\w*|entretien)\b',
    'GREFFAGE': r'\b(?:greff\w*)\b',
    'CONTROLE_QUALITE': r'\b(?:controle\s+qualite|inspection|inspect\w*)\b',
    'PREPARATION': r'\b(?:prepar\w*|reserv\w*|conditionn\w*)\b',
    'LIVRAISON': r'\b(?:livr\w*|expedi\w*)\b',
    'RETOUR': r'\b(?:retourn\w*|retour\w*)\b',
    'RECEPTION_SEMENCES': r'\b(?:reception\w*|arrivage|recu\w*)\b',
}
NEGATION = re.compile(r"\b(?:ne\s+|n')(?:\S+\s+){0,5}(?:pas|jamais|plus)\b|\b(?:annulee?s?|interdit|pas\s+de\s+transfert)\b")
QUESTION = re.compile(r"\?|\b(?:est.ce\s+que|faut.il|pourquoi|comment|pouvez.vous\s+m'expliquer)\b")


def assess_instruction(text: str) -> dict:
    """Return REQUIRES_REVIEW on negation/questions/possible multiple operations.

    Deliberately doesn't submit, mutate, or resolve anything.
    """
    text_norm=normalize(text)
    kinds=sorted(label for label,pattern in OPERATION_STEMS.items()
                 if re.search(pattern,text_norm))
    reasons=[]
    if NEGATION.search(text_norm):reasons.append('NEGATION_OU_ANNULATION')
    if QUESTION.search(text_norm):reasons.append('QUESTION_OU_DEMANDE_EXPLICATION')
    if len(kinds)>1:reasons.append('OPERATIONS_MULTIPLES_POSSIBLES')
    return {
        'status':'REQUIRES_REVIEW' if reasons else 'NO_SIMPLE_RISK_DETECTED',
        'reasons':reasons,
        'operation_keywords_detected':kinds,
        'note':'Aucun résultat ne permet une exécution automatique.'
    }

if __name__=='__main__':
    for s in [
      'Ne transférez pas 500 plants du lot 12345.',
      'Transférer 60 plants vers serre 7 et livrer 25 plants demain.',
      'Nous avons déplacé 230 plants du lot RO-54321/25.',
      'Est-ce que nous devons préparer cette commande ?',
    ]:
        print(s, assess_instruction(s))
