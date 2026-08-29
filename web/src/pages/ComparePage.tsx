import { FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, CompareResult, RunSummary } from "../api";

export default function ComparePage() {
  const [params] = useSearchParams();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [baseline, setBaseline] = useState(params.get("baseline") || "");
  const [candidate, setCandidate] = useState(params.get("candidate") || "");
  const [result, setResult] = useState<CompareResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const qBaseline = params.get("baseline");
    const qCandidate = params.get("candidate");
    api.runs().then((r) => {
      setRuns(r);
      if (qBaseline && qCandidate) {
        setBaseline(qBaseline);
        setCandidate(qCandidate);
        return;
      }
      if (r.length >= 2) {
        setBaseline((prev) => prev || r[1].id);
        setCandidate((prev) => prev || r[0].id);
      } else if (r.length === 1) {
        setBaseline((prev) => prev || r[0].id);
      }
    });
  }, [params]);

  useEffect(() => {
    const qBaseline = params.get("baseline");
    const qCandidate = params.get("candidate");
    if (!qBaseline || !qCandidate || runs.length === 0) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const suite = runs.find((r) => r.id === qBaseline)?.suite_name;
        const data = await api.compare({
          baseline: qBaseline,
          candidate: qCandidate,
          suite_name: suite,
        });
        if (!cancelled) setResult(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [params, runs]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const suite = runs.find((r) => r.id === baseline)?.suite_name;
      const data = await api.compare({
        baseline,
        candidate,
        suite_name: suite,
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <h1>Compare</h1>
      <p className="sub">Side-by-side metric deltas and regressed examples.</p>

      <form className="panel" onSubmit={onSubmit}>
        <div className="grid-2">
          <div>
            <label htmlFor="baseline">Baseline</label>
            <select
              id="baseline"
              value={baseline}
              onChange={(e) => setBaseline(e.target.value)}
            >
              <option value="">Select run…</option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.id.slice(0, 8)} · {r.suite_name} · {r.model_label}
                  {r.tag ? ` @${r.tag}` : ""}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="candidate">Candidate</label>
            <select
              id="candidate"
              value={candidate}
              onChange={(e) => setCandidate(e.target.value)}
            >
              <option value="">Select run…</option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.id.slice(0, 8)} · {r.suite_name} · {r.model_label}
                  {r.tag ? ` @${r.tag}` : ""}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div style={{ marginTop: "1rem" }}>
          <button type="submit" disabled={!baseline || !candidate || loading}>
            {loading ? "Comparing…" : "Compare"}
          </button>
        </div>
      </form>

      {error && <p className="error">{error}</p>}

      {result && (
        <>
          <div className="panel">
            <span className={`badge ${result.passed ? "pass" : "fail"}`}>
              {result.passed ? "PASS" : "REGRESSION"}
            </span>{" "}
            <span className="muted">{result.suite_name}</span>
          </div>

          <div className="table-wrap" style={{ marginBottom: "1.25rem" }}>
            <table>
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>Baseline</th>
                  <th>Candidate</th>
                  <th>Delta</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {result.metric_deltas.map((d) => (
                  <tr key={d.name}>
                    <td>{d.name}</td>
                    <td className="mono">{d.baseline.toFixed(4)}</td>
                    <td className="mono">{d.candidate.toFixed(4)}</td>
                    <td className="mono">{d.delta.toFixed(4)}</td>
                    <td>
                      <span className={`badge ${d.breached ? "fail" : "pass"}`}>
                        {d.breached ? "breach" : "ok"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2 style={{ fontSize: "1.1rem" }}>Regressed examples</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Baseline out</th>
                  <th>Candidate out</th>
                  <th>Scores</th>
                </tr>
              </thead>
              <tbody>
                {result.example_diffs
                  .filter((e) => e.regressed)
                  .map((e) => (
                    <tr key={e.example_id}>
                      <td className="mono">{e.example_id}</td>
                      <td>
                        <code>{JSON.stringify(e.baseline_output)}</code>
                      </td>
                      <td>
                        <code>{JSON.stringify(e.candidate_output)}</code>
                      </td>
                      <td className="mono">
                        {e.baseline_score ?? "—"} → {e.candidate_score ?? "—"}
                      </td>
                    </tr>
                  ))}
                {result.example_diffs.filter((e) => e.regressed).length === 0 && (
                  <tr>
                    <td colSpan={4} className="muted">
                      No per-example regressions flagged.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
