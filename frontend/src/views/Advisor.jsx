import React, { useState } from 'react';
import { Sparkles, AlertTriangle, Info, ShieldAlert, ArrowRight } from 'lucide-react';
import { api, Section, Err } from './shared';

const ICON = { critical: ShieldAlert, warning: AlertTriangle, info: Info };

export default function Advisor({ API, go }) {
  const [data, setData] = useState(null), [busy, setBusy] = useState(false), [err, setErr] = useState('');
  async function run() {
    setBusy(true); setErr('');
    try { setData(await api(API, '/advisor')); } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }
  return <>
    <section className="hero">
      <div>
        <div className="eyebrow light">SMART ADVISOR</div>
        <h2>{data ? data.summary : 'Get a prioritized plan for your PC.'}</h2>
        <p>Checks junk, disk space, startup load, memory, security and your scan trend, then tells you what to do first and why.</p>
        <button className="primary" disabled={busy} onClick={run}>{busy ? 'Analyzing… (up to 30s)' : <><Sparkles size={17} /> {data ? 'Analyze again' : 'Analyze my PC'}</>}</button>
      </div>
    </section>
    <Err msg={err} />
    {data && <Section title="Recommendations" sub="Most important first. Nothing is changed until you act." tag="EVIDENCE-BASED">
      <section className="panel findings">
        {data.recommendations.length === 0 && <div className="empty">Nothing needs attention right now.</div>}
        {data.recommendations.map(r => {
          const Icon = ICON[r.severity] || Info;
          return <div className="finding" key={r.id}>
            <div className={`finding-icon ${r.severity === 'critical' ? 'critical' : r.severity}`}><Icon /></div>
            <div style={{ flex: 1 }}>
              <b>{r.title}</b>
              <p>{r.detail}</p>
              <p className="evidence">Evidence: {r.evidence}</p>
              {r.action && <button className="ghost" onClick={() => go(r.action.view)}>{r.action.label} <ArrowRight size={14} /></button>}
            </div>
          </div>;
        })}
        <p className="scope">{data.note}</p>
      </section>
    </Section>}
  </>;
}
