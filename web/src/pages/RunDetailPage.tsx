import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, RunDetail } from "../api";

export default function RunDetailPage() {
  const { id } = useParams();
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api
      .run(id)
      .then(setRun)
      .catch((e: Error) => setError(e.message));
  }, [id]);

  if (error) return <p className="error">{error}</p>;
  if (!run) return <p className="muted">Loading…</p>;

  return (
    <div>
      <p className="muted">
        <Link to="/runs">← Runs</Link>
      </p>
      <h1>Run {run.id.slice(0, 8)}</h1>
      <p className="sub">
        {run.suite_name} · {run.model_label}
        {run.tag ? ` · @${run.tag}` : ""} · {run.task_type}
      </p>

      <div className="panel">
        <div className="metrics">
          {Object.entries(run.metrics).map(([k, v]) => (
            <div className="metric-chip" key={k}>
              {k}: <strong>{v.toFixed(4)}</strong>
            </div>
          ))}
        </div>
      </div>

      <h2 style={{ fontSize: "1.1rem" }}>Examples</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Input</th>
              <th>Expected</th>
              <th>Output</th>
              <th>Score</th>
              <th>Pass</th>
            </tr>
          </thead>
          <tbody>
            {run.examples.map((ex) => (
              <tr key={ex.example_id}>
                <td className="mono">{ex.example_id}</td>
                <td>
                  <code>{JSON.stringify(ex.input)}</code>
                </td>
                <td>
                  <code>{JSON.stringify(ex.expected)}</code>
                </td>
                <td>
                  <code>{JSON.stringify(ex.output)}</code>
                </td>
                <td className="mono">{ex.score ?? "—"}</td>
                <td>
                  {ex.passed == null ? (
                    "—"
                  ) : (
                    <span className={`badge ${ex.passed ? "pass" : "fail"}`}>
                      {ex.passed ? "pass" : "fail"}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
