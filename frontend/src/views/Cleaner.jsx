import React, { useEffect, useState } from 'react';
import { Trash2, RefreshCw, ShieldCheck, CheckCircle2 } from 'lucide-react';
import { api, fmtBytes, Section, Err } from './shared';

export default function Cleaner({ API }) {
  const [scan, setScan] = useState(null), [picked, setPicked] = useState({}), [busy, setBusy] = useState(''), [err, setErr] = useState('');
  const [result, setResult] = useState(null), [history, setHistory] = useState([]);
  const loadHistory = () => api(API, '/cleaner/history').then(d => setHistory(d.cleanups || [])).catch(() => {});
  useEffect(() => { loadHistory(); }, []);

  async function runScan() {
    setBusy('scan'); setErr(''); setResult(null);
    try {
      const d = await api(API, '/cleaner/scan');
      if (!d.available) throw new Error(d.reason || 'Cleaner unavailable');
      setScan(d);
      setPicked(Object.fromEntries(d.categories.map(c => [c.id, c.default && c.bytes > 0])));
    } catch (e) { setErr(e.message); } finally { setBusy(''); }
  }
  const selected = scan ? scan.categories.filter(c => picked[c.id]) : [];
  const selectedBytes = selected.reduce((a, c) => a + c.bytes, 0);

  async function clean() {
    if (!selected.length) return;
    const hasReview = selected.some(c => c.risk === 'review');
    const msg = `Delete ${fmtBytes(selectedBytes)} from:\n\n${selected.map(c => '• ' + c.label).join('\n')}\n\n${hasReview ? 'Some selected items cannot be undone (e.g. Recycle Bin).\n\n' : ''}Continue?`;
    if (!window.confirm(msg)) return;
    setBusy('clean'); setErr('');
    try {
      setResult(await api(API, '/cleaner/clean', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ categories: selected.map(c => c.id), confirm: true }) }));
      await loadHistory(); await runScanKeepResult();
    } catch (e) { setErr(e.message); } finally { setBusy(''); }
  }
  async function runScanKeepResult() {
    try { const d = await api(API, '/cleaner/scan'); setScan(d); setPicked({}); } catch { /* ignore */ }
  }

  return <>
    <section className="hero">
      <div>
        <div className="eyebrow light">SAFE CLEANUP</div>
        <h2>{scan ? `${fmtBytes(scan.total_bytes)} can be cleaned` : 'Find junk you can safely remove.'}</h2>
        <p>Scan first, choose what to remove, then confirm. Your documents, passwords, browser history and bookmarks are never touched.</p>
        <button className="primary" disabled={!!busy} onClick={runScan}>{busy === 'scan' ? <><RefreshCw className="spin" size={17} /> Scanning…</> : <><Trash2 size={17} /> {scan ? 'Scan again' : 'Scan for junk'}</>}</button>
      </div>
    </section>
    <Err msg={err} />
    {result && <div className="success"><CheckCircle2 size={18} /> Freed {fmtBytes(result.freed_bytes)}. {result.results.map(r => `${r.label}: ${r.deleted} deleted${r.skipped ? `, ${r.skipped} skipped (in use or protected)` : ''}${r.error ? ` — ${r.error}` : ''}`).join(' · ')}</div>}
    {scan && <Section title="What was found" sub="Safe items are pre-selected. Items marked Review are unticked." tag="PREVIEW ONLY">
      <section className="panel">
        {scan.categories.map(c => <label className={`clean-row ${!c.present && !c.bytes ? 'dim' : ''}`} key={c.id}>
          <input type="checkbox" checked={!!picked[c.id]} disabled={!c.bytes} onChange={e => setPicked({ ...picked, [c.id]: e.target.checked })} />
          <div style={{ flex: 1 }}>
            <b>{c.label} {c.risk === 'review' && <span className="tag">REVIEW</span>}</b>
            <small>{c.description}{c.skipped_recent ? ` (${c.skipped_recent} recent file(s) excluded)` : ''}{!c.present && !c.bytes ? ' · Not found on this PC' : ''}</small>
          </div>
          <b>{fmtBytes(c.bytes)}</b>
        </label>)}
        <div className="clean-actions">
          <span><ShieldCheck size={15} /> {selected.length} selected · {fmtBytes(selectedBytes)}</span>
          <button className="primary danger" disabled={!!busy || !selected.length} onClick={clean}>{busy === 'clean' ? 'Cleaning…' : 'Clean selected'}</button>
        </div>
        <p className="scope">{scan.note} Close your browsers first for best results.</p>
      </section>
    </Section>}
    <Section title="Cleanup history" sub="Stored locally on this PC">
      <section className="panel history">
        {history.length ? history.map(h => <div className="history-row" key={h.id}><div><b>Cleanup #{h.id}</b><small>{new Date(h.cleaned_at).toLocaleString()}</small></div><span className="score">{fmtBytes(h.freed_bytes)}</span></div>) : <div className="empty">No cleanups yet.</div>}
      </section>
    </Section>
  </>;
}
