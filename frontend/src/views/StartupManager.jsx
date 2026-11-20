import React, { useEffect, useState } from 'react';
import { Power } from 'lucide-react';
import { api, Section, Err } from './shared';

export default function StartupManager({ API }) {
  const [data, setData] = useState(null), [busy, setBusy] = useState(''), [err, setErr] = useState('');
  const load = async () => { try { setData(await api(API, '/startup')); setErr(''); } catch (e) { setErr(e.message); } };
  useEffect(() => { load(); }, []);
  async function toggle(item) {
    setBusy(item.name); setErr('');
    try { await api(API, '/startup/toggle', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: item.name, enabled: !item.enabled }) }); await load(); }
    catch (e) { setErr(e.message); } finally { setBusy(''); }
  }
  const items = data?.items || [];
  return <>
    <section className="hero"><div>
      <div className="eyebrow light">STARTUP MANAGER</div>
      <h2>{data?.available ? `${items.filter(i => i.enabled).length} of ${items.length} startup apps are enabled` : 'Control what launches with Windows.'}</h2>
      <p>Turning an app off is fully reversible and does not uninstall it. Fewer startup apps means a faster sign-in.</p>
    </div></section>
    <Err msg={err} />
    <Section title="Startup entries" sub="Registry Run keys" tag="REVERSIBLE">
      <section className="panel pad">
        {!data && <div className="empty">Loading…</div>}
        {data && !data.available && <div className="notice">{data.reason}</div>}
        {items.map((it, i) => <div className="info-row" key={`${it.name}-${i}`}>
          <span>{it.name}<small className="sub" title={it.command}>{it.scope === 'User' ? 'Your account' : 'All users'} · {it.command.slice(0, 90)}</small></span>
          {it.scope === 'User'
            ? <button className={`switch ${it.enabled ? 'on' : ''}`} disabled={busy === it.name} onClick={() => toggle(it)} aria-label={`${it.enabled ? 'Disable' : 'Enable'} ${it.name}`}><Power size={14} /> {it.enabled ? 'Enabled' : 'Disabled'}</button>
            : <b className="muted">{it.enabled ? 'Enabled' : 'Disabled'} · needs admin</b>}
        </div>)}
        {data?.available && <p className="scope">{data.note} Changes take effect at your next sign-in.</p>}
      </section>
    </Section>
  </>;
}
