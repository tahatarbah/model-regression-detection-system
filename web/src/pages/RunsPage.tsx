import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, RunSummary } from "../api";

function fmtMetrics(m: Record<string, number>) {
  return Object.entries(m)
    .map(([k, v]) => `${k}=${v.toFixed(3)}`)
    .join(" · ");
}

export default function RunsPage() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .runs()
      .then(setRuns)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div>
      <h1>Runs</h1>
      <p className="sub">Eval runs stored locally in SQLite.</p>
      {error && <p className="error">{error}</p>}
      {!error && runs.length === 0 && <p className="muted">No runs yet. Use the CLI to create some.</p>}
      {runs.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Suite</th>
                <th>Model</th>
                <th>Tag</th>
                <th>Metrics</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td className="mono">
                    <Link to={`/runs/${r.id}`}>{r.id.slice(0, 8)}</Link>
                  </td>
                  <td>{r.suite_name}</td>
                  <td>{r.model_label}</td>
                  <td className="mono">{r.tag || "—"}</td>
                  <td className="mono muted">{fmtMetrics(r.metrics)}</td>
                  <td className="muted">{r.created_at?.replace("T", " ").slice(0, 19) || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
