import React, { useState } from 'react';
import { FolderSearch, Copy, Package } from 'lucide-react';
import { api, fmtBytes, Section, Err } from './shared';

export default function SpaceFinder({ API }) {
  const [minMb, setMinMb] = useState(500), [big, setBig] = useState(null);
  const [dupPath, setDupPath] = useState(''), [dups, setDups] = useState(null);
  const [apps, setApps] = useState(null), [busy, setBusy] = useState(''), [err, setErr] = useState('');
  async function go(kind, fn) { setBusy(kind); setErr(''); try { await fn(); } catch (e) { setErr(e.message); } finally { setBusy(''); } }
  const copy = (t) => navigator.clipboard?.writeText(t).catch(() => {});
  return <>
    <section className="hero"><div>
      <div className="eyebrow light">REPORT ONLY</div>
      <h2>See what is really using your disk.</h2>
      <p>These tools only <b>show</b> big files, duplicates and installed apps. You decide what to remove, so nothing here can delete your data.</p>
    </div></section>
    <Err msg={err} />

    <Section title="Large file finder" sub="Scans Downloads, Desktop, Documents, Videos, Pictures and Music" tag="READ-ONLY">
      <section className="panel pad">
        <div className="row">
          <label className="field">Minimum size (MB)<input type="number" min="10" value={minMb} onChange={e => setMinMb(Number(e.target.value) || 500)} /></label>
          <button className="primary" disabled={!!busy} onClick={() => go('big', async () => setBig(await api(API, `/space/large-files?min_mb=${minMb}`)))}><FolderSearch size={17} /> {busy === 'big' ? 'Scanning…' : 'Find large files'}</button>
        </div>
        {big && (big.error ? <div className="notice">{big.error}</div> : <>
          <p className="metric-sub">{big.total_found} file(s) ≥ {big.min_mb} MB · {big.elapsed_seconds}s{big.truncated ? ' · partial (time limit)' : ''}</p>
          {big.files.map(f => <div className="info-row" key={f.path}><span title={f.path}>{f.name}<small className="sub">{f.path} · last modified {f.days_since_modified} days ago</small></span><b>{fmtBytes(f.size_bytes)} <button className="ghost sm" onClick={() => copy(f.path)}>Copy path</button></b></div>)}
          <p className="scope">{big.note}</p></>)}
      </section>
    </Section>

    <Section title="Duplicate finder" sub="Finds byte-identical files (SHA-256 verified) in one folder" tag="READ-ONLY">
      <section className="panel pad">
        <div className="row">
          <label className="field grow">Folder to check<input value={dupPath} onChange={e => setDupPath(e.target.value)} placeholder="e.g. C:\Users\you\Downloads" /></label>
          <button className="primary" disabled={!!busy || !dupPath.trim()} onClick={() => go('dup', async () => setDups(await api(API, `/space/duplicates?path=${encodeURIComponent(dupPath)}&min_mb=1`)))}><Copy size={17} /> {busy === 'dup' ? 'Comparing…' : 'Find duplicates'}</button>
        </div>
        {dups && (dups.error ? <div className="notice">{dups.error}</div> : <>
          <p className="metric-sub">{dups.group_count} duplicate group(s) · about {dups.total_wasted_mb} MB reclaimable · {dups.elapsed_seconds}s{dups.truncated ? ' · partial' : ''}</p>
          {dups.groups.map((g, i) => <div className="dup-group" key={i}><b>{g.copies} copies × {g.size_mb} MB <span className="tag">{g.wasted_mb} MB wasted</span></b>{g.paths.map(p => <small key={p} className="sub">{p}</small>)}</div>)}
          <p className="scope">{dups.note}</p></>)}
      </section>
    </Section>

    <Section title="Installed apps by size" sub="Spot big programs you no longer use" tag="READ-ONLY">
      <section className="panel pad">
        <button className="primary" disabled={!!busy} onClick={() => go('apps', async () => setApps(await api(API, '/apps')))}><Package size={17} /> {busy === 'apps' ? 'Reading…' : 'List installed apps'}</button>
        {apps && (!apps.available ? <div className="notice">{apps.reason}</div> : <>
          <p className="metric-sub">{apps.count} apps · sorted by declared size</p>
          {apps.apps.slice(0, 40).map((a, i) => <div className="info-row" key={i}><span>{a.name}<small className="sub">{a.publisher || 'Unknown publisher'}{a.version ? ` · v${a.version}` : ''}</small></span><b>{a.size_mb ? fmtBytes(a.size_mb * 1024 * 1024) : 'Size not declared'}</b></div>)}
          <p className="scope">{apps.note}</p></>)}
      </section>
    </Section>
  </>;
}
