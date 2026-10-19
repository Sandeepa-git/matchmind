import { useEffect, useRef, useState } from "react";
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, Moment, Produced, State, Why } from "./api";

const KIND_LABEL: Record<string, string> = { goal: "⚽ Goal", big_chance: "🎯 Big chance", momentum_flip: "🔄 Momentum flip" };

export default function App() {
  const [minute, setMinute] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [state, setState] = useState<State | null>(null);
  const [selected, setSelected] = useState<Moment | null>(null);
  const [why, setWhy] = useState<Why | null>(null);
  const timer = useRef<number>();

  useEffect(() => { api.state(minute).then(setState); }, [minute]);

  useEffect(() => {
    if (!playing) return;
    timer.current = window.setInterval(() => setMinute((m) => (m >= 95 ? (setPlaying(false), 95) : m + 1)), 700);
    return () => window.clearInterval(timer.current);
  }, [playing]);

  const openWhy = async (m: Moment) => {
    setSelected(m); setWhy(null);
    setWhy(await api.why(m.id));
  };

  if (!state) return <div className="loading">Loading match…</div>;
  const { teams, summary } = state;

  return (
    <div className="app">
      <header>
        <h1>MatchMind <span>explainable match intelligence</span></h1>
        {state.mock && <div className="badge">Mock mode: add Azure keys to .env for AI</div>}
      </header>

      <section className="scoreboard card">
        <div className="team">{teams.home}</div>
        <div className="score">{summary.score.home} – {summary.score.away}<small>{minute}'</small></div>
        <div className="team">{teams.away}</div>
        <div className="xg">xG {summary.xg.home} – {summary.xg.away}</div>
        <div className="controls">
          <button onClick={() => setPlaying((p) => !p)}>{playing ? "⏸ Pause" : "▶ Play live"}</button>
          <input type="range" min={0} max={95} value={minute} onChange={(e) => setMinute(+e.target.value)} />
          <button onClick={() => { setPlaying(false); setMinute(95); }}>Full time</button>
        </div>
      </section>

      <section className="card">
        <h2>Momentum <small>above = {teams.home}, below = {teams.away}</small></h2>
        <ResponsiveContainer width="100%" height={180}>
          <AreaChart data={state.series}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
            <XAxis dataKey="minute" domain={[0, 95]} type="number" />
            <YAxis />
            <Tooltip />
            <ReferenceLine y={0} stroke="#888" />
            {state.moments.filter((m) => m.kind === "goal").map((m) => (
              <ReferenceLine key={m.id} x={m.minute} stroke="#f5c518" label="⚽" />
            ))}
            <Area dataKey="momentum" stroke="#7c5cff" fill="#7c5cff" fillOpacity={0.35} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </section>

      <div className="grid">
        <section className="card">
          <h2>Key moments</h2>
          <ul className="moments">
            {[...state.moments].reverse().map((m) => (
              <li key={m.id} className={selected?.id === m.id ? "active" : ""} onClick={() => openWhy(m)}>
                <b>{m.minute}'</b> {KIND_LABEL[m.kind] ?? m.kind} · {teams[m.team]} {m.player && `· ${m.player}`}
                <span className="whybtn">Why?</span>
              </li>
            ))}
            {!state.moments.length && <li className="muted">Press play…</li>}
          </ul>
        </section>

        <section className="card">
          <h2>Why did it happen?</h2>
          {!selected && <p className="muted">Pick a moment to get an evidence-backed explanation.</p>}
          {selected && !why && <p className="muted">Analyst agent is reviewing the evidence…</p>}
          {why && (
            <div>
              <h3>{why.headline}</h3>
              <p>{why.explanation}</p>
              <p><b>Pattern:</b> {why.tactical_pattern} · <b>Confidence:</b> {why.confidence}</p>
              <details open>
                <summary>Evidence ({why.evidence_events.length} events)</summary>
                <ul className="evidence">
                  {why.evidence_events.map((e) => (
                    <li key={e.id}>#{e.id} {e.minute}:{String(e.second).padStart(2, "0")} {e.player} – {e.type} ({teams[e.team as "home"]})</li>
                  ))}
                </ul>
              </details>
            </div>
          )}
        </section>
      </div>

      <div className="grid">
        <RecapStudio minute={minute} />
        <AskAnalyst />
      </div>
    </div>
  );
}

