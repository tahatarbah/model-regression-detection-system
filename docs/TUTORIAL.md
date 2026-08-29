# MRDS Technical Tutorial

A guided walkthrough of the **Model Regression Detection System**: what it does, how the pieces fit together, and how to run classical ML and LLM regression gates end-to-end.

---

## 1. Problem it solves

When you change a model (new weights, prompt, provider, or hyperparameters), quality can silently drop. MRDS answers:

> Is this **candidate** worse than the accepted **baseline** on a fixed eval suite, past thresholds I care about?

If yes → **gate fails** (CI exit code 1) and the dashboard shows which metrics and examples regressed.

It is **batch eval + compare**, not live production drift monitoring.

---

## 2. Mental model

```text
Suite YAML ──► Adapter (classical | llm) ──► Scores / metrics
                                                    │
                                                    ▼
                                              SQLite Run
                                                    │
                         Baseline Run ◄── compare ──► Candidate Run
                                                    │
                                                    ▼
                                              Gate PASS / FAIL
                                                    │
                                    CLI (CI) · API · Dashboard
```

| Concept | Meaning |
|---|---|
| **Suite** | Named eval: dataset + metrics + thresholds + model adapter config |
| **Run** | One evaluation of one model on one suite (aggregates + per-example rows) |
| **Tag** | Alias on a run (e.g. `@prod`) so CI can pin a baseline without hardcoding UUIDs |
| **Compare** | Metric deltas + example-level regressions |
| **Gate** | Pass/fail policy over a comparison |

**Regression rule (v1):** for each metric, if degradation exceeds `absolute` and/or `relative` threshold (respecting higher-is-better vs lower-is-better), that metric **breaches**. Any breach → gate fail.

---

## 3. Repository map

```text
mrds/
  core/          schema, EvalRunner, CompareEngine, GatePolicy
  adapters/      classical.py, llm.py
  storage/       SQLite + SQLAlchemy
  cli/           Typer commands
  api/           FastAPI + static UI mount
web/             React + Vite dashboard
examples/        iris + LLM suites, demo.py
tests/           unit + integration (no network for LLM mocks)
docs/TUTORIAL.md this file
```

---

## 4. Data flow (detail)

### 4.1 Load suite

`load_suite(path)` reads YAML into a Pydantic `SuiteConfig` and remembers `suite_dir` so relative dataset/model paths resolve next to the YAML.

### 4.2 Run

`EvalRunner.run`:

1. Registers the suite in SQLite.
2. Loads examples (CSV for classical, JSONL for LLM).
3. Builds the adapter from `ModelSpec`.
4. `predict_batch(examples)` → `Prediction` list.
5. Computes metrics + per-example scores.
6. Persists a `Run` + `Example` rows; optional `--tag`.

### 4.3 Compare

`CompareEngine.compare_metrics` walks each `MetricConfig`:

- `delta = candidate - baseline`
- degradation = how much worse (depends on direction)
- breach if over `threshold.absolute` / `threshold.relative`
- if **no** thresholds set → any degradation breaches

`attach_example_diffs` marks examples that flipped pass→fail or dropped score.

### 4.4 Gate

`GatePolicy.evaluate(comparison)` → human-readable message + `passed` bool. CLI `gate` exits `0` / `1`.

---

## 5. Adapters

### Classical (`task_type: classification | regression`)

- Model: `joblib` file or `module:callable`
- Features/labels from CSV columns in the suite
- Metrics: `accuracy`, `f1`, `mae`, `rmse`, …

```yaml
# examples/iris_classification.yaml (sketch)
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

### LLM (`task_type: llm`)

- OpenAI-compatible `/chat/completions` (`OPENAI_API_KEY`, optional `OPENAI_BASE_URL`)
- Or **mock_responses** for offline demos/tests (substring match on the user prompt)
- Scorers: `exact_match`, `contains`, `regex`, `llm_judge`
- Secondary metrics: `latency_ms`, `tokens`

```yaml
# examples/llm_qa.yaml (sketch)
task_type: llm
scorer: { type: exact_match }
metrics:
  - name: exact_match
    direction: higher_is_better
    threshold: { absolute: 0.2 }
