# Conrad: gut health survey

A simple web survey that collects demographics, smoking and alcohol use, health
history, diet and eating habits. Answers are stored in a structured way so they
can later be joined with gut-health data to predict foods that cause bloating.

## Run it locally

Needs only Python 3.9+.

```bash
python app.py                      # http://127.0.0.1:8000
```

Responses are saved to `data/responses.db` (SQLite, git-ignored). Set
`DATABASE_URL` to a Postgres URL to use Postgres instead (needs
`pip install -r requirements.txt`).

## Deploy to Vercel

Vercel's disk is wiped between requests, so the deployed survey stores
responses in Postgres.

1. In Vercel, **Add New → Project** and import this GitHub repo. Leave the
   framework preset as **Other** and all build settings at their defaults.
2. In the project's **Storage** tab, add a Postgres database (e.g. **Neon**)
   and connect it. This sets `DATABASE_URL` / `POSTGRES_URL` for you. The
   table is created automatically on the first response.
3. In **Settings → Environment Variables**, add `EXPORT_TOKEN` with a long
   random value. Without it the export is switched off on Vercel.
4. Deploy. The survey is at the project URL, and the data export at
   `https://<your-app>.vercel.app/api/export.csv?token=<EXPORT_TOKEN>`.

How it's wired: `public/` is served as static files, and `api/questions.py`,
`api/responses.py` and `api/export.py` are Python serverless functions that
share the logic in `survey/`. `vercel.json` maps `/api/export.csv` to the
export function.

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

`GET /api/export.csv` (with `?token=<EXPORT_TOKEN>` or an
`Authorization: Bearer <EXPORT_TOKEN>` header when that variable is set) returns one row per response and one column per answer,
ready for pandas or a model:

- `single`, `number`, `text` → one column named after the question id
- `multi` → one 0/1 column per option, e.g. `chronic_conditions__ibs`
- `height` → `height_cm`
- questions that weren't shown (e.g. tobacco products for non-smokers) are blank

The raw answers are also kept as JSON in the `survey_responses` table (Postgres) or
`responses` table (SQLite).

## Tests

```bash
python -m unittest discover -s tests -t .
TEST_DATABASE_URL=postgresql://... python -m unittest discover -s tests -t .   # also tests Postgres
```