const AGENT_ICON: Record<string, string> = {
  Detector: "📡", Analyst: "🧠", Narrator: "✍️", FactChecker: "🔍", Fallback: "🛟", Localizer: "🌍",
};

function RecapStudio({ minute }: { minute: number }) {
  const [opts, setOpts] = useState<{ personas: string[]; formats: string[]; langs: Record<string, string> } | null>(null);
  const [persona, setPersona] = useState("casual");
  const [format, setFormat] = useState("article");
  const [lang, setLang] = useState("en");
  const [stress, setStress] = useState(false);
  const [out, setOut] = useState<Produced | null>(null);
  const [shown, setShown] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.options().then(setOpts); }, []);

  // reveal trace steps one by one so the handoffs are visible
  useEffect(() => {
    if (!out || shown >= out.trace.length) return;
    const t = window.setTimeout(() => setShown((n) => n + 1), 450);
    return () => window.clearTimeout(t);
  }, [out, shown]);

  const go = async () => {
    setBusy(true); setOut(null); setShown(0);
    try { setOut(await api.produce({ minute, persona, format, lang, inject_error: stress })); } finally { setBusy(false); }
  };
  const done = out && shown >= out.trace.length;

  return (
    <section className="card">
      <h2>AI production room <small>multi-agent · Microsoft Agent Framework</small></h2>
      {opts && (
        <div className="row">
          <select aria-label="Audience" value={persona} onChange={(e) => setPersona(e.target.value)}>{opts.personas.map((p) => <option key={p}>{p}</option>)}</select>
          <select aria-label="Format" value={format} onChange={(e) => setFormat(e.target.value)}>{opts.formats.map((f) => <option key={f}>{f}</option>)}</select>
          <select aria-label="Language" value={lang} onChange={(e) => setLang(e.target.value)}>
            {Object.entries(opts.langs).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <button onClick={go} disabled={busy}>{busy ? "Agents working…" : "Produce"}</button>
        </div>
      )}
      <label className="stress"><input type="checkbox" checked={stress} onChange={(e) => setStress(e.target.checked)} />
        Stress test: inject a hallucination into the first draft</label>
      {out && (
        <ol className="trace">
          {out.trace.slice(0, shown).map((s, i) => (
            <li key={i} className={s.status}>
              <span className="who">{AGENT_ICON[s.agent] ?? "🤖"} {s.agent}</span>
              <span className="tag">{s.status}</span>
              <span className="det">{s.detail}</span>
            </li>
          ))}
        </ol>
      )}
      {done && (
        <>
          <p className="verified">{out!.verified ? "✅ Every claim verified against match data" : "⚠️ Unverified"} · {out!.attempts} draft(s)</p>
          <pre className="recap" dir={lang === "ar" ? "rtl" : "ltr"}>{out!.text}</pre>
        </>
      )}
    </section>
  );
}

function AskAnalyst() {
  const [q, setQ] = useState("");
  const [log, setLog] = useState<{ q: string; a: string; c: string[] }[]>([]);
  const [busy, setBusy] = useState(false);

  const send = async () => {
    if (!q.trim()) return;
    setBusy(true);
    const r = await api.ask(q);
    setLog((l) => [...l, { q, a: r.answer, c: r.citations }]);
    setQ(""); setBusy(false);
  };

  return (
    <section className="card">
      <h2>Ask the analyst</h2>
      <div className="chat">
        {log.map((m, i) => (
          <div key={i}><p className="q">{m.q}</p><p className="a">{m.a}</p><p className="cite">Sources: min {m.c.join(", ")}</p></div>
        ))}
      </div>
      <div className="row">
        <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()}
               placeholder="Why did the away side take over after 55'?" />
        <button onClick={send} disabled={busy}>{busy ? "…" : "Ask"}</button>
      </div>
    </section>
  );
}
