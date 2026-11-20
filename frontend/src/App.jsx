import React, { useEffect, useState } from 'react';
import Advisor from './views/Advisor';
import Cleaner from './views/Cleaner';
import SpaceFinder from './views/SpaceFinder';
import StartupManager from './views/StartupManager';
import { Activity, Cpu, MemoryStick, HardDrive, ShieldCheck, RefreshCw, ScanSearch, Laptop, Battery, Thermometer, Clock3, AlertTriangle, CheckCircle2, Info, Gauge, History, ChevronRight, Sparkles, Trash2, FolderSearch, Power } from 'lucide-react';

const API = 'http://127.0.0.1:8000/api';
const fmt = (v, suffix='') => v === null || v === undefined ? '—' : `${v}${suffix}`;
function Card({icon:Icon,label,value,sub}) { return <div className="metric-card"><div className="metric-head"><span>{label}</span><Icon size={17}/></div><div className="metric-value">{value}</div><div className="metric-sub">{sub}</div></div>; }
function App(){
  const [overview,setOverview]=useState(null), [report,setReport]=useState(null), [history,setHistory]=useState([]);
  const [busy,setBusy]=useState(false), [error,setError]=useState('');
  const [storagePath,setStoragePath]=useState('C:\\');
  const [storageResult,setStorageResult]=useState(null), [processes,setProcesses]=useState([]), [startup,setStartup]=useState([]), [windowsHealth,setWindowsHealth]=useState(null), [stability,setStability]=useState(null), [diagnosticBusy,setDiagnosticBusy]=useState('');
  const [hardware,setHardware]=useState(null), [power,setPower]=useState(null), [drivers,setDrivers]=useState(null), [view,setView]=useState('overview');
  async function runDiagnostic(kind){
    setDiagnosticBusy(kind);
    try {
      let url = `${API}/diagnostics/${kind}`;
      if(kind==='storage') url += `?path=${encodeURIComponent(storagePath)}`;
      const r=await fetch(url); if(!r.ok) throw new Error(`Request failed (${r.status})`); const data=await r.json();
      if(kind==='storage') setStorageResult(data);
      if(kind==='processes') setProcesses(data.processes||[]);
      if(kind==='startup') setStartup(data.items||[]);
      if(kind==='windows') setWindowsHealth(data);
      if(kind==='stability') setStability(data);
      if(kind==='hardware') setHardware(data);
      if(kind==='power') setPower(data);
      if(kind==='drivers') setDrivers(data);
    } catch(e){setError(`Could not run ${kind} diagnostics: ${e.message}`)}
    finally{setDiagnosticBusy('')}
  }
  async function loadOverview(){
    try { const r=await fetch(`${API}/overview`); if(!r.ok) throw new Error('Diagnostic service unavailable'); setOverview(await r.json()); setError(''); }
    catch(e){setError('Cannot reach the local diagnostic service. Start backend\\start-dev.ps1 or run the launch script in the project folder.');}
  }
  async function loadHistory(){ try{const r=await fetch(`${API}/history`); const d=await r.json(); setHistory(d.scans||[]);}catch{} }
  async function scan(){
    setBusy(true); setError('');
    try {const r=await fetch(`${API}/scan`,{method:'POST'}); if(!r.ok) throw new Error('Scan failed'); setReport(await r.json()); await loadOverview(); await loadHistory();}
    catch(e){setError('Scan failed. Check that the backend is running.');}
    finally{setBusy(false);}
  }
  useEffect(()=>{loadOverview();loadHistory();const t=setInterval(loadOverview,3000);return()=>clearInterval(t);},[]);
  const m=overview?.metrics, sys=overview?.system, disk=overview?.storage||[];
  const score=report?.health_score;
  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-icon"><Activity/></div><div><b>PC DOCTOR</b><small>AI SYSTEM CARE</small></div></div>
      <div className="nav-label">WORKSPACE</div>
      {[['overview','Overview',Gauge],['advisor','Smart Advisor',Sparkles],['cleaner','Cleaner',Trash2],['space','Space Finder',FolderSearch],['startup','Startup Manager',Power],['diagnostics','Diagnostics',ScanSearch]].map(([id,label,Icon])=><button key={id} className={`nav ${view===id?'active':''}`} onClick={()=>setView(id)}><Icon size={18}/> {label}</button>)}
      <div className="sidebar-bottom"><div className="secure"><ShieldCheck size={17}/><div><b>Local-first protection</b><small>Changes only after you confirm</small></div></div><small className="version">PC Doctor AI · v3.1.0</small></div>
    </aside>
    <main className="main">
      <header className="topbar"><div><div className="eyebrow">{view.toUpperCase()} / WINDOWS</div><h1>{({overview:'Your PC at a glance',advisor:'Smart Advisor',cleaner:'Junk Cleaner',space:'Space Finder',startup:'Startup Manager',diagnostics:'Advanced diagnostics'})[view]}</h1></div><div className="top-actions"><span className="live-dot">● LIVE MONITORING</span><button className="icon-btn" onClick={loadOverview} title="Refresh"><RefreshCw size={17}/></button></div></header>
      {error && <div className="error"><AlertTriangle size={18}/>{error}</div>}
      {view==='advisor' && <Advisor API={API} go={setView}/>}
      {view==='cleaner' && <Cleaner API={API}/>}
      {view==='space' && <SpaceFinder API={API}/>}
      {view==='startup' && <StartupManager API={API}/>}
      {view==='overview' && <>
      <section className="hero">
        <div><div className="eyebrow light">PC HEALTH CHECK</div><h2>{report ? 'Your latest scan is ready.' : 'Know your PC. Keep it healthy.'}</h2><p>{report ? `Scan completed · ${new Date(report.scanned_at).toLocaleString()}` : 'Run a diagnostic scan to check hardware resources, storage and system status.'}</p><button className="primary" disabled={busy} onClick={scan}>{busy?<><RefreshCw className="spin" size={17}/> Scanning…</>:<><ScanSearch size={17}/> Run full health scan</>}</button></div>
        <div className="health-orb"><div className="orb-ring"><div className="orb-inner"><ShieldCheck size={29}/><strong>{score===undefined?'—':score}</strong><small>{report?.health_label||'NOT SCANNED'}</small></div></div></div>
      </section>
      <div className="section-title"><div><h3>Live system metrics</h3><p>Refreshes automatically every 3 seconds</p></div><span className="muted">LOCAL DEVICE</span></div>
      <section className="metrics">
        <Card icon={Cpu} label="CPU usage" value={fmt(m?.cpu_percent,'%')} sub={sys?.cpu_name||'Processor information loading'}/>
        <Card icon={MemoryStick} label="Memory usage" value={fmt(m?.memory_percent,'%')} sub={`${fmt(m?.memory_used_gb,' GB')} / ${fmt(m?.memory_total_gb,' GB')} used`}/>
        <Card icon={HardDrive} label="Highest disk usage" value={fmt(m?.disk_percent,'%')} sub={`${disk.length} volume(s) detected`}/>
        <Card icon={Clock3} label="System uptime" value={m?.boot_time?uptime(m.boot_time):'—'} sub="Since last boot"/>
      </section>
      <div className="section-title"><div><h3>Hardware & system</h3><p>Information reported by Windows</p></div></div>
      <section className="info-grid">
        <div className="panel"><div className="panel-title"><Laptop size={18}/> Device information</div><InfoRow label="Computer" value={sys?.hostname}/><InfoRow label="Manufacturer" value={sys?.manufacturer}/><InfoRow label="Model" value={sys?.model}/><InfoRow label="Operating system" value={sys?.windows_caption||sys?.platform}/><InfoRow label="Windows build" value={sys?.windows_build}/><InfoRow label="Processor" value={sys?.cpu_name}/></div>
        <div className="panel"><div className="panel-title"><Battery size={18}/> Battery & sensors</div><InfoRow label="Battery" value={overview?.battery?.available?`${overview.battery.percent}%`:'Not detected / unavailable'}/><InfoRow label="Power" value={overview?.battery?.available?(overview.battery.plugged_in?'Plugged in':'On battery'):'—'}/><InfoRow label="CPU temperature" value="Not available yet"/><InfoRow label="GPU temperature" value="Not available yet"/><div className="notice"><Info size={16}/> Sensor support will be added through a hardware-monitor provider in a later phase.</div></div>
      </section>
      <div className="section-title"><div><h3>Storage volumes</h3><p>Capacity and free-space overview</p></div></div>
      <section className="panel storage-panel">
        {disk.length ? disk.map((d,i)=><div className="disk-row" key={i}><div className="disk-name"><HardDrive size={18}/><div><b>{d.mountpoint}</b><small>{d.device} · {d.filesystem||'Filesystem unknown'}</small></div></div><div className="disk-bar-wrap"><div className="disk-bar"><span style={{width:`${d.used_percent}%`}}/></div><small>{d.used_gb} GB used of {d.total_gb} GB</small></div><b className="disk-percent">{d.used_percent}%</b></div>) : <div className="empty">Waiting for storage information…</div>}
      </section>
      {report && <><div className="section-title"><div><h3>Latest scan findings</h3><p>Transparent checks from the Phase 1 diagnostic engine</p></div><span className="muted">SCAN #{report.scan_id}</span></div><section className="panel findings">{report.findings.map((f,i)=><div className="finding" key={i}><div className={`finding-icon ${f.severity}`}>{f.severity==='success'?<CheckCircle2/>:f.severity==='warning'||f.severity==='critical'?<AlertTriangle/>:<Info/>}</div><div><b>{f.title}</b><p>{f.detail}</p></div></div>)}<p className="scope">{report.scope_note}</p></section></>}
      <div className="section-title"><div><h3>Recent scan history</h3><p>Stored locally on this PC</p></div></div>
      <section className="panel history">{history.length?history.slice(0,5).map(h=><div className="history-row" key={h.id}><div><b>System health scan</b><small>{new Date(h.scanned_at).toLocaleString()}</small></div><span className={`score ${h.health_score<65?'bad':h.health_score<85?'mid':''}`}>{h.health_score}/100</span><ChevronRight size={16}/></div>):<div className="empty">No scans yet. Run your first health scan above.</div>}</section>
      </>}
      {view==='diagnostics' && <>
      <div className="section-title"><div><h3>Advanced diagnostics</h3><p>Phase 2 · Read-only inspection · No changes are made</p></div><span className="muted">LOCAL ANALYSIS</span></div>
      <section className="panel" style={{padding:20,marginBottom:18}}>
        <div className="panel-title"><HardDrive size={18}/> Storage analyzer</div>
        <p className="metric-sub" style={{margin:'8px 0 12px'}}>Inspect top-level folder sizes. The scan reads file metadata only and never opens or deletes your files.</p>
        <div style={{display:'flex',gap:10,flexWrap:'wrap'}}><input aria-label="Folder path" value={storagePath} onChange={e=>setStoragePath(e.target.value)} placeholder="Drive or folder path, e.g. D:\\" style={{flex:'1 1 220px',padding:11,borderRadius:8,border:'1px solid #334155',background:'#0f172a',color:'white'}}/><button className="primary" disabled={!!diagnosticBusy||!storagePath.trim()} onClick={()=>runDiagnostic('storage')}>{diagnosticBusy==='storage'?'Scanning…':'Analyze folder sizes'}</button></div>
        {storageResult && <><p className="metric-sub" style={{marginTop:12}}>{storageResult.path} · {storageResult.entries_visited} entries inspected · {storageResult.elapsed_seconds}s {storageResult.truncated?'· Partial scan (safety limit reached)':''}</p>{storageResult.error?<div className="notice">{storageResult.error}</div>:<div className="findings">{storageResult.folders?.map(f=><div className="history-row" key={f.path}><div><b>{f.name}</b><small>{f.path}</small></div><b>{f.size_gb} GB</b></div>)}</div>}</>}
      </section>
      <section className="info-grid" style={{marginBottom:18}}>
        <div className="panel" style={{padding:20}}><div className="panel-title"><Activity size={18}/> Process analyzer</div><p className="metric-sub">Top processes by memory use.</p><button className="primary" disabled={!!diagnosticBusy} onClick={()=>runDiagnostic('processes')}>{diagnosticBusy==='processes'?'Loading…':'Analyze processes'}</button>{processes.slice(0,8).map(p=><div className="info-row" key={p.pid}><span>{p.name} · PID {p.pid}</span><b>{p.memory_mb} MB</b></div>)}</div>
        <div className="panel" style={{padding:20}}><div className="panel-title"><Laptop size={18}/> Startup analyzer</div><p className="metric-sub">Registry startup entries. Nothing is disabled.</p><button className="primary" disabled={!!diagnosticBusy} onClick={()=>runDiagnostic('startup')}>{diagnosticBusy==='startup'?'Loading…':'Analyze startup apps'}</button>{startup.slice(0,8).map((item,i)=><div className="info-row" key={`${item.name}-${i}`}><span>{item.name}</span><b title={item.command}>Registry entry</b></div>)}</div>
      </section>
      <section className="panel" style={{padding:20,marginBottom:18}}><div className="panel-title"><ShieldCheck size={18}/> Windows health checks</div><p className="metric-sub">Read-only physical disk, Defender and recent System event-log signals (last 7 days).</p><button className="primary" disabled={!!diagnosticBusy} onClick={()=>runDiagnostic('windows')}>{diagnosticBusy==='windows'?'Checking…':'Run Windows health checks'}</button>{windowsHealth && <><p className="metric-sub" style={{marginTop:12}}>{windowsHealth.reason||windowsHealth.note}</p>{(windowsHealth.physical_disks||[]).map((d,i)=><div className="info-row" key={i}><span>{d.FriendlyName||'Physical disk'}</span><b>{d.HealthStatus||'Status unavailable'}</b></div>)}{windowsHealth.defender && <div className="info-row"><span>Microsoft Defender real-time protection</span><b>{windowsHealth.defender.RealTimeProtectionEnabled===true?'Enabled':windowsHealth.defender.RealTimeProtectionEnabled===false?'Disabled':'Unavailable'}</b></div>}<b style={{display:'block',marginTop:14}}>Recent critical/error events</b>{(windowsHealth.critical_events||[]).slice(0,8).map((ev,i)=>{const rawTime=ev.time||ev.timestamp||ev.TimeCreated;const date=rawTime?new Date(rawTime):null;const shownTime=date&&!Number.isNaN(date.getTime())?date.toLocaleString():'Time unavailable';return <details key={`${ev.ProviderName||'event'}-${ev.Id||i}-${i}`} style={{borderBottom:'1px solid #263449',padding:'10px 0'}}><summary className="info-row" style={{cursor:'pointer'}}><span>{shownTime} · {ev.ProviderName||'Windows'} · {ev.Id||'Unknown'}</span><b>{ev.LevelDisplayName||'Event'}{ev.Count>1?` · ${ev.Count} occurrences`:''}</b></summary><p style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',fontSize:13,lineHeight:1.6,color:'#94a3b8',padding:'8px 12px'}}>{ev.Message||'No event description available.'}</p></details>})}</>}</section>
      <div className="section-title"><div><h3>Hardware, power & driver audit</h3><p>Read-only Windows inventory and battery telemetry</p></div><span className="muted">DEVICE AUDIT</span></div>
      <section className="info-grid" style={{marginBottom:18}}>
        <div className="panel" style={{padding:20}}>
          <div className="panel-title"><Laptop size={18}/> Hardware inventory</div>
          <p className="metric-sub">CPU, RAM modules, graphics adapters, BIOS and Windows device problem codes.</p>
          <button className="primary" disabled={!!diagnosticBusy} onClick={()=>runDiagnostic('hardware')}>{diagnosticBusy==='hardware'?'Checking…':'Audit hardware'}</button>
          {hardware && <><p className="metric-sub" style={{marginTop:12}}>{hardware.reason || `${hardware.cpu?.length||0} CPU record(s) · ${hardware.memory_modules?.length||0} RAM module(s) · ${hardware.video_controllers?.length||0} display adapter(s)`}</p>
            {(hardware.cpu||[]).map((x,i)=><InfoRow key={i} label="CPU" value={`${x.Name} · ${x.NumberOfCores} cores / ${x.NumberOfLogicalProcessors} threads`}/>)}
            {(hardware.memory_modules||[]).map((x,i)=><InfoRow key={i} label={`RAM ${i+1}`} value={`${x.Capacity ? (x.Capacity/1073741824).toFixed(1)+' GB' : 'Capacity unavailable'} · ${x.Speed||'—'} MHz · ${x.Manufacturer||'Manufacturer unknown'}`}/>)}
            {(hardware.video_controllers||[]).map((x,i)=><InfoRow key={i} label="Graphics" value={`${x.Name} · ${x.DriverVersion||'Driver version unavailable'}`}/>)}
            {hardware.bios && <InfoRow label="BIOS" value={`${hardware.bios.SMBIOSBIOSVersion||'—'} · ${hardware.bios.Manufacturer||''}`}/>}
            <b style={{display:'block',marginTop:12}}>Windows device problems: {hardware.device_problems?.length||0}</b>
            {(hardware.device_problems||[]).slice(0,12).map((x,i)=><InfoRow key={i} label={x.Name||'Unknown device'} value={`Code ${x.ConfigManagerErrorCode} · ${x.PNPClass||'Class unknown'}`}/>)}
            <p className="scope">{hardware.note}</p>
          </>}
        </div>
        <div className="panel" style={{padding:20}}>
          <div className="panel-title"><Battery size={18}/> Power & battery audit</div>
          <p className="metric-sub">Reads battery status/capacity exposed by the firmware and active Windows power plan. It cannot electrically load-test the charger.</p>
          <button className="primary" disabled={!!diagnosticBusy} onClick={()=>runDiagnostic('power')}>{diagnosticBusy==='power'?'Checking…':'Audit power & battery'}</button>
          {power && <><p className="metric-sub" style={{marginTop:12}}>{power.reason||power.active_power_plan||'Power plan unavailable'}</p>
            {(power.battery||[]).map((x,i)=><InfoRow key={i} label={x.Name||`Battery ${i+1}`} value={`Charge ${x.EstimatedChargeRemaining ?? '—'}% · Status ${x.Status||'—'} · Windows code ${x.BatteryStatus ?? '—'}`}/>)}
            {(power.battery_static||[]).map((x,i)=><InfoRow key={i} label="Design capacity (firmware)" value={x.DesignedCapacity ?? 'Not exposed'}/>)}
            {(power.battery_full_charge||[]).map((x,i)=><InfoRow key={i} label="Full charge capacity (firmware)" value={x.FullChargedCapacity ?? 'Not exposed'}/>)}
            {(power.battery_status||[]).map((x,i)=><InfoRow key={i} label="Battery electrical state" value={`Online ${x.PowerOnline} · Charging ${x.Charging} · Discharging ${x.Discharging}`}/>)}
            <p className="scope">{power.note}</p>
          </>}
        </div>
      </section>
      <section className="panel" style={{padding:20,marginBottom:18}}>
        <div className="panel-title"><ShieldCheck size={18}/> Signed driver inventory</div>
        <p className="metric-sub">Inventory only. Version numbers are not treated as proof that a driver is old or unsafe.</p>
        <button className="primary" disabled={!!diagnosticBusy} onClick={()=>runDiagnostic('drivers')}>{diagnosticBusy==='drivers'?'Reading…':'Read installed drivers'}</button>
        {drivers && <><p className="metric-sub" style={{marginTop:12}}>{drivers.reason||`${drivers.count} signed-driver records returned`}</p>
          {(drivers.drivers||[]).filter(x=>/display|net|bluetooth|system|storage/i.test(`${x.DeviceClass} ${x.DeviceName}`)).slice(0,30).map((x,i)=><InfoRow key={i} label={x.DeviceName||'Device'} value={`${x.DriverProviderName||'Provider unknown'} · ${x.DriverVersion||'Version unknown'} · ${x.DriverDate||'Date unknown'}`}/>)}
          <p className="scope">{drivers.note}</p>
        </>}
      </section>
      <div className="section-title"><div><h3>System stability analyzer</h3><p>Correlates shutdown, crash, storage, service and firewall events · Read-only</p></div><span className="muted">STABILITY REVIEW</span></div>
      <section className="panel" style={{padding:20,marginBottom:18}}>
        <div className="panel-title"><Activity size={18}/> System stability analysis</div>
        <p className="metric-sub" style={{margin:'8px 0 12px'}}>Reviews selected System and Application event IDs from the last 7 days. Events within 10 minutes of a shutdown/crash anchor are grouped as possible correlations, not proven causes.</p>
        <button className="primary" disabled={!!diagnosticBusy} onClick={()=>runDiagnostic('stability')}>{diagnosticBusy==='stability'?'Analyzing…':'Analyze system stability'}</button>
        {stability && <>
          <p className="metric-sub" style={{marginTop:12}}>{stability.reason || `${stability.total_events_scanned} events reviewed · ${stability.findings?.length || 0} findings · ${stability.correlations?.length || 0} possible time correlations`}</p>
          {!stability.available ? <div className="notice">{stability.reason}</div> : <>
            {stability.findings?.length ? stability.findings.map((f,i)=><details key={`${f.event_id}-${f.time}-${i}`} style={{borderBottom:'1px solid #263449',padding:'12px 0'}}>
              <summary style={{display:'flex',justifyContent:'space-between',gap:12,cursor:'pointer'}}><span><b>{f.title}</b><small style={{display:'block',color:'#94a3b8',marginTop:4}}>{f.time ? new Date(f.time).toLocaleString() : 'Time unavailable'} · {f.provider} · Event {f.event_id}</small></span><b style={{color:f.severity==='critical'?'#fb7185':f.severity==='warning'?'#fbbf24':'#60a5fa'}}>{f.severity.toUpperCase()}</b></summary>
              <p className="metric-sub" style={{marginTop:10}}>{f.explanation}</p>
              <p style={{fontSize:13,lineHeight:1.6,whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}><b>Windows evidence:</b><br/>{f.evidence || 'No event message supplied.'}</p>
              <p className="metric-sub"><b>Recommended next step:</b> {f.recommended_next_step}</p>
            </details>) : <div className="notice">No matching stability events were returned for this period. This does not guarantee the system has no issues.</div>}
            {stability.correlations?.length > 0 && <><h3 style={{marginTop:20}}>Possible event correlations</h3>{stability.correlations.map((c,i)=><div key={i} style={{padding:'12px 0',borderBottom:'1px solid #263449'}}><b>Event {c.anchor.id} · {c.anchor.provider}</b><p className="metric-sub">Anchor: {c.anchor.time ? new Date(c.anchor.time).toLocaleString() : 'Time unavailable'} · ±{c.window_minutes} minutes</p><p className="metric-sub">{c.interpretation}</p>{c.nearby_events.map((e,j)=><p key={j} className="metric-sub">{e.time ? new Date(e.time).toLocaleString() : 'Time unavailable'} · {e.provider} · {e.id} · {e.level}</p>)}</div>)}</>}
            <p className="scope">{stability.safety_note}</p>
          </>}
        </>}
      </section>
      </>}
      <footer>PC Doctor AI · v3.1 <span>Diagnostics stay on this device.</span></footer>
    </main>
  </div>;
}
function InfoRow({label,value}){return <div className="info-row"><span>{label}</span><b>{value||'Not reported'}</b></div>}
function uptime(iso){const s=Math.max(0,Math.floor((Date.now()-new Date(iso).getTime())/1000));const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return d?`${d}d ${h}h`:`${h}h ${m}m`;}
export default App;
