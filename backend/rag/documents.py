"""Small document index with document ACLs checked BEFORE retrieval.

Only files explicitly enumerated in backend/rag_documents/manifest.json are read.
Metadata is administrator-managed on disk, not supplied by the chat user.
"""
from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'rag_documents'
ROLES = {'admin', 'production', 'qualite', 'logistique', 'lecture'}
MAX_DOCS = 100
MAX_BYTES_PER_DOCUMENT = 120_000
MAX_CHUNKS = 1000


@dataclass(frozen=True)
class Chunk:
    id: str
    title: str
    content: str
    roles: tuple[str, ...]
    sites: tuple[str, ...]
    file_name: str


def text_tokens(text: str) -> list[str]:
    plain = ''.join(ch for ch in unicodedata.normalize('NFKD', text.lower())
                    if not unicodedata.combining(ch))
    return re.findall(r'[a-z0-9]{2,}', plain)


def _split(text: str, max_len: int = 850, overlap: int = 110) -> list[str]:
    text = re.sub(r'\r\n?', '\n', text).strip()
    # Keep nearby context with a modest overlap; do not cut long words unnecessarily.
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_len)
        if end < len(text):
            cut = text.rfind(' ', start + max_len // 2, end)
            if cut > start:
                end = cut
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def load_chunks(root: Path = ROOT) -> list[Chunk]:
    manifest_path = root / 'manifest.json'
    if not manifest_path.is_file():
        return []
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    entries = manifest.get('documents', [])
    if not isinstance(entries, list) or len(entries) > MAX_DOCS:
        raise ValueError('Manifest RAG invalide ou trop volumineux.')
    root_real = root.resolve()
    chunks = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('Entrée du manifeste RAG invalide.')
        name = entry.get('file', '')
        roles = entry.get('roles', [])
        sites = entry.get('sites', [])
        if (not isinstance(name, str) or not name.endswith('.md') or
                not isinstance(roles, list) or not roles or not set(roles) <= ROLES or
                not isinstance(sites, list) or any(not isinstance(x, str) for x in sites)):
            raise ValueError('Manifeste RAG : fichier/rôles/sites invalides.')
        file_path = (root_real / name).resolve()
        if not file_path.is_relative_to(root_real) or not file_path.is_file():
            raise ValueError('Document non autorisé ou introuvable dans le manifeste.')
        if file_path.stat().st_size > MAX_BYTES_PER_DOCUMENT:
            raise ValueError('Document RAG trop volumineux.')
        body = file_path.read_text(encoding='utf-8')
        title = str(entry.get('title') or name)[:120]
        for idx, piece in enumerate(_split(body), 1):
            chunks.append(Chunk(f'doc:{name}:{idx}', title, piece, tuple(roles),
                                tuple(sites), name))
            if len(chunks) > MAX_CHUNKS:
                raise ValueError('Trop de blocs de documents RAG.')
    return chunks


def visible(chunk: Chunk, user: dict) -> bool:
    if user.get('role') not in chunk.roles:
        return False
    if chunk.sites and user.get('role') != 'admin':
        return bool(set(chunk.sites) & set(user.get('siteCodes', [])))
    return True


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(os.getenv('RAG_EMBEDDING_MODEL',
                     'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'), device='cpu')


# Common French function words are unhelpful when searching internal procedures.
STOPWORDS = set('le la les de du des un une et ou est dans pour sur par avec comment quelles quels quelle quel '
                'avant apres aux au ce cette ces en votre nos nous vous a sont que qui cela plus etre'.split())


def lexical_rank(question: str, items: list[Chunk], k: int = 6) -> list[tuple[Chunk, float]]:
    """Simple lexical ranking that emphasizes actual topic terms and titles."""
    from collections import Counter
    query = [w for w in text_tokens(question) if w not in STOPWORDS]
    if not query:
        return []
    q = set(query)
    ranked = []
    for item in items:
        title = Counter(w for w in text_tokens(item.title) if w not in STOPWORDS)
        body = Counter(w for w in text_tokens(item.content) if w not in STOPWORDS)
        matched = q.intersection(set(title) | set(body))
        if not matched:
            continue
        # A single generic token is not enough to justify a document answer.
        if len(q) >= 3 and len(matched) < 2:
            continue
        score = sum((3.0 if title.get(w) else 0.0) + (1.0 + math.log1p(body[w]) if body[w] else 0.0)
                    for w in matched) / max(1.0, len(q))
        ranked.append((item, score))
    return sorted(ranked, key=lambda p: p[1], reverse=True)[:k]


@lru_cache(maxsize=8)
def _cached_vectors(items: tuple[Chunk, ...]):
    # Cache is scoped to an already ACL-filtered tuple of immutable chunks.
    return _model().encode([c.content + '\n' + c.title for c in items], normalize_embeddings=True)


def search_documents(question: str, user: dict, root: Path = ROOT, k: int = 5):
    """ACLs are enforced before lexical *or* embedding retrieval."""
    allowed = [c for c in load_chunks(root) if visible(c, user)]
    if not allowed:
        return [], 'aucun_document_autorise'
    lexical = lexical_rank(question, allowed, max(k * 2, 8))
    if os.getenv('RAG_USE_EMBEDDINGS', '0') == '0':
        return lexical[:k], 'lexical'
    try:
        import numpy as np
        model = _model()
        vectors = _cached_vectors(tuple(allowed))
        query_vec = model.encode([question], normalize_embeddings=True)[0]
        scores = np.asarray(vectors) @ np.asarray(query_vec)
        min_sem = float(os.getenv('RAG_DOC_MIN_SIMILARITY', '0.24'))
        lexical_scores = {c.id: v for c, v in lexical}
        max_lex = max(lexical_scores.values(), default=1.0)
        ranked = []
        for i, item in enumerate(allowed):
            similarity = float(scores[i])
            lex = lexical_scores.get(item.id, 0.0)
            # A lexical match must remain accessible even with weak embeddings.
            if similarity < min_sem and not lex:
                continue
            combined = 0.65 * max(0.0, similarity) + 0.35 * (lex/max_lex if lex else 0)
            ranked.append((item, round(combined, 3)))
        return sorted(ranked, key=lambda p: p[1], reverse=True)[:k], 'hybride_lexical_semantique'
    except (ImportError, OSError, RuntimeError, ValueError):
        return lexical[:k], 'lexical_fallback'


def document_status(user: dict, root: Path = ROOT) -> dict:
    """Report whether the approved document index is installed for this role.

    No document body or unauthorized filename is exposed to other roles.
    """
    try:
        if not (root / 'manifest.json').is_file():
            return {'ready': False, 'visible_documents': 0,
                    'hint': 'backend/rag_documents/manifest.json absent.'}
        chunks = [item for item in load_chunks(root) if visible(item, user)]
        return {'ready': bool(chunks),
                'visible_documents': len({item.file_name for item in chunks}),
                'visible_passages': len(chunks),
                'hint': ('Index documentaire accessible.' if chunks
                         else 'Aucun document approuvé accessible pour votre rôle/site.')}
    except (OSError, ValueError, json.JSONDecodeError):
        return {'ready': False, 'visible_documents': 0,
                'hint': 'Manifeste ou documents invalides; vérifier les fichiers et les droits.'}
