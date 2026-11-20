import React from 'react';

export const fmtBytes = (b) => {
  if (b === null || b === undefined) return '—';
  if (b >= 1024 ** 3) return `${(b / 1024 ** 3).toFixed(2)} GB`;
  if (b >= 1024 ** 2) return `${(b / 1024 ** 2).toFixed(1)} MB`;
  if (b >= 1024) return `${Math.round(b / 1024)} KB`;
  return `${b} B`;
};

export async function api(API, path, options) {
  const r = await fetch(`${API}${path}`, options);
  let data = null;
  try { data = await r.json(); } catch { /* non-JSON error body */ }
  if (!r.ok) throw new Error((data && (data.detail || data.error)) || `Request failed (${r.status})`);
  return data;
}

export function Section({ title, sub, tag, children }) {
  return <>
    <div className="section-title"><div><h3>{title}</h3>{sub && <p>{sub}</p>}</div>{tag && <span className="muted">{tag}</span>}</div>
    {children}
  </>;
}

export const Err = ({ msg }) => msg ? <div className="error">{msg}</div> : null;
