"""Local-only bridge client. Never put Fabric private keys in the FastAPI service."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

class FabricBridgeError(Exception):
    pass


def _settings():
    url = os.getenv('FABRIC_BRIDGE_URL', '').rstrip('/')
    token = os.getenv('FABRIC_BRIDGE_TOKEN', '')
    # Dev safeguard: no SSRF or public address. Bridge binds to loopback only.
    if url not in ('http://127.0.0.1:8787', 'http://localhost:8787'):
        raise FabricBridgeError('Passerelle Fabric locale non configurée.')
    if len(token) < 32 or token.startswith('REPLACE_'):
        raise FabricBridgeError('FABRIC_BRIDGE_TOKEN absent ou trop court.')
    return url, token


def _request(method, path, body=None):
    url, token = _settings()
    payload = json.dumps(body).encode('utf-8') if body is not None else None
    request = Request(url + path, data=payload, method=method,
                      headers={'Authorization': 'Bearer ' + token,
                               'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=70) as response:
            return json.loads(response.read(8192))
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise FabricBridgeError('Passerelle Fabric indisponible ou transaction non confirmée.') from exc


def read_proof(event_id):
    return _request('GET', '/internal/events/' + quote(event_id, safe=''))


def submit_proof(event):
    return _request('POST', '/internal/events', {
        'eventId': event['_id'], 'subjectId': event['subjectId'],
        'eventType': event['eventType'], 'eventHash': event['eventHash']
    })


def proof_matches(proof, event):
    return (isinstance(proof, dict)
            and proof.get('eventId') == event['_id']
            and proof.get('subjectId') == event['subjectId']
            and proof.get('eventType') == event['eventType']
            and proof.get('eventHash') == event['eventHash']
            and bool(proof.get('transactionId')))
