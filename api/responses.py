import os
import sys
from http.server import BaseHTTPRequestHandler

# Make the repo root importable so this function can use the survey package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from survey import web  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        web.send(self, web.post_response(web.read_body(self)))
