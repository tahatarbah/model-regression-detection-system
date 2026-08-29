# Model Regression Detection System (MRDS)

Detect when a **candidate** model (classical ML or LLM) regresses vs a **baseline** on a fixed eval suite. Gate CI with the CLI, then inspect failures in a local dashboard.

## Quick start

```bash
# Python package
pip install -e ".[dev]"

# Train toy iris models
python examples/models.py

# Baseline run
mrds run --suite examples/iris_classification.yaml --tag prod --label good

# Gate a worse model (exits 1 on regression)
mrds gate --suite examples/iris_classification.yaml --baseline @prod --model examples/iris_bad.joblib

# LLM mock suite (no API key needed when mock_responses are set)
mrds run --suite examples/llm_qa.yaml --tag prod --label llm-good
mrds run --suite examples/llm_qa_bad.yaml --tag candidate --label llm-bad
mrds gate --suite examples/llm_qa.yaml --baseline @prod --candidate @candidate

# Full demo script
python examples/demo.py
```

## Dashboard

```bash
cd web && npm install && npm run build
mrds serve
# http://127.0.0.1:8000
```

Dev UI with API proxy:

```bash
# terminal 1
mrds serve --port 8000
# terminal 2
cd web && npm run dev
# http://127.0.0.1:5173
```

Full walkthrough: [docs/TUTORIAL.md](docs/TUTORIAL.md).
## CLI

| Command | Purpose |
|---|---|
| `mrds run -s SUITE [-m MODEL] [-t TAG]` | Evaluate and store a run |
| `mrds compare -b BASE -c CAND [--suite-name NAME]` | Metric deltas |
| `mrds gate -s SUITE -b @prod [-m MODEL \| -c RUN]` | CI gate (exit 1 on regression) |
| `mrds list-runs` | Recent runs |
| `mrds serve` | API + built React UI |

Baseline/candidate refs are run UUIDs or `@tag` (requires suite context).

DB path defaults to `.mrds/mrds.db` (override with `--db` or `MRDS_DB`).

## Suite YAML

Classical:

```yaml
name: iris_classification
task_type: classification
dataset:
  path: iris.csv
  feature_columns: [sepal_length, sepal_width, petal_length, petal_width]
  label_column: species
metrics:
  - name: accuracy
    direction: higher_is_better
    threshold: { absolute: 0.05 }
model:
  adapter: classical
  path: iris_good.joblib
```

LLM (OpenAI-compatible; set `OPENAI_API_KEY`, optional `OPENAI_BASE_URL`):

```yaml
name: llm_qa
task_type: llm
dataset:
  path: qa.jsonl
  input_field: input
  expected_field: expected
scorer: { type: exact_match }  # exact_match | contains | regex | llm_judge
metrics:
  - name: exact_match
    direction: higher_is_better
    threshold: { absolute: 0.2 }
model:
  adapter: llm
  model: gpt-4o-mini
  prompt_template: "{input}"
```

## Layout

```
mrds/           # core, adapters, storage, cli, api
web/            # React + Vite dashboard
examples/       # iris + LLM suites, demo script
tests/
```

## Tests

```bash
pytest
```
