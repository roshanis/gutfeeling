"""Gut health survey server (Python standard library only).

    python app.py               # serves http://localhost:8000
    python app.py --port 9000 --db data/responses.db

Endpoints:
    GET  /                    the survey page
    GET  /api/questions       the question config (survey/questions.json)
    POST /api/responses       submit {"answers": {...}}
    GET  /api/export.csv      all responses, one row each, one column per answer
"""
import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from survey import schema, store

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
MAX_BODY = 100_000


def make_handler(conn, export_token=None):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, body, content_type="application/json"):
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, status, obj):
            self._send(status, json.dumps(obj))

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/api/questions":
                # Re-read on every request so edits to questions.json show up without a restart.
                return self._json(200, schema.load_config())
            if path == "/api/export.csv":
                if export_token and f"token={export_token}" not in self.path:
                    return self._json(403, {"error": "forbidden"})
                return self._send(200, store.export_csv(conn, schema.load_config()), "text/csv; charset=utf-8")
            name = "index.html" if path == "/" else path.lstrip("/")
            file = (STATIC / name).resolve()
            if STATIC.resolve() not in file.parents or not file.is_file():
                return self._json(404, {"error": "not found"})
            ctype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            self._send(200, file.read_bytes(), ctype)

        def do_POST(self):
            if self.path != "/api/responses":
                return self._json(404, {"error": "not found"})
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                return self._json(413, {"error": "too large"})
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                config = schema.load_config()
                answers = schema.validate(config, body.get("answers"))
            except json.JSONDecodeError:
                return self._json(400, {"error": "invalid JSON"})
            except schema.ValidationError as exc:
                return self._json(400, {"error": "invalid answers", "fields": exc.errors})
            response_id = store.save(conn, config, answers)
            self._json(201, {"id": response_id})

        def log_message(self, fmt, *args):
            print(f"{self.address_string()} {fmt % args}")

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default=str(ROOT / "data" / "responses.db"))
    parser.add_argument("--export-token", help="if set, /api/export.csv requires ?token=<value>")
    args = parser.parse_args()
    schema.load_config()  # fail fast on a broken questions.json
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    conn = store.connect(args.db)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(conn, args.export_token))
    print(f"Survey running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
