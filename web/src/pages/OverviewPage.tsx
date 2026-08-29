import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, RunSummary } from "../api";

const STEPS = [
  {
    n: "01",
    title: "Eval suite",
    body: "A YAML file defines the dataset, metrics, thresholds, and which adapter (classical or LLM) to use.",
  },
  {
    n: "02",
    title: "Run",
    body: "The runner loads examples, calls the model adapter, scores predictions, and stores a Run in SQLite.",
  },
  {
    n: "03",
    title: "Compare",
    body: "Baseline vs candidate metric deltas are checked against absolute/relative thresholds.",
  },
  {
    n: "04",
    title: "Gate",
    body: "CI fails (exit 1) when any metric breaches its threshold — this dashboard shows why.",
  },
];

export default function OverviewPage() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .runs()
      .then(setRuns)
      .catch((e: Error) => setError(e.message));
  }, []);

  const stats = useMemo(() => {
    const suites = new Set(runs.map((r) => r.suite_name));
    const tagged = runs.filter((r) => r.tag).length;
    const classical = runs.filter((r) => r.task_type !== "llm").length;
    const llm = runs.filter((r) => r.task_type === "llm").length;
    return {
      runs: runs.length,
      suites: suites.size,
      tagged,
      classical,
      llm,
      latest: runs[0] ?? null,
    };
  }, [runs]);

  const bySuite = useMemo(() => {
    const map = new Map<string, RunSummary[]>();
    for (const r of runs) {
      const list = map.get(r.suite_name) ?? [];
      list.push(r);
      map.set(r.suite_name, list);
    }
    return [...map.entries()];
  }, [runs]);

  return (
    <div>
      <h1>How MRDS works</h1>
      <p className="sub">
        Model Regression Detection System — evaluate a candidate against a baseline and gate
        regressions before they ship.
      </p>

      <div className="flow">
        {STEPS.map((s) => (
          <div className="flow-step" key={s.n}>
            <div className="flow-n mono">{s.n}</div>
            <div>
              <strong>{s.title}</strong>
              <p className="muted" style={{ margin: "0.35rem 0 0" }}>
                {s.body}
              </p>
            </div>
          </div>
        ))}
      </div>

      <div className="stat-row">
        <div className="stat">
          <div className="stat-label">Runs</div>
          <div className="stat-value mono">{stats.runs}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Suites</div>
          <div className="stat-value mono">{stats.suites}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Tagged</div>
          <div className="stat-value mono">{stats.tagged}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Classical / LLM</div>
          <div className="stat-value mono">
            {stats.classical} / {stats.llm}
          </div>
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      {!error && runs.length === 0 && (
        <div className="panel">
          <strong>No runs yet</strong>
          <p className="muted" style={{ margin: "0.5rem 0 0" }}>
            Seed demo data, then refresh:
          </p>
          <pre className="code-block">{`python examples/demo.py
python -m mrds.cli.main serve --db .mrds/demo.db`}</pre>
        </div>
      )}

      {bySuite.length > 0 && (
        <>
          <h2 className="section-title">Try it in this UI</h2>
          <div className="grid-2">
            {bySuite.map(([name, suiteRuns]) => {
              const baseline = suiteRuns.find((r) => r.tag === "prod") ?? suiteRuns[suiteRuns.length - 1];
              const candidate =
                suiteRuns.find((r) => r.id !== baseline.id && (r.tag === "candidate" || !r.tag)) ??
                suiteRuns[0];
              return (
                <div className="panel" key={name}>
                  <strong>{name}</strong>
                  <p className="muted" style={{ margin: "0.4rem 0 0.8rem" }}>
                    {suiteRuns.length} run{suiteRuns.length === 1 ? "" : "s"} ·{" "}
                    {suiteRuns[0]?.task_type}
                  </p>
                  <div className="metrics" style={{ marginBottom: "0.85rem" }}>
                    {Object.entries(baseline.metrics)
                      .slice(0, 3)
                      .map(([k, v]) => (
                        <div className="metric-chip" key={k}>
                          {k}: <strong>{Number(v).toFixed(3)}</strong>
                        </div>
                      ))}
                  </div>
                  <div className="action-row">
                    <Link className="btn-link" to={`/runs/${baseline.id}`}>
                      Open baseline
                    </Link>
                    {candidate && candidate.id !== baseline.id && (
                      <Link
                        className="btn-link primary"
                        to={`/compare?baseline=${baseline.id}&candidate=${candidate.id}`}
                      >
                        Compare regression
                      </Link>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      <h2 className="section-title">Surfaces</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Surface</th>
              <th>Role</th>
              <th>Go</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>CLI</td>
              <td className="muted">run / compare / gate for local &amp; CI</td>
              <td className="mono muted">mrds gate …</td>
            </tr>
            <tr>
              <td>API</td>
              <td className="muted">JSON over FastAPI</td>
              <td className="mono">
                <a href="/api/runs" target="_blank" rel="noreferrer">
                  /api/runs
                </a>
              </td>
            </tr>
            <tr>
              <td>Dashboard</td>
              <td className="muted">Inspect runs, deltas, failing examples</td>
              <td>
                <Link to="/runs">Runs</Link>
                {" · "}
                <Link to="/compare">Compare</Link>
                {" · "}
                <Link to="/suites">Suites</Link>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
