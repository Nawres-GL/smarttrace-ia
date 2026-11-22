"""Phase 7 V4 — human-friendly RAG: exact records + governed analysis + approved docs.

The API never issues writes and never treats Excel history as blockchain proof.
Requests are authenticated; Excel remains admin-only and MongoDB site-scoped.
"""
from __future__ import annotations
import os
import re
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from app.auth import authenticated_user
from .schemas import QuestionIn, ExploreIn
from .catalog import public_catalog, FILTER_LABELS
from .planner import Plan, maybe_plan, norm
from .source_selection import alternative_for_empty, fallback_notice
from .explorer import explore, ForbiddenExplore, InvalidExplore
from .presentation import present_explore, present_document
from .structured import structured_search, code_from_question
from .documents import search_documents, document_status
from .llm import synthesize
from .llm_planner import propose_plan

router = APIRouter(prefix='/api/rag', tags=['RAG · consultation et exploration'])


def _database(request: Request):
    """Get the app's configured MongoDB database; never open a second unscoped client."""
    db = getattr(request.app.state, 'db', None)
    if db is None:
        raise HTTPException(503, 'MongoDB Atlas requis pour SmartTrace.')
    return db


def _run_explore(body: ExploreIn, user: dict, db):
    """Apply catalog and access checks to deterministic calculations."""
    try:
        return explore(body.dataset, body.metric, body.group_by, body.filters,
                       user, db, limit=body.limit, offset=body.offset,
                       order=body.order, threshold=body.threshold)
    except ForbiddenExplore:
        raise HTTPException(403, 'Jeu de données ou site non autorisé.')
    except InvalidExplore as exc:
        raise HTTPException(422, str(exc))
    except (FileNotFoundError, OSError) as exc:
        raise HTTPException(503, 'Source historique indisponible.') from exc


def _execute_plan(plan: Plan, user: dict, db) -> dict:
    """Execute only catalog-defined projections and metrics, never LLM-generated commands."""
    return _run_explore(ExploreIn(dataset=plan.dataset, metric=plan.metric,
                                  group_by=plan.group_by, filters=plan.filters,
                                  order=plan.order, threshold=plan.threshold,
                                  limit=plan.limit), user, db)


def _is_document_question(q: str) -> bool:
    """Prioritize procedural 'how/why' questions over analytic keyword collisions."""
    normalized = norm(q)
    return (any(x in normalized for x in ('comment fonctionne', 'quelles sont les etapes',
            'quelle procedure', 'comment proceder', 'explique ', 'pourquoi ',
            'quelles regles', 'que signifie', 'definition de', 'comment faire'))
            and not any(x in normalized for x in ('combien', 'quel taux', 'moyenne', 'statistique')))


def _answer_documents(question: str, user: dict) -> dict:
    """Retrieve approved passages and optionally synthesize a cited explanation."""
    try:
        matches, mode = search_documents(question, user)
    except (OSError, ValueError):
        raise HTTPException(503, 'Index documentaire indisponible; vérifier les fichiers.')
    sources = [{'id': chunk.id, 'kind': 'document', 'title': chunk.title,
                'excerpt': chunk.content[:1100], 'file': chunk.file_name,
                'retrieval_score': score} for chunk, score in matches[:5]]
    if not sources:
        return present_document(
            'Je n’ai pas trouvé de document approuvé répondant à cette question. '
            'Demandez à un administrateur de vérifier le dossier rag_documents et son manifeste.',
            [], mode, ['Aucune réponse inventée. Vérifiez l’index documentaire via /api/rag/status.'])
    generated, generation_mode = synthesize(question, sources)
    if generated:
        cited = [int(n) for n in re.findall(r'\[(\d+)\]', generated)]
        if not cited or any(n < 1 or n > len(sources) for n in cited):
            generated = None  # Unverifiable source numbers cannot be displayed as fact.
    if not generated:
        first = sources[0]
        # Natural, concise fallback even without Ollama; source remains separately visible.
        snippet = first['excerpt'].replace('#', '').strip()[:1000]
        generated = f'Selon « {first["title"]} » :\n{snippet}\n\nVoir la source [1] pour le contexte.'
    result = present_document(generated, sources, mode)
    result['generation_mode'] = generation_mode if generated and generation_mode == 'ollama' else 'document_extractif'
    result['read_only'] = True
    return result


@router.get('/status')
def status(response: Response, user=Depends(authenticated_user)):
    """Safe diagnostics to distinguish missing documents from retrieval failure."""
    response.headers['Cache-Control'] = 'no-store'
    return {'ready': True, 'read_only': True,
            'llm_enabled': os.getenv('RAG_USE_OLLAMA', '0') == '1',
            'llm_planner_enabled': os.getenv('RAG_USE_LLM_PLANNER', '0') == '1',
            'semantic_enabled': os.getenv('RAG_USE_EMBEDDINGS', '0') == '1',
            'historical_access': user.get('role') == 'admin',
            'documents': document_status(user),
            'note': 'Excel historique non certifié; réservé aux administrateurs.'}


