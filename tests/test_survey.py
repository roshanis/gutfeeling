import csv
import io
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import app
from survey import schema, store

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
    @classmethod
    def setUpClass(cls):
        cls.conn = store.connect(":memory:")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(cls.conn))
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def post(self, answers):
        req = urllib.request.Request(f"{self.base}/api/responses", data=json.dumps({"answers": answers}).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_submit_and_export(self):
        status, body = self.post(VALID)
        self.assertEqual(status, 201)
        with urllib.request.urlopen(f"{self.base}/api/export.csv") as r:
            rows = list(csv.DictReader(io.StringIO(r.read().decode())))
        row = next(x for x in rows if x["response_id"] == body["id"])
        self.assertEqual(row["tobacco_products__vaping"], "1")
        self.assertEqual(row["diet_type"], "vegetarian")

    def test_invalid_submission(self):
        status, body = self.post({"age": 30})
        self.assertEqual(status, 400)
        self.assertIn("gender", body["fields"])

    def test_static_and_traversal(self):
        with urllib.request.urlopen(f"{self.base}/") as r:
            self.assertIn(b"<form", r.read())
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(f"{self.base}/../app.py")


if __name__ == "__main__":
    unittest.main()
