"""Load the question config, validate answers against it, and flatten answers
into one row of columns for analysis or model training."""
import json
from pathlib import Path

QUESTIONS_PATH = Path(__file__).with_name("questions.json")
TYPES = {"single", "multi", "number", "text", "height"}


class ValidationError(ValueError):
    def __init__(self, errors):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


def load_config(path=QUESTIONS_PATH):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    check_config(config)
    return config


def iter_questions(config):
    for section in config["sections"]:
        yield from section["questions"]


def check_config(config):
    """Catch typos in questions.json early (duplicate ids, bad types, broken show_if)."""
    seen = {}
    for q in iter_questions(config):
        qid = q.get("id")
        if not qid or qid in seen:
            raise ValueError(f"question id missing or duplicated: {qid!r}")
        if q.get("type") not in TYPES:
            raise ValueError(f"{qid}: unknown type {q.get('type')!r}")
        if q["type"] in ("single", "multi"):
            values = [o["value"] for o in q.get("options", [])]
            if not values or len(values) != len(set(values)):
                raise ValueError(f"{qid}: options missing or duplicated")
        cond = q.get("show_if")
        if cond:
            parent = seen.get(cond.get("question"))
            if parent is None:
                raise ValueError(f"{qid}: show_if must refer to an earlier question")
            if parent["type"] in ("single", "multi"):
                parent_values = {o["value"] for o in parent["options"]}
                bad = set(cond.get("in", [])) - parent_values
                if bad:
                    raise ValueError(f"{qid}: show_if uses unknown values {sorted(bad)}")
        seen[qid] = q


def is_visible(question, answers):
    cond = question.get("show_if")
    if not cond:
        return True
    value = answers.get(cond["question"])
    if isinstance(value, list):
        return any(v in cond["in"] for v in value)
    return value in cond["in"]


def _is_empty(value):
    return value is None or value == "" or value == []


def validate(config, raw_answers):
    """Return cleaned answers (hidden questions dropped) or raise ValidationError."""
    if not isinstance(raw_answers, dict):
        raise ValidationError({"_": "answers must be an object"})
    cleaned, errors = {}, {}
    for q in iter_questions(config):
        qid = q["id"]
        if not is_visible(q, cleaned):
            continue
        value = raw_answers.get(qid)
        if _is_empty(value):
            if q.get("required"):
                errors[qid] = "required"
            continue
        try:
            cleaned[qid] = _clean(q, value)
        except ValueError as exc:
            errors[qid] = str(exc)
    unknown = set(raw_answers) - {q["id"] for q in iter_questions(config)}
    if unknown:
        errors["_"] = f"unknown questions: {sorted(unknown)}"
    if errors:
        raise ValidationError(errors)
    return cleaned


def _clean(q, value):
    t = q["type"]
    if t == "single":
        if value not in {o["value"] for o in q["options"]}:
            raise ValueError("not a valid option")
        return value
    if t == "multi":
        if not isinstance(value, list):
            raise ValueError("must be a list")
        allowed = [o["value"] for o in q["options"]]
        if any(v not in allowed for v in value):
            raise ValueError("contains an invalid option")
        value = [v for v in allowed if v in value]  # dedupe, stable order
        exclusive = set(q.get("exclusive", []))
        if len(value) > 1 and exclusive & set(value):
            raise ValueError(f"{sorted(exclusive & set(value))} cannot be combined with other options")
        return value
    if t in ("number", "height"):
        if isinstance(value, bool):
            raise ValueError("must be a number")
        try:
            num = float(value)
        except (TypeError, ValueError):
            raise ValueError("must be a number") from None
        if "min" in q and num < q["min"] or "max" in q and num > q["max"]:
            raise ValueError(f"must be between {q.get('min')} and {q.get('max')}")
        return int(num) if num.is_integer() else round(num, 2)
    if t == "text":
        if not isinstance(value, str):
            raise ValueError("must be text")
        value = value.strip()
        if len(value) > 500:
            raise ValueError("must be 500 characters or fewer")
        return value
    raise ValueError(f"unsupported type {t}")


def columns(config):
    """Column names for the flat export. Multi-select questions become one 0/1
    column per option (e.g. chronic_conditions__ibs) so they are model-ready."""
    cols = []
    for q in iter_questions(config):
        if q["type"] == "multi":
            cols += [f"{q['id']}__{o['value']}" for o in q["options"]]
        elif q["type"] == "height":
            cols.append(f"{q['id']}_cm")
        else:
            cols.append(q["id"])
    return cols


def flatten(config, answers):
    row = {}
    for q in iter_questions(config):
        qid, value = q["id"], answers.get(q["id"])
        if q["type"] == "multi":
            for o in q["options"]:
                row[f"{qid}__{o['value']}"] = None if value is None else int(o["value"] in value)
        elif q["type"] == "height":
            row[f"{qid}_cm"] = value
        else:
            row[qid] = value
    return row