@router.get('/catalog')
def catalog(response: Response, user=Depends(authenticated_user)):
    """Return only datasets and fields that this user's role can query."""
    response.headers['Cache-Control'] = 'no-store'
    return public_catalog(user)


@router.post('/explore')
def explore_data(body: ExploreIn, request: Request, response: Response,
                 user=Depends(authenticated_user)):
    """Run a user-selected, catalog-limited query from the structured Data Explorer."""
    response.headers['Cache-Control'] = 'no-store'
    result = _run_explore(body, user, _database(request))
    return present_explore(result, body.dataset, body.metric, body.filters)


@router.post('/ask')
def ask(body: QuestionIn, request: Request, response: Response,
        user=Depends(authenticated_user)):
    """Orchestrate lot lookup, governed analytics and approved-document RAG.

    Crucial safety property: empty operational results are NOT interpreted as
    absence of historical data, and fallback never merges incompatible units.
    """
    response.headers['Cache-Control'] = 'no-store'
    db = _database(request)
    question = body.question.strip()
    q = norm(question)
    if code_from_question(question):
        answer, sources, route, warnings = structured_search(question, db, user)
        if answer is not None:
            return {'answer': answer, 'summary': answer, 'route': route, 'sources': sources,
                    'warnings': warnings, 'read_only': True, 'status': 'ok',
                    'retrieval_mode': 'lot_exact', 'generation_mode': 'deterministe'}

    if any(phrase in q for phrase in ('quelles donnees', 'quels jeux de donnees',
                                      'que puis-je demander', 'que peux-tu interroger')):
        allowed = public_catalog(user)['datasets']
        text = ('Voici les données que vous pouvez consulter : ' +
                '; '.join(item['label'] for item in allowed) +
                '. Utilisez « Explorer les données » pour choisir les mesures et filtres.')
        return {'answer': text, 'summary': text, 'route': 'catalogue',
                'sources': [], 'warnings': [], 'status': 'ok', 'read_only': True}

    if _is_document_question(question):
        return _answer_documents(question, user)

    plan = maybe_plan(question, user.get('role'))
    if plan is None:
        plan = propose_plan(question, user)  # Optional local JSON proposal, schema-validated.
    if plan is None:
        if any(x in q for x in ('combien', 'nombre', 'taux', 'quantite', 'statistique',
                                 'total', 'moyenne', 'classement', 'repartition')):
            msg = ('Je ne peux pas calculer cet indicateur avec les champs autorisés disponibles. '
                   'Vous pouvez consulter le catalogue et choisir une mesure dans « Explorer les données ». '
                   'Aucune valeur n’a été estimée.')
            return {'answer': msg, 'summary': msg, 'route': 'analyse_non_disponible',
                    'status': 'not_supported', 'sources': [], 'warnings': [], 'read_only': True}
        return _answer_documents(question, user)
    result = _execute_plan(plan, user, db)
    applied = plan
    notice = ''
    if (result.get('meta', {}).get('total_groups', 0) == 0 and
            result.get('meta', {}).get('complete_scan') is True):
        alternative = alternative_for_empty(plan, question, user)
        if alternative is not None:
            try:
                alternate_result = _execute_plan(alternative, user, db)
            except HTTPException as exc:
                if exc.status_code != 503:
                    raise
                result.setdefault('warnings', []).append(
                    'La source historique est temporairement indisponible; résultat opérationnel seulement.')
                alternate_result = None
            if alternate_result and alternate_result.get('meta', {}).get('total_groups', 0):
                result, applied = alternate_result, alternative
                notice = fallback_notice(plan, alternative)

    result = present_explore(result, applied.dataset, applied.metric, applied.filters,
                             notice=notice)
    result['interpreted_query'] = {'dataset': applied.dataset, 'metric': applied.metric,
                                   'group_by': applied.group_by, 'filters': applied.filters}
    result['route'] = f'analytics:{applied.dataset}'
    result['read_only'] = True
    if notice:
        result['fallback_from'] = plan.dataset
    # Multi-dimensional question yields separate evidence panels, never ambiguous combined totals.
    panels = []
    if applied.extra_groups:
        panels.append({'title': f'Vue par {FILTER_LABELS.get(applied.group_by, applied.group_by).lower()}', 'result': result.get('table')})
        for grouping in applied.extra_groups:
            other = Plan(applied.dataset, applied.metric, grouping, applied.filters,
                         applied.order, applied.threshold, applied.limit)
            sub = present_explore(_execute_plan(other, user, db),
                                  applied.dataset, applied.metric, applied.filters)
            panels.append({'title': f'Vue par {FILTER_LABELS.get(grouping, grouping).lower()}', 'result': sub.get('table'),
                           'sources': sub.get('sources', []), 'warnings': sub.get('warnings', [])})
        result['panels'] = panels
        result['answer'] += '\nDeux regroupements sont présentés séparément ci-dessous.'
    return result
