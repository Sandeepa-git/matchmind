export type Moment = {
  id: number; kind: string; team: "home" | "away"; player?: string; minute: number;
  event_id: number; score: { home: number; away: number }; momentum: number;
};
export type State = {
  match_id: string; teams: { home: string; away: string }; minute: number; mock: boolean;
  summary: { score: { home: number; away: number }; xg: { home: number; away: number } };
  series: { minute: number; momentum: number; xg_home: number; xg_away: number }[];
  moments: Moment[];
};
export type Why = {
  headline: string; explanation: string; tactical_pattern: string; confidence: string;
  evidence: number[]; evidence_events: { id: number; minute: number; second: number; player: string; type: string; team: string }[];
};

export type TraceStep = { agent: string; status: "ok" | "pass" | "reject" | "warn"; detail: string; ms: number };
export type Produced = { text: string; lang: string; verified: boolean; attempts: number; trace: TraceStep[] };

const get = async <T,>(url: string): Promise<T> => (await fetch(url)).json();
const post = async <T,>(url: string, body: unknown): Promise<T> =>
  (await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json();

export const api = {
  state: (minute: number) => get<State>(`/api/state?minute=${minute}`),
  why: (id: number) => get<Why>(`/api/why/${id}`),
  options: () => get<{ personas: string[]; formats: string[]; langs: Record<string, string> }>("/api/options"),
  produce: (b: { minute: number; persona: string; format: string; lang: string; inject_error: boolean }) =>
    post<Produced>("/api/produce", b),
  ask: (question: string) => post<{ answer: string; citations: string[] }>("/api/ask", { question }),
};
