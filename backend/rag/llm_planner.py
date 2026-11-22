"""Optional local LLM to translate unfamiliar questions into audited ExploreIn plans.

The LLM is NEVER trusted with raw MongoDB query expressions or source records.
It returns an allowlisted plan, which FastAPI validates before reading any data.
Disabled unless RAG_USE_LLM_PLANNER=1 and a local Ollama server is configured.
"""
from __future__ import annotations
import json
import os
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from .catalog import CATALOG
from .planner import Plan


def allowed_catalog_summary(user: dict) -> dict:
    """Only give the LLM datasets/fields that the authenticated role is permitted to see."""
    return {key: {'description': spec.description, 'metrics': list(spec.metrics),
                  'grouping': list(spec.dimensions)}
            for key, spec in CATALOG.items() if user.get('role') in spec.roles}


def validate_plan(candidate: dict, user: dict) -> Plan | None:
    """Validate the entire LLM output against a strict catalog; refuse unknown fields."""
    if not isinstance(candidate, dict):
        return None
    dataset = candidate.get('dataset')
    if not isinstance(dataset, str):
        return None
    spec = CATALOG.get(dataset)
    if not spec or user.get('role') not in spec.roles:
        return None
    metric, group = candidate.get('metric'), candidate.get('group_by')
    if not isinstance(metric, str) or (group is not None and not isinstance(group, str)):
        return None
    if metric not in spec.metrics or (group is not None and group not in spec.dimensions):
        return None
    filters = candidate.get('filters', {})
    if (not isinstance(filters, dict) or len(filters) > 8 or
            any(k not in spec.dimensions or not isinstance(v, str) or not v.strip() or len(v) > 120
                for k, v in filters.items())):
        return None
    order = candidate.get('order', 'desc')
    if order not in ('asc', 'desc'):
        return None
    limit = candidate.get('limit', 10)
    if type(limit) is not int or limit < 1 or limit > 50:
        return None
    threshold = candidate.get('threshold')
    if threshold is not None:
        if type(threshold) not in (float, int) or not -1e6 <= threshold <= 1e6:
            return None
    return Plan(dataset, metric, group, filters, order, threshold, limit,
                reason='Plan proposé par LLM local, validé sur catalogue')


def propose_plan(question: str, user: dict) -> Plan | None:
    """Ask local Ollama for constrained JSON and verify before it can reach explorer."""
    if os.getenv('RAG_USE_LLM_PLANNER', '0') != '1':
        return None
    catalog = allowed_catalog_summary(user)
    if not catalog:
        return None
    root = os.getenv('RAG_OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')
    parsed = urlparse(root)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.username:
        return None
    prompt = ('Convertis cette question française en un plan JSON, sans aucun commentaire. '
              'Utilise UNIQUEMENT le catalogue disponible; ne crée ni SQL ni MongoDB. '
              'Si les champs disponibles ne peuvent répondre, réponds {}. '
              'Clés: dataset, metric, group_by, filters, order, threshold, limit. '
              'Ne déduis pas des valeurs absentes de la question.\n'
              'CATALOGUE: ' + json.dumps(catalog, ensure_ascii=False)[:12_000] +
              '\nQUESTION: ' + question[:800])
    body = {'model': os.getenv('RAG_OLLAMA_MODEL', 'qwen2.5:3b'), 'stream': False,
            'format': 'json',
            'messages': [{'role': 'system', 'content': 'Tu es un planificateur JSON, pas un exécuteur.'},
                         {'role': 'user', 'content': prompt}],
            'options': {'temperature': 0, 'num_predict': 320}}
    req = Request(root + '/api/chat', data=json.dumps(body).encode('utf-8'),
                  headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urlopen(req, timeout=12) as reply:
            raw = json.loads(reply.read(65_536).decode('utf-8'))
        draft = json.loads(str(raw.get('message', {}).get('content', '{}')))
        return validate_plan(draft, user)
    except (OSError, ValueError, TypeError, KeyError):
        return None
