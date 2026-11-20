# Conrad: gut health survey

A simple web survey that collects demographics, smoking and alcohol use, health
history, diet and eating habits. Answers are stored in a structured way so they
can later be joined with gut-health data to predict foods that cause bloating.

No dependencies beyond Python 3.9+.

## Run it

```bash
python app.py                      # http://127.0.0.1:8000
python app.py --host 0.0.0.0 --port 8000 --export-token SECRET
```

Responses are saved to `data/responses.db` (SQLite, git-ignored).

## Edit the questions

All questions live in [`survey/questions.json`](survey/questions.json). The
page and the server both read it, so editing that one file is enough (no
restart needed). Each question has:

| field      | meaning |
|------------|---------|
| `id`       | stable snake_case key used in the stored data and CSV. Don't rename once data is collected. |
| `type`     | `single` (pick one), `multi` (pick many), `number`, `text`, `height` (stored in cm; people can enter ft/in or cm) |
| `label`    | question text shown to people |
| `options`  | for `single`/`multi`: list of `{"value", "label"}` |
| `required` | `true` if it must be answered |
| `min`/`max`/`unit` | for numbers |
| `exclusive`| for `multi`: options like `"none"` that can't be combined with others |
| `show_if`  | only ask when an earlier answer matches, e.g. `{"question": "smoking_status", "in": ["current"]}` |

Bump `version` at the top when you change questions in a way that matters for
analysis; each response records the version it was answered with. `python -m
unittest` checks the config for typos (duplicate ids, broken `show_if`).

## Get the data out

`GET /api/export.csv` returns one row per response and one column per answer,
ready for pandas or a model:

- `single`, `number`, `text` → one column named after the question id
- `multi` → one 0/1 column per option, e.g. `chronic_conditions__ibs`
- `height` → `height_cm`
- questions that weren't shown (e.g. tobacco products for non-smokers) are blank

The raw answers are also kept as JSON in the `responses` table.

## Tests

```bash
python -m unittest discover -s tests -t .
```