model:
  adapter: llm
  model: gpt-4o-mini
  prompt_template: "{input}"
  mock_responses:
    "capital of France": "Paris"
```

---

## 6. CLI cookbook

Install:

```bash
python -m pip install -e ".[dev]" --user
python examples/models.py   # writes iris_good/bad.joblib
```

### Classical regression gate

```bash
python -m mrds.cli.main run \
  --suite examples/iris_classification.yaml \
  --tag prod --label good

python -m mrds.cli.main gate \
  --suite examples/iris_classification.yaml \
  --baseline @prod \
  --model examples/iris_bad.joblib
# → GATE FAIL, exit 1
```

### LLM mock gate

```bash
python -m mrds.cli.main run --suite examples/llm_qa.yaml --tag prod
python -m mrds.cli.main run --suite examples/llm_qa_bad.yaml --tag candidate
python -m mrds.cli.main gate \
  --suite examples/llm_qa.yaml \
  --baseline @prod --candidate @candidate
```

### Compare / list / serve

```bash
python -m mrds.cli.main list-runs
python -m mrds.cli.main compare -b @prod -c @candidate --suite-name llm_qa
python -m mrds.cli.main serve --db .mrds/demo.db
# http://127.0.0.1:8000
```

DB path: `--db` or env `MRDS_DB` (default `.mrds/mrds.db`).

One-shot demo (seeds `.mrds/demo.db`):

```bash
python examples/demo.py
```

---

## 7. Dashboard & API

### UI pages

| Route | Purpose |
|---|---|
| `/` | Overview: pipeline steps, live stats, deep-links into compare |
| `/runs` | All stored runs |
| `/runs/:id` | Metrics + per-example table |
| `/compare` | Pick baseline/candidate (supports `?baseline=&candidate=`) |
| `/suites` | Registered suite configs |

Build UI (required once for `serve` to mount static files):

```bash
cd web && npm install && npm run build
```

Dev mode: API on `:8000`, Vite proxy on `:5173` (`npm run dev` in `web/`).

### HTTP API

| Method | Path | Role |
|---|---|---|
| GET | `/api/health` | Liveness |
| GET | `/api/runs` | List runs |
| GET | `/api/runs/{id}` | Run + examples |
| GET | `/api/suites` | Suite registry |
| POST | `/api/compare` | `{ baseline, candidate, suite_name? }` |

Same compare/gate math as the CLI — one source of truth in `mrds.core`.

---

## 8. How to add your own suite

1. Put a dataset next to a new YAML (`data.csv` or `data.jsonl`).
2. Declare `task_type`, `dataset`, `metrics` (+ thresholds), and `model`.
3. Run a known-good model with `--tag prod`.
4. In CI, `mrds gate --suite … --baseline @prod --model <candidate>`.
5. On fail, open the dashboard Compare view for failing examples.

**Threshold tips**

- Start with a small `absolute` (e.g. 0.02–0.05 for accuracy/F1).
- Use `relative` when baseline scale varies.
- For latency/tokens use `direction: lower_is_better`.

---

## 9. Testing strategy

```bash
python -m pytest -q
```

- `test_compare_gate.py` — threshold math only
- `test_classical.py` — iris good vs bad → gate fail
- `test_llm.py` — mock client, no network
- `test_api.py` — FastAPI TestClient smoke

---

## 10. What v1 deliberately skips

- Auth / multi-tenant SaaS
- Streaming production drift
- Auto-retrain / remote model registries
- Heavy statistical significance tests

Those can layer on later; the suite → run → compare → gate loop stays the core.

---

## 11. Suggested learning path (30 minutes)

1. Read `examples/iris_classification.yaml` and `examples/llm_qa.yaml`.
2. Run `python examples/demo.py`.
3. `python -m mrds.cli.main serve --db .mrds/demo.db` → open Overview → **Compare regression**.
4. Skim `mrds/core/runner.py`, `compare.py`, `gate.py`.
5. Copy a suite YAML and point it at your own CSV/JSONL.
