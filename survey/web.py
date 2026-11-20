"""Request handling shared by the local server (app.py) and the Vercel
functions in api/. Each function returns (status, content_type, body)."""
import hmac
import json
import os
from urllib.parse import parse_qs, urlsplit

from . import schema, store

MAX_BODY = 100_000
JSON = "application/json"
_store = None


def get_store():
    global _store
    if _store is None:
        _store = store.open_store()
    return _store


def _json(status, obj):
    return status, JSON, json.dumps(obj)


def get_questions():
    return _json(200, schema.load_config())


def post_response(raw_body):
    if len(raw_body) > MAX_BODY:
        return _json(413, {"error": "too large"})
    try:
        body = json.loads(raw_body or b"{}")
        config = schema.load_config()
        answers = schema.validate(config, body.get("answers") if isinstance(body, dict) else None)
    except json.JSONDecodeError:
        return _json(400, {"error": "invalid JSON"})
    except schema.ValidationError as exc:
        return _json(400, {"error": "invalid answers", "fields": exc.errors})
    return _json(201, {"id": get_store().save(config, answers)})


def export(path, headers, required_token=None):
    """CSV export. Needs EXPORT_TOKEN (sent as ?token= or 'Authorization: Bearer').
    Without a token configured it is only allowed when explicitly local."""
    token = required_token if required_token is not None else os.environ.get("EXPORT_TOKEN")
    if token is None:
        if os.environ.get("VERCEL"):
            return _json(403, {"error": "export disabled: set EXPORT_TOKEN"})
    else:
        given = parse_qs(urlsplit(path).query).get("token", [""])[0]
        auth = headers.get("Authorization") or ""
        if auth.startswith("Bearer "):
            given = auth[len("Bearer "):]
        if not hmac.compare_digest(given.encode(), token.encode()):
            return _json(403, {"error": "forbidden"})
    return 200, "text/csv; charset=utf-8", store.export_csv(get_store(), schema.load_config())


def send(handler, result, extra_headers=None):
    status, content_type, body = result
    data = body if isinstance(body, bytes) else body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    for k, v in (extra_headers or {}).items():
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(data)


def read_body(handler):
    length = int(handler.headers.get("Content-Length") or 0)
    if length > MAX_BODY:
        return b"x" * (MAX_BODY + 1)
    return handler.rfile.read(length)
