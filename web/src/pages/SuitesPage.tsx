import { useEffect, useState } from "react";
import { api, SuiteInfo } from "../api";

export default function SuitesPage() {
  const [suites, setSuites] = useState<SuiteInfo[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .suites()
      .then(setSuites)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div>
      <h1>Suites</h1>
      <p className="sub">Registered when you run an eval via the CLI.</p>
      {error && <p className="error">{error}</p>}
      {!error && suites.length === 0 && (
        <p className="muted">No suites registered yet.</p>
      )}
      {suites.map((s) => (
        <div className="panel" key={s.name}>
          <strong>{s.name}</strong>{" "}
          <span className="badge">{s.task_type}</span>
          <p className="muted" style={{ margin: "0.4rem 0 0.6rem" }}>
            {s.description || "No description"}
          </p>
          <p className="mono muted" style={{ margin: 0, fontSize: "0.8rem" }}>
            {s.path}
          </p>
        </div>
      ))}
    </div>
  );
}
