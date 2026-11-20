"""Run the survey locally (Python standard library; SQLite by default).

    python app.py               # serves http://127.0.0.1:8000
    python app.py --port 9000 --db data/responses.db

On Vercel the same logic runs through the functions in api/ instead.

Endpoints:
    GET  /                    the survey page (public/)
    GET  /api/questions       the question config (survey/questions.json)
    POST /api/responses       submit {"answers": {...}}
    GET  /api/export.csv      all responses as CSV (needs EXPORT_TOKEN if set)
"""
import argparse
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from survey import schema, web

PUBLIC = Path(__file__).parent / "public"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/questions":
            return web.send(self, web.get_questions())
        if path in ("/api/export.csv", "/api/export"):
            return web.send(self, web.export(self.path, self.headers))
        name = "index.html" if path == "/" else path.lstrip("/")
        file = (PUBLIC / name).resolve()
        if PUBLIC.resolve() not in file.parents or not file.is_file():
            return web.send(self, (404, web.JSON, '{"error": "not found"}'))
        ctype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        web.send(self, (200, ctype, file.read_bytes()))

    def do_POST(self):
        if self.path != "/api/responses":
            return web.send(self, (404, web.JSON, '{"error": "not found"}'))
        web.send(self, web.post_response(web.read_body(self)))

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", help="SQLite file (default data/responses.db; ignored if DATABASE_URL is set)")
    args = parser.parse_args()
    if args.db:
        os.environ["SQLITE_PATH"] = args.db
    schema.load_config()  # fail fast on a broken questions.json
    web.get_store()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Survey running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
