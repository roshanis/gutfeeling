import csv
import io
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock
from http.server import ThreadingHTTPServer

import app
from api import export as api_export
from api import questions as api_questions
from api import responses as api_responses
from survey import schema, store, web

VALID = {
    "age": 34, "gender": "female", "height": 165, "country": "USA", "education": "bachelor",
    "smoking_status": "current", "tobacco_products": ["vaping", "cigarettes"], "smoking_frequency": "daily",
    "alcohol_frequency": "never",
    "chronic_conditions": ["ibs"], "medications": ["none"], "surgeries": ["none"], "therapies": ["none"],
    "food_allergies": ["none"], "food_intolerances": ["lactose"],
    "diet_type": "vegetarian", "breakfast_frequency": "most_days", "meals_per_day": 3, "snacking": "rarely",
    "bloating_frequency": "weekly",
}


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.config = schema.load_config()

    def test_config_is_valid(self):
        ids = [q["id"] for q in schema.iter_questions(self.config)]
        self.assertEqual(len(ids), len(set(ids)))

    def test_valid_answers_pass_and_multi_is_ordered(self):
        cleaned = schema.validate(self.config, VALID)
        self.assertEqual(cleaned["tobacco_products"], ["cigarettes", "vaping"])

    def test_required_missing(self):
        answers = dict(VALID)
        del answers["age"]
        with self.assertRaises(schema.ValidationError) as ctx:
            schema.validate(self.config, answers)
        self.assertIn("age", ctx.exception.errors)

    def test_hidden_answers_are_dropped(self):
        answers = dict(VALID, smoking_status="never")
        cleaned = schema.validate(self.config, answers)
        self.assertNotIn("tobacco_products", cleaned)
        self.assertNotIn("smoking_frequency", cleaned)

    def test_conditional_required(self):
        answers = dict(VALID)
        del answers["tobacco_products"]
        with self.assertRaises(schema.ValidationError) as ctx:
            schema.validate(self.config, answers)
        self.assertIn("tobacco_products", ctx.exception.errors)

    def test_bad_values(self):
        for qid, bad in [("age", 5), ("age", "abc"), ("gender", "robot"), ("medications", ["none", "statins"]),
                         ("chronic_conditions", "ibs"), ("height", 400)]:
            with self.assertRaises(schema.ValidationError, msg=qid):
                schema.validate(self.config, dict(VALID, **{qid: bad}))

    def test_unknown_question_rejected(self):
        with self.assertRaises(schema.ValidationError):
            schema.validate(self.config, dict(VALID, hacker="x"))

    def test_flatten_one_hot(self):
        row = schema.flatten(self.config, schema.validate(self.config, VALID))
        self.assertEqual(row["chronic_conditions__ibs"], 1)
        self.assertEqual(row["chronic_conditions__none"], 0)
        self.assertEqual(row["height_cm"], 165)
        self.assertIsNone(row["alcohol_drinks_per_day"])
        self.assertEqual(set(row), set(schema.columns(self.config)))


class ServerTests(unittest.TestCase):
    """Runs the local server and the Vercel function handlers against SQLite."""

    @classmethod
    def setUpClass(cls):
        web._store = store.SqliteStore(":memory:")
        cls.servers = {}
        for name, handler in [("app", app.Handler), ("questions", api_questions.handler),
                              ("responses", api_responses.handler), ("export", api_export.handler)]:
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            cls.servers[name] = server

    @classmethod
    def tearDownClass(cls):
        for server in cls.servers.values():
            server.shutdown()
        web._store = None

    def url(self, name, path):
        return f"http://127.0.0.1:{self.servers[name].server_address[1]}{path}"

    def post(self, name, answers):
        req = urllib.request.Request(self.url(name, "/api/responses"),
                                     data=json.dumps({"answers": answers}).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def get(self, name, path, headers=None):
        req = urllib.request.Request(self.url(name, path), headers=headers or {})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_submit_and_export_local(self):
        status, body = self.post("app", VALID)
        self.assertEqual(status, 201)
        status, text = self.get("app", "/api/export.csv")
        self.assertEqual(status, 200)
        row = next(x for x in csv.DictReader(io.StringIO(text)) if x["response_id"] == body["id"])
        self.assertEqual(row["tobacco_products__vaping"], "1")
        self.assertEqual(row["diet_type"], "vegetarian")

    def test_vercel_functions(self):
        status, text = self.get("questions", "/api/questions")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(text)["title"], schema.load_config()["title"])
        status, body = self.post("responses", VALID)
        self.assertEqual(status, 201)
        status, body = self.post("responses", {"age": 30})
        self.assertEqual(status, 400)
        self.assertIn("gender", body["fields"])

    def test_export_token(self):
        with mock.patch.dict(os.environ, {"EXPORT_TOKEN": "s3cret"}):
            self.assertEqual(self.get("export", "/api/export")[0], 403)
            self.assertEqual(self.get("export", "/api/export?token=wrong")[0], 403)
            self.assertEqual(self.get("export", "/api/export?token=s3cret")[0], 200)
            status, _ = self.get("export", "/api/export", {"Authorization": "Bearer s3cret"})
            self.assertEqual(status, 200)

    def test_export_disabled_on_vercel_without_token(self):
        env = {k: v for k, v in os.environ.items() if k != "EXPORT_TOKEN"}
        env["VERCEL"] = "1"
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(self.get("export", "/api/export")[0], 403)

    def test_invalid_submission(self):
        status, body = self.post("app", {"age": 30})
        self.assertEqual(status, 400)
        self.assertIn("gender", body["fields"])

    def test_static_and_traversal(self):
        status, text = self.get("app", "/")
        self.assertIn("<form", text)
        self.assertEqual(self.get("app", "/../app.py")[0], 404)


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "set TEST_DATABASE_URL to test Postgres")
class PostgresTests(unittest.TestCase):
    def test_round_trip(self):
        pg = store.PostgresStore(os.environ["TEST_DATABASE_URL"])
        config = schema.load_config()
        rid = pg.save(config, schema.validate(config, VALID))
        rows = {r["id"]: r for r in pg.all()}
        self.assertEqual(rows[rid]["answers"]["tobacco_products"], ["cigarettes", "vaping"])
        self.assertIn(rid, store.export_csv(pg, config))


if __name__ == "__main__":
    unittest.main()
