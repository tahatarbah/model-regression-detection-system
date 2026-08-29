export type RunSummary = {
  id: string;
  suite_name: string;
  suite_path: string | null;
  model_label: string;
  tag: string | null;
  status: string;
  task_type: string;
  metrics: Record<string, number>;
  created_at: string | null;
};

export type RunDetail = RunSummary & {
  examples: Array<{
    example_id: string;
    input: unknown;
    expected: unknown;
    output: unknown;
    score: number | null;
    passed: boolean | null;
    latency_ms: number | null;
    tokens_in: number | null;
    tokens_out: number | null;
    details: Record<string, unknown>;
  }>;
};

export type SuiteInfo = {
  name: string;
  path: string;
  description: string;
  task_type: string;
  config: Record<string, unknown>;
};

export type CompareResult = {
  baseline_run_id: string;
  candidate_run_id: string;
  suite_name: string;
  passed: boolean;
  metric_deltas: Array<{
    name: string;
    baseline: number;
    candidate: number;
    delta: number;
    relative_delta: number | null;
    direction: string;
    breached: boolean;
    reason: string | null;
  }>;
  example_diffs: Array<{
    example_id: string;
    baseline_output: unknown;
    candidate_output: unknown;
    baseline_score: number | null;
    candidate_score: number | null;
    baseline_passed: boolean | null;
    candidate_passed: boolean | null;
    regressed: boolean;
  }>;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  runs: (suiteName?: string) =>
    request<RunSummary[]>(
      suiteName ? `/api/runs?suite_name=${encodeURIComponent(suiteName)}` : "/api/runs"
    ),
  run: (id: string) => request<RunDetail>(`/api/runs/${id}`),
  suites: () => request<SuiteInfo[]>("/api/suites"),
  compare: (body: { baseline: string; candidate: string; suite_name?: string }) =>
    request<CompareResult>("/api/compare", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
