#!/usr/bin/env python3
"""Render dashboard/index.html from data/state.json + config.

Pure templating, no network needed. Run after run_check.py (and, on Mondays,
after the Morningstar fair-value refresh) to produce the file that then gets
published as the Artifact dashboard.
"""
import datetime as dt
import json
import sys
from zoneinfo import ZoneInfo

from common import DATA_DIR, ROOT, load_rules, load_rung_notes, load_state, load_stocks, normalize_rung_id

TIER_ORDER = ["T1", "T2", "T3", "T3.5", "T5", "T9"]
NY = ZoneInfo("America/New_York")


def format_et_label(iso_ts: str | None) -> str:
    if not iso_ts:
        return ""
    try:
        ts = dt.datetime.fromisoformat(iso_ts)
    except ValueError:
        return ""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return ts.astimezone(NY).strftime("%-I:%M %p ET")

TEMPLATE = r"""<title>__TITLE__</title>
<style>
:root{
  --bg:#f5f6f8; --surface:#ffffff; --surface-2:#eef0f3; --border:#dde1e7;
  --text:#12151c; --text-muted:#5b6472;
  --accent:#a8631f; --accent-soft:#f3e3d2;
  --good:#1f8a5f; --good-soft:#e3f3ec;
  --bad:#c23b3b; --bad-soft:#fbe9e8;
  --warn:#a8760f; --warn-soft:#f6ecd6;
  --font-display:"Iowan Old Style","Palatino Linotype",Georgia,"Times New Roman",serif;
  --font-body:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#0d1117; --surface:#151a22; --surface-2:#1b2130; --border:#262d3a;
    --text:#e6e9ef; --text-muted:#939bab;
    --accent:#d99a4e; --accent-soft:#3a2c18;
    --good:#4cbf8a; --good-soft:#123526;
    --bad:#e0645f; --bad-soft:#3a1b1a;
    --warn:#d9a441; --warn-soft:#362a11;
  }
}
:root[data-theme="dark"]{
  --bg:#0d1117; --surface:#151a22; --surface-2:#1b2130; --border:#262d3a;
  --text:#e6e9ef; --text-muted:#939bab;
  --accent:#d99a4e; --accent-soft:#3a2c18;
  --good:#4cbf8a; --good-soft:#123526;
  --bad:#e0645f; --bad-soft:#3a1b1a;
  --warn:#d9a441; --warn-soft:#362a11;
}
*{box-sizing:border-box;}
body{
  background:var(--bg); color:var(--text); font-family:var(--font-body);
  margin:0; padding:2rem 1.25rem 4rem; line-height:1.45;
}
.wrap{max-width:1080px; margin:0 auto;}
h1{font-family:var(--font-display); font-weight:600; font-size:1.9rem; margin:0 0 .2rem; text-wrap:balance;}
.subtitle{color:var(--text-muted); font-size:.92rem; margin-bottom:1.5rem;}
.subtitle b{color:var(--text);}
.stale-banner{
  background:var(--warn-soft); border:1px solid var(--warn); color:var(--warn);
  border-radius:10px; padding:.7rem 1rem; font-size:.88rem; margin-bottom:1.25rem;
}
.action-summary{
  background:var(--surface); border:1px solid var(--border); border-left:4px solid var(--accent);
  border-radius:12px; padding:.9rem 1.1rem; margin-bottom:1.25rem;
}
.action-summary.clear{border-left-color:var(--good);}
.action-summary h2{font-family:var(--font-display); font-size:1rem; margin:0 0 .15rem;}
.action-summary .sum-sub{color:var(--text-muted); font-size:.78rem; margin-bottom:.6rem;}
.action-summary ul{list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:.3rem;}
.action-summary li{
  display:flex; gap:.6rem; align-items:baseline; flex-wrap:wrap;
  padding:.35rem .5rem; border-radius:8px; background:var(--surface-2); cursor:pointer;
}
.action-summary li:hover{outline:1px solid var(--accent);}
.action-summary .s-tick{font-family:var(--font-display); font-weight:700; min-width:4.2rem;}
.action-summary .s-lvl{font-variant-numeric:tabular-nums; font-weight:600; min-width:5.2rem;}
.action-summary .s-src{color:var(--text-muted); flex:1; font-size:.8rem;}
.action-summary .s-amt{font-variant-numeric:tabular-nums; font-weight:600;}
.action-summary .s-when{color:var(--text-muted); font-size:.74rem; white-space:nowrap;}
.action-summary .s-new{color:var(--accent); font-weight:700; font-size:.74rem; white-space:nowrap;}
.summary-row{display:flex; gap:.75rem; flex-wrap:wrap; margin-bottom:1.75rem;}
.stat{
  background:var(--surface); border:1px solid var(--border); border-radius:12px;
  padding:.85rem 1.1rem; min-width:150px; flex:1;
}
.stat .n{font-family:var(--font-display); font-size:1.7rem; font-variant-numeric:tabular-nums; line-height:1;}
.stat .l{color:var(--text-muted); font-size:.78rem; text-transform:uppercase; letter-spacing:.04em; margin-top:.3rem;}
.stat.hot .n{color:var(--accent);}
.tier-section{margin-bottom:2.2rem;}
.tier-head{
  display:flex; align-items:baseline; gap:.6rem; margin-bottom:.7rem;
  border-bottom:1px solid var(--border); padding-bottom:.4rem;
}
.tier-head h2{font-family:var(--font-display); font-size:1.25rem; margin:0; font-weight:600;}
.tier-head .meta{color:var(--text-muted); font-size:.82rem;}
.cards{display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:.9rem;}
.card{
  background:var(--surface); border:1px solid var(--border); border-radius:14px;
  padding:1rem 1.1rem; display:flex; flex-direction:column; gap:.6rem;
}
.card.has-open{border-color:var(--accent);}
.card-head{display:flex; justify-content:space-between; align-items:flex-start; gap:.5rem;}
.card-head .name{font-weight:600; font-size:1.02rem;}
.card-head .sub{color:var(--text-muted); font-size:.78rem;}
.price{font-family:var(--font-display); font-size:1.5rem; font-variant-numeric:tabular-nums;}
.price-date{color:var(--text-muted); font-size:.76rem;}
.live-tag{background:var(--good-soft); color:var(--good); border-radius:999px; padding:.05rem .4rem; font-size:.68rem; font-weight:700; margin-right:.35rem; text-transform:uppercase; letter-spacing:.03em;}
.pills{display:flex; gap:.4rem; flex-wrap:wrap;}
.pill{
  border-radius:999px; padding:.2rem .55rem; font-size:.74rem; font-weight:600;
  font-variant-numeric:tabular-nums; white-space:nowrap;
}
.pill.good{background:var(--good-soft); color:var(--good);}
.pill.bad{background:var(--bad-soft); color:var(--bad);}
.pill.neutral{background:var(--surface-2); color:var(--text-muted);}
.valuation-line{color:var(--text-muted); font-size:.74rem;}
.rungs{display:flex; flex-direction:column; gap:.35rem; margin-top:.15rem;}
.rung{
  display:flex; align-items:center; gap:.55rem; border:1px solid var(--border);
  border-radius:9px; padding:.4rem .55rem; font-size:.82rem; background:var(--surface-2);
}
.rung.open{border-color:var(--accent); background:var(--accent-soft);}
.rung.done{opacity:.55;}
.rung .lvl{font-variant-numeric:tabular-nums; font-weight:600; min-width:5.2rem;}
.rung .src{color:var(--text-muted); flex:1;}
.rung .amt{font-variant-numeric:tabular-nums; font-weight:600;}
.rung input[type=checkbox]{width:16px; height:16px; accent-color:var(--accent); cursor:pointer;}
.next-hint{color:var(--text-muted); font-size:.78rem; border-top:1px dashed var(--border); padding-top:.5rem;}
.ma-strip{display:flex; gap:.5rem; flex-wrap:wrap; font-size:.72rem; color:var(--text-muted); font-variant-numeric:tabular-nums;}
.ma-strip span b{color:var(--text);}
.err{color:var(--bad); font-size:.78rem;}
.section-title{font-family:var(--font-display); font-size:1.15rem; margin:2rem 0 .6rem; font-weight:600;}
table.log{width:100%; border-collapse:collapse; font-size:.85rem; background:var(--surface); border:1px solid var(--border); border-radius:10px; overflow:hidden;}
table.log th, table.log td{text-align:left; padding:.5rem .7rem; border-bottom:1px solid var(--border);}
table.log th{background:var(--surface-2); color:var(--text-muted); font-weight:600; font-size:.74rem; text-transform:uppercase; letter-spacing:.03em;}
table.log td{font-variant-numeric:tabular-nums;}
.empty-log{color:var(--text-muted); font-size:.85rem; padding:.8rem;}
.actions-bar{display:flex; gap:.6rem; align-items:center; margin:.6rem 0 1.2rem;}
button.export{
  background:var(--surface); border:1px solid var(--border); color:var(--text);
  border-radius:8px; padding:.45rem .85rem; font-size:.82rem; cursor:pointer; font-family:var(--font-body);
}
button.export:hover{border-color:var(--accent); color:var(--accent);}
footer{color:var(--text-muted); font-size:.76rem; margin-top:2.5rem; border-top:1px solid var(--border); padding-top:1rem;}
.assumptions{
  background:var(--surface); border:1px solid var(--border); border-radius:10px;
  padding:.8rem 1rem; font-size:.82rem; color:var(--text-muted); margin-bottom:1.5rem;
}
.assumptions b{color:var(--text);}
.pill.custom{background:var(--accent-soft); color:var(--accent);}
.rung.custom{border-color:var(--accent); background:var(--accent-soft);}
.rung.custom.done{opacity:.55;}
.rung.pending{opacity:.68; border-style:dashed;}
.rung .dist{color:var(--text-muted); font-size:.72rem; white-space:nowrap;}
.rung.live-hit{opacity:1; border-style:solid; border-color:var(--good); background:var(--good-soft);}
.rung .live-hit-tag{color:var(--good); font-size:.72rem; font-weight:700; white-space:nowrap;}
.live-status{color:var(--text-muted); font-size:.76rem; margin-left:.4rem;}
.live-status.err{color:var(--bad);}
.rung .confirmed-tag{color:var(--good); font-size:.72rem; white-space:nowrap; font-weight:600;}
.rung-wrap{display:flex; flex-direction:column; gap:.15rem;}
.note-input{
  width:100%; border:1px dashed var(--border); background:transparent; color:var(--text);
  border-radius:7px; padding:.3rem .5rem; font-size:.76rem; font-family:var(--font-body);
  box-sizing:border-box;
}
.note-input::placeholder{color:var(--text-muted);}
.note-input:focus{outline:none; border-color:var(--accent); border-style:solid;}
.card-sub-title{font-size:.72rem; color:var(--text-muted); text-transform:uppercase; letter-spacing:.04em; margin-top:.2rem;}
.tabs{display:flex; gap:.4rem; margin-bottom:1.5rem; border-bottom:1px solid var(--border);}
.tab-btn{
  background:none; border:none; color:var(--text-muted); font-family:var(--font-body); font-size:.9rem;
  font-weight:600; padding:.6rem .3rem; cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-1px;
}
.tab-btn.active{color:var(--accent); border-bottom-color:var(--accent);}
.tabpanel{display:none;}
.tabpanel.active{display:block;}
.val-caption{color:var(--text-muted); font-size:.85rem; margin-bottom:1rem;}
.val-chart{background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:1rem 1.1rem; margin-bottom:1.5rem;}
.val-row{display:flex; align-items:center; gap:.7rem; padding:.4rem 0; border-bottom:1px solid var(--border);}
.val-row:last-child{border-bottom:none;}
.val-label{width:130px; flex:0 0 130px; font-size:.82rem; overflow:hidden;}
.val-label b{display:block;}
.val-label span{color:var(--text-muted); font-size:.72rem;}
.val-track{flex:1; position:relative; height:22px; background:var(--surface-2); border-radius:4px; min-width:80px;}
.val-track .zero{position:absolute; left:50%; top:0; bottom:0; width:1px; background:var(--border);}
.val-bar{position:absolute; top:2px; bottom:2px; border-radius:3px;}
.val-bar.good{background:var(--good);}
.val-bar.bad{background:var(--bad);}
.val-pct{width:60px; flex:0 0 60px; text-align:right; font-variant-numeric:tabular-nums; font-weight:600; font-size:.84rem;}
.val-pct.good{color:var(--good);}
.val-pct.bad{color:var(--bad);}
.val-legend{display:flex; gap:1.2rem; font-size:.78rem; color:var(--text-muted); margin-top:.8rem; padding-top:.6rem; border-top:1px solid var(--border);}
.val-legend .sw{display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:.35rem; vertical-align:middle;}
table.val-table{width:100%; border-collapse:collapse; font-size:.85rem; background:var(--surface); border:1px solid var(--border); border-radius:10px; overflow:hidden;}
table.val-table th, table.val-table td{text-align:right; padding:.5rem .7rem; border-bottom:1px solid var(--border);}
table.val-table th:first-child, table.val-table td:first-child{text-align:left;}
table.val-table th{background:var(--surface-2); color:var(--text-muted); font-weight:600; font-size:.74rem; text-transform:uppercase; letter-spacing:.03em;}
table.val-table td{font-variant-numeric:tabular-nums;}
table.val-table td.good{color:var(--good);}
table.val-table td.bad{color:var(--bad);}
</style>
<div class="wrap">
  <h1>DCA Alert Dashboard</h1>
  <div class="subtitle">Prices as of <b>__PRICE_DATE__</b>__LIVE_SNAPSHOT__ &middot; generated __GENERATED_AT__ &middot; fundamentals last refreshed <b>__FUND_DATE__</b></div>
  <div class="subtitle"><button class="export" id="refresh-prices-btn">Refresh live prices</button><span class="live-status" id="live-status"></span></div>
  __STALE_BANNER__
  <div class="tabs">
    <button class="tab-btn active" data-tab="alerts">Alerts &amp; ladder</button>
    <button class="tab-btn" data-tab="valuation">Valuation overview</button>
  </div>
  <div class="tabpanel active" id="tab-alerts">
    <div class="action-summary" id="action-summary"></div>
    <div class="summary-row">
      <div class="stat hot"><div class="n">__OPEN_COUNT__</div><div class="l">open triggers</div></div>
      <div class="stat"><div class="n">__STOCK_COUNT__</div><div class="l">stocks tracked</div></div>
      <div class="stat"><div class="n">__STALE_COUNT__</div><div class="l">stale data</div></div>
    </div>
    __TIER_SECTIONS__
    <div class="section-title">Action log</div>
    <div class="actions-bar">
      <button class="export" id="export-btn">Export CSV</button>
      <button class="export" id="export-notes-btn">Backup my notes</button>
      <span class="next-hint" id="export-hint"></span>
      <span class="next-hint" id="sync-status"></span>
    </div>
    <div id="log-wrap"><div class="empty-log">Nothing ticked yet.</div></div>
  </div>
  <div class="tabpanel" id="tab-valuation">
    __VALUATION_TAB__
  </div>
  <footer>
    Ticks and notes both sync across your devices via small backend endpoints (no login -- anyone with this link can view or edit them). Rule assumptions that still need your confirmation are noted in <b>README.md</b> / <b>config/rules.yaml</b>.
  </footer>
</div>
<script>
const STATE = __STATE_JSON__;
const STORE_KEY = "moomooinvest-ticks-v1";
const TICKS_API = "/api/ticks";

document.querySelectorAll(".tab-btn").forEach(btn=>{
  btn.addEventListener("click", ()=>{
    document.querySelectorAll(".tab-btn").forEach(b=>b.classList.remove("active"));
    document.querySelectorAll(".tabpanel").forEach(p=>p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
  });
});

// Ticks live server-side (via TICKS_API, backed by a small database) so a
// tick made on one device shows up on every other device -- localStorage is
// kept only as an instant-paint cache for while the fetch is in flight.
function loadTicksCache(){
  try { return JSON.parse(localStorage.getItem(STORE_KEY) || "{}"); } catch(e){ return {}; }
}
function saveTicksCache(t){ try { localStorage.setItem(STORE_KEY, JSON.stringify(t)); } catch(e){} }

let ticksLoaded = false;

function renderLog(){
  const ticks = loadTicksCache();
  const rows = Object.values(ticks).sort((a,b)=> (b.tickedAt||"").localeCompare(a.tickedAt||""));
  const wrap = document.getElementById("log-wrap");
  if(!rows.length){ wrap.innerHTML = '<div class="empty-log">Nothing ticked yet.</div>'; return; }
  let html = '<table class="log"><thead><tr><th>Ticked</th><th>Ticker</th><th>Tier</th><th>Rung</th><th>Level</th><th>Multiplier</th><th>Amount</th><th>First hit</th></tr></thead><tbody>';
  for(const r of rows){
    html += `<tr><td>${r.tickedAt ? r.tickedAt.slice(0,16).replace('T',' ') : ''}</td><td>${r.ticker}</td><td>${r.tier}</td><td>${r.source}</td><td>${r.level}</td><td>x${r.multiplier}</td><td>${r.amount}</td><td>${r.firstHit}</td></tr>`;
  }
  html += '</tbody></table>';
  wrap.innerHTML = html;
}

function confirmedLabel(iso){
  if(!iso) return "confirmed";
  const d = new Date(iso);
  if(isNaN(d)) return "confirmed";
  const today = new Date();
  const sameDay = d.toDateString() === today.toDateString();
  return sameDay ? "confirmed today" : "confirmed " + d.toISOString().slice(0,10);
}

// What still needs doing, at the top of the page: every rung that has a
// checkbox (i.e. its level was reached) and is NOT ticked yet. Rungs you
// already confirmed are deliberately left out -- the point is to answer
// "what do I act on right now" in one glance, so anything already handled
// is noise. It reads the checkboxes rather than state.json because only the
// browser knows what's ticked: tick state lives in the sync backend, not in
// the committed state the page is built from. That also means it covers
// intraday live hits and custom targets for free, since those are checkboxes
// too.
const CURRENCY = "__CURRENCY__";

function renderActionSummary(){
  const el = document.getElementById("action-summary");
  if(!el) return;

  const rows = [];
  document.querySelectorAll('input[type=checkbox][data-id]').forEach(cb=>{
    if(cb.checked) return;
    rows.push({
      id: cb.dataset.id,
      ticker: cb.dataset.ticker || "",
      level: cb.dataset.level,
      source: cb.dataset.source || "",
      amount: parseFloat(cb.dataset.amount) || 0,
      firstHit: cb.dataset.firsthit || "",
    });
  });

  if(!rows.length){
    el.classList.add("clear");
    el.innerHTML = '<h2>Nothing to act on</h2>' +
      '<div class="sum-sub">No threshold is waiting for you. Anything already confirmed is in the Action log below.</div>';
    return;
  }

  const today = etDateStr();
  rows.sort((a, b) => (b.firstHit || "").localeCompare(a.firstHit || "") || a.ticker.localeCompare(b.ticker));
  const total = rows.reduce((sum, r) => sum + r.amount, 0);
  const todayCount = rows.filter(r => r.firstHit === today).length;

  el.classList.remove("clear");
  el.innerHTML =
    '<h2>' + rows.length + ' threshold' + (rows.length === 1 ? '' : 's') + ' waiting — ' +
      CURRENCY + ' ' + total.toLocaleString("en-US", {maximumFractionDigits: 0}) + ' if you take them all</h2>' +
    '<div class="sum-sub">' +
      (todayCount ? todayCount + ' hit today. ' : '') +
      'Hit but not yet ticked. Confirmed ones are not listed.</div>' +
    '<ul>' + rows.map(r =>
      '<li data-goto="' + r.ticker + '">' +
        '<span class="s-tick">' + r.ticker + '</span>' +
        '<span class="s-lvl">' + fmtLivePrice(parseFloat(r.level)) + '</span>' +
        '<span class="s-src">' + r.source + '</span>' +
        '<span class="s-amt">' + CURRENCY + ' ' + r.amount.toLocaleString("en-US", {maximumFractionDigits: 0}) + '</span>' +
        (r.firstHit === today
          ? '<span class="s-new">hit today</span>'
          : '<span class="s-when">hit ' + r.firstHit + '</span>') +
      '</li>').join('') +
    '</ul>';
}

// Jump to the stock's card from the summary.
document.addEventListener("click", (e)=>{
  const li = e.target.closest('.action-summary li[data-goto]');
  if(!li) return;
  const card = document.querySelector('.card[data-ticker="' + li.dataset.goto + '"]');
  if(card) card.scrollIntoView({behavior: "smooth", block: "center"});
});

function applyTicksToDom(ticks){
  document.querySelectorAll('input[type=checkbox][data-id]').forEach(cb=>{
    const entry = ticks[cb.dataset.id];
    cb.checked = !!entry;
    const rungEl = cb.closest(".rung");
    if(rungEl){ rungEl.classList.toggle("done", !!entry); }
  });
  document.querySelectorAll('.confirmed-tag').forEach(tag=>{
    const id = tag.dataset.confirmFor;
    const entry = ticks[id];
    tag.textContent = entry ? ("✓ " + confirmedLabel(entry.tickedAt)) : "";
  });
  renderLog();
  renderActionSummary();
}

// Ticks and notes sync independently -- keep their statuses separate so
// one channel succeeding doesn't silently clobber the other's error.
const syncStatusByChannel = {ticks: "", notes: ""};
function setSyncStatus(msg, channel){
  syncStatusByChannel[channel || "ticks"] = msg || "";
  const el = document.getElementById("sync-status");
  if(el) el.textContent = [syncStatusByChannel.ticks, syncStatusByChannel.notes].filter(Boolean).join(" ");
}

async function fetchTicks(){
  const res = await fetch(TICKS_API, {method: "GET"});
  if(!res.ok) throw new Error("bad status " + res.status);
  return res.json();
}

async function pushTick(id, entry){
  const res = await fetch(TICKS_API, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(entry ? {id, entry} : {id, remove: true}),
  });
  if(!res.ok) throw new Error("bad status " + res.status);
  return res.json();
}

async function syncTicksFromServer(){
  try {
    const ticks = await fetchTicks();
    saveTicksCache(ticks);
    applyTicksToDom(ticks);
    ticksLoaded = true;
    setSyncStatus("", "ticks");
  } catch(e){
    setSyncStatus("Couldn't reach the tick sync backend -- showing this device's last known state.", "ticks");
  }
}

function onToggle(cb){
  const ticks = loadTicksCache();
  const id = cb.dataset.id;
  let entry = null;
  if(cb.checked){
    entry = {
      ticker: cb.dataset.ticker, tier: cb.dataset.tier, source: cb.dataset.source,
      level: cb.dataset.level, multiplier: cb.dataset.multiplier, amount: cb.dataset.amount,
      firstHit: cb.dataset.firsthit, tickedAt: new Date().toISOString()
    };
    ticks[id] = entry;
  } else {
    delete ticks[id];
  }
  saveTicksCache(ticks);
  applyTicksToDom(ticks);
  pushTick(id, entry).catch(()=>{
    setSyncStatus("Couldn't save that tick to the sync backend -- it's saved on this device only for now. Reload once it's back to retry.", "ticks");
  });
}

document.addEventListener("change", (e)=>{
  if(e.target.matches('input[type=checkbox][data-id]')) onToggle(e.target);
});

function applyStoredTicks(){
  // Instant paint from the local cache while the network fetch is in
  // flight; syncTicksFromServer() overwrites this once it lands.
  applyTicksToDom(loadTicksCache());
}

async function exportCsv(){
  const ticks = Object.values(loadTicksCache());
  const header = "tickedAt,ticker,tier,source,level,multiplier,amount,firstHit";
  const lines = [header, ...ticks.map(r=>[r.tickedAt,r.ticker,r.tier,r.source,r.level,r.multiplier,r.amount,r.firstHit].map(v=>`"${String(v??'').replace(/"/g,'""')}"`).join(","))];
  const csv = lines.join("\n");
  const downloads = (window.claude && window.claude.use) ? await window.claude.use("downloads") : null;
  if(downloads){
    try {
      await downloads.save({filename: "moomooinvest-action-log.csv", data: csv});
      document.getElementById("export-hint").textContent = "Saved.";
      return;
    } catch(e){ /* fall through to clipboard fallback */ }
  }
  try {
    await navigator.clipboard.writeText(csv);
    document.getElementById("export-hint").textContent = "Downloads unavailable here — copied CSV to clipboard instead.";
  } catch(e){
    document.getElementById("export-hint").textContent = "Could not export automatically — open browser console to copy STATE/localStorage manually.";
  }
}
document.getElementById("export-btn").addEventListener("click", exportCsv);

// Notes sync server-side too, same pattern as ticks (api/notes.js backed
// by the same database) -- localStorage is just the instant-paint cache.
const NOTES_KEY = "moomooinvest-rung-notes-v1";
const NOTES_API = "/api/notes";
function loadNotesCache(){ try { return JSON.parse(localStorage.getItem(NOTES_KEY) || "{}"); } catch(e){ return {}; } }
function saveNotesCache(n){ try { localStorage.setItem(NOTES_KEY, JSON.stringify(n)); } catch(e){} }

function applyNotesToDom(notes){
  document.querySelectorAll('.note-input').forEach(inp=>{
    const key = inp.dataset.noteKey;
    if(Object.prototype.hasOwnProperty.call(notes, key)){
      if(document.activeElement !== inp){ inp.value = notes[key]; }
    }
  });
}

function applyStoredNotes(){
  // Instant paint from the local cache while the network fetch is in
  // flight; syncNotesFromServer() overwrites this once it lands.
  applyNotesToDom(loadNotesCache());
}

async function fetchNotes(){
  const res = await fetch(NOTES_API, {method: "GET"});
  if(!res.ok) throw new Error("bad status " + res.status);
  return res.json();
}

async function pushNote(key, text){
  const res = await fetch(NOTES_API, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({key, text}),
  });
  if(!res.ok) throw new Error("bad status " + res.status);
  return res.json();
}

async function syncNotesFromServer(){
  try {
    const notes = await fetchNotes();
    saveNotesCache(notes);
    applyNotesToDom(notes);
    setSyncStatus("", "notes");
  } catch(e){
    setSyncStatus("Couldn't reach the notes sync backend -- showing this device's last known state.", "notes");
  }
}

document.addEventListener("change", (e)=>{
  if(!e.target.matches('.note-input')) return;
  const notes = loadNotesCache();
  const key = e.target.dataset.noteKey;
  const val = e.target.value.trim();
  if(val){ notes[key] = val; } else { delete notes[key]; }
  saveNotesCache(notes);
  pushNote(key, val).catch(()=>{
    setSyncStatus("Couldn't save that note to the sync backend -- it's saved on this device only for now. Reload once it's back to retry.", "notes");
  });
});

async function exportNotes(){
  const rows = [];
  document.querySelectorAll('.note-input').forEach(inp=>{
    const val = inp.value.trim();
    if(!val) return;
    const card = inp.closest('.card');
    const ticker = card ? card.dataset.ticker : '';
    const rungEl = inp.closest('.rung');
    const lvl = rungEl ? (rungEl.querySelector('.lvl')?.textContent || '') : '';
    const src = rungEl ? (rungEl.querySelector('.src')?.textContent || '') : '';
    rows.push({ticker, key: inp.dataset.noteKey, level: lvl, source: src, note: val});
  });
  let md = "# My rung notes -- moomooinvest\n\n";
  md += "Exported " + new Date().toISOString() + " -- a local backup copy only. Notes already sync live across your devices via the notes backend; you don't need this file for that.\n\n";
  if(!rows.length){
    md += "_(no notes yet -- type into any rung's note field on the dashboard, then re-download)_\n";
  }
  for(const r of rows){
    md += `## ${r.ticker} -- ${r.source} @ ${r.level}\n`;
    md += `(key: \`${r.key}\`)\n\n${r.note}\n\n`;
  }
  const downloads = (window.claude && window.claude.use) ? await window.claude.use("downloads") : null;
  if(downloads){
    try {
      await downloads.save({filename: "moomooinvest-rung-notes.md", data: md});
      document.getElementById("export-hint").textContent = "Saved.";
      return;
    } catch(e){ /* fall through to clipboard fallback */ }
  }
  try {
    await navigator.clipboard.writeText(md);
    document.getElementById("export-hint").textContent = "Downloads unavailable here — copied notes to clipboard instead.";
  } catch(e){
    document.getElementById("export-hint").textContent = "Could not export automatically — open browser console to copy notes manually.";
  }
}
document.getElementById("export-notes-btn").addEventListener("click", exportNotes);

// ---------------------------------------------------------------------------
// Live prices.
//
// data/state.json only ever holds the daily close plus, at best, one
// intraday snapshot whenever GitHub got round to running the cron. /api/quote
// fetches real quotes server-side on demand, so opening this page during the
// session shows a price seconds old rather than hours.
//
// Display only: the MA ladder levels and which rungs have officially "fired"
// are still decided by run_check.py off the daily close. What updates here is
// the price shown, the distance to each pending rung, and a "hit now" flag on
// any pending rung the live price has already reached.
const QUOTE_API = "/api/quote";
const LIVE_REFRESH_MS = 60000;

function nyNow(){
  const parts = {};
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", weekday: "short",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  });
  for(const part of fmt.formatToParts(new Date())) parts[part.type] = part.value;
  return parts;
}

// Market holidays aren't tracked -- on one the quote just repeats the previous
// session's last print, same as the rest of the page would show anyway.
function marketOpenNow(){
  const p = nyNow();
  if(p.weekday === "Sat" || p.weekday === "Sun") return false;
  const mins = (parseInt(p.hour, 10) % 24) * 60 + parseInt(p.minute, 10);
  return mins >= 570 && mins <= 960;  // 09:30 - 16:00 ET
}

function fmtLivePrice(v){
  return "$" + v.toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

function etTimeLabel(iso){
  if(!iso) return "";
  return new Date(iso).toLocaleTimeString("en-US", {
    timeZone: "America/New_York", hour: "numeric", minute: "2-digit",
  }) + " ET";
}

function applyQuote(card, quote){
  const price = quote && quote.price;
  if(typeof price !== "number" || !isFinite(price)) return;

  const priceEl = card.querySelector(".price");
  if(priceEl) priceEl.textContent = fmtLivePrice(price);

  const sub = card.querySelector(".price-sub");
  if(sub){
    const close = parseFloat(card.dataset.close);
    const closeLine = isFinite(close)
      ? '<div class="price-date" style="opacity:.65">close ' + fmtLivePrice(close) +
        " &middot; " + (card.dataset.closeDate || "-") + "</div>"
      : "";
    sub.innerHTML = '<div class="price-date"><span class="live-tag">live</span>' +
      etTimeLabel(quote.at) + "</div>" + closeLine;
  }

  card.querySelectorAll(".rung[data-level]").forEach((rung) => {
    // Rungs already fired this period keep whatever run_check.py decided;
    // re-labelling them from a live price would contradict the stored state.
    if(rung.dataset.open === "1") return;
    const level = parseFloat(rung.dataset.level);
    if(!isFinite(level)) return;

    const dist = rung.querySelector(".dist");
    if(dist){
      const pct = (level - price) / price * 100;
      dist.textContent = (pct >= 0 ? "+" : "") + pct.toFixed(1) + "% away";
    }

    const hit = price <= level;
    rung.classList.toggle("live-hit", hit);
    let tag = rung.querySelector(".live-hit-tag");
    if(hit && !tag){
      tag = document.createElement("span");
      tag.className = "live-hit-tag";
      tag.textContent = "hit now";
      rung.appendChild(tag);
    }else if(!hit && tag){
      tag.remove();
    }
    syncLiveCheckbox(card, rung, hit);
  });
}

// A rung the live price has reached needs a checkbox you can actually tick.
//
// The daily run only fires rungs against the closing price, so without this
// a level touched at 10am that recovers by 4pm never becomes tickable at
// all -- and even one that does hold only gets its checkbox hours later,
// after the close. You buy during the session, so the box has to exist
// during the session.
//
// The id is built the same way the server builds it --
// ticker|rung-id|trading-date -- so when tonight's run fires this rung with
// first_hit_date set to the same date, the server-rendered checkbox inherits
// the tick and the ✓ simply stays put. Nothing needs reconciling.
//
// Only while the market is open: outside the session "today in New York"
// may not be a trading day, and an id carrying a non-trading date would
// never be matched by a later run.
function etDateStr(){
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());
}

let liveCheckboxAdded = false;
function syncLiveCheckbox(card, rung, hit){
  const existing = rung.querySelector('input[type=checkbox][data-live-injected]');

  if(!hit || !marketOpenNow()){
    // Never destroy a tick: if it's already checked, the buy happened and
    // the row stays. Only an untouched box is cleaned up when price lifts
    // back above the level.
    if(existing && !existing.checked){
      existing.remove();
      const tag = rung.querySelector('.confirmed-tag[data-live-injected]');
      if(tag) tag.remove();
    }
    return;
  }
  if(existing) return;

  const id = card.dataset.ticker + "|" + rung.dataset.rungId + "|" + etDateStr();
  const cb = document.createElement("input");
  cb.type = "checkbox";
  cb.dataset.liveInjected = "1";
  cb.dataset.id = id;
  cb.dataset.ticker = card.dataset.ticker;
  cb.dataset.tier = card.dataset.tier || "";
  cb.dataset.source = rung.dataset.source || "";
  cb.dataset.level = rung.dataset.level || "";
  cb.dataset.multiplier = rung.dataset.multiplier || "";
  cb.dataset.amount = rung.dataset.amount || "";
  cb.dataset.firsthit = etDateStr();
  rung.insertBefore(cb, rung.firstChild);

  const tag = document.createElement("span");
  tag.className = "confirmed-tag";
  tag.dataset.confirmFor = id;
  tag.dataset.liveInjected = "1";
  rung.appendChild(tag);

  liveCheckboxAdded = true;
}

function setLiveStatus(msg, isError){
  const el = document.getElementById("live-status");
  if(!el) return;
  el.textContent = msg || "";
  el.classList.toggle("err", !!isError);
}

let liveRefreshInFlight = false;
async function refreshLivePrices(manual){
  if(liveRefreshInFlight) return;
  const cards = [...document.querySelectorAll(".card[data-ticker]")];
  const tickers = [...new Set(cards.map((c) => c.dataset.ticker).filter(Boolean))];
  if(!tickers.length) return;

  liveRefreshInFlight = true;
  setLiveStatus("Fetching live prices…");
  try{
    const res = await fetch(QUOTE_API + "?tickers=" + encodeURIComponent(tickers.join(",")));
    if(!res.ok) throw new Error("quote endpoint returned " + res.status);
    const data = await res.json();
    const quotes = (data && data.quotes) || {};
    let applied = 0;
    for(const card of cards){
      const quote = quotes[card.dataset.ticker];
      if(quote){ applyQuote(card, quote); applied++; }
    }
    if(!applied) throw new Error("no quotes returned");
    if(liveCheckboxAdded){
      liveCheckboxAdded = false;
      applyTicksToDom(loadTicksCache());
    }
    renderActionSummary();
    const missing = tickers.length - applied;
    setLiveStatus(
      "Live as of " + new Date().toLocaleTimeString() +
      (missing ? " (" + missing + " stock(s) unavailable, showing their last close)" : ""),
      false
    );
  }catch(err){
    // Failure is not a broken page: every card still shows the committed
    // close from data/state.json, which is exactly the old behaviour.
    setLiveStatus(
      "Couldn't fetch live prices — showing the last close from the daily run." +
      (manual ? " (" + String((err && err.message) || err) + ")" : ""),
      true
    );
  }finally{
    liveRefreshInFlight = false;
  }
}

const refreshBtn = document.getElementById("refresh-prices-btn");
if(refreshBtn) refreshBtn.addEventListener("click", () => refreshLivePrices(true));

applyStoredTicks();
applyStoredNotes();
renderLog();
syncTicksFromServer();
syncNotesFromServer();

// One fetch on load whatever the clock says (outside the session it simply
// shows the last print, which is still more current than a day-old commit),
// then keep it ticking only while the market is actually open.
refreshLivePrices(false);
setInterval(() => { if(marketOpenNow()) refreshLivePrices(false); }, LIVE_REFRESH_MS);
// Coming back to a tab left open overnight should not keep showing yesterday.
document.addEventListener("visibilitychange", () => {
  if(!document.hidden) refreshLivePrices(false);
});
</script>
"""


def fmt_money(v: float | None, currency: str) -> str:
    if v is None:
        return "-"
    return f"{currency} {v:,.2f}"


def fmt_price(v: float | None) -> str:
    if v is None:
        return "-"
    return f"${v:,.2f}"


def pill(text: str, cls: str) -> str:
    return f'<span class="pill {cls}">{text}</span>'


def html_escape(v: str) -> str:
    return (
        str(v)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_rung(
    ticker: str,
    tier: str,
    rung: dict,
    is_open: bool,
    extra_cls: str = "",
    price: float | None = None,
    note: str | None = None,
) -> str:
    status_cls = ("open " + extra_cls).strip() if is_open else extra_cls
    checkbox = ""
    confirmed_tag = ""
    if is_open:
        rid = f"{ticker}|{rung.get('id')}|{rung.get('first_hit_date','')}"
        checkbox = (
            f'<input type="checkbox" data-id="{rid}" data-ticker="{ticker}" data-tier="{tier}" '
            f'data-source="{rung.get("source")}" data-level="{rung.get("level")}" '
            f'data-multiplier="{rung.get("multiplier","-")}" data-amount="{rung.get("amount","")}" '
            f'data-firsthit="{rung.get("first_hit_date","")}">'
        )
        confirmed_tag = f'<span class="confirmed-tag" data-confirm-for="{rid}"></span>'
    amt = f'{rung.get("amount"):,.0f}' if rung.get("amount") is not None else ""
    mult_txt = f'x{rung.get("multiplier")}' if rung.get("multiplier") is not None else "your target"
    dist_html = ""
    if not is_open and price and rung.get("level"):
        dist = (rung["level"] - price) / price * 100
        dist_html = f'<span class="dist">{dist:+.1f}% away</span>'
    note_key = f"{ticker}|{rung.get('id')}"
    note_input = (
        f'<input type="text" class="note-input" data-note-key="{html_escape(note_key)}" '
        f'value="{html_escape(note or "")}" placeholder="add a note: target price / reasoning...">'
    )
    return (
        f'<div class="rung-wrap">'
        # data-level / data-open let the live-price refresher recompute
        # "% away" and flag a rung the live price has reached, without
        # re-rendering the card.
        f'<div class="rung {status_cls}" data-level="{rung.get("level", "")}" '
        f'data-open="{1 if is_open else 0}" data-rung-id="{html_escape(rung.get("id", ""))}" '
        f'data-source="{html_escape(rung.get("source", ""))}" '
        f'data-multiplier="{rung.get("multiplier", "")}" '
        f'data-amount="{rung.get("amount", "")}">{checkbox}'
        f'<span class="lvl">{fmt_price(rung.get("level"))}</span>'
        f'<span class="src">{rung.get("source")}</span>'
        f'<span class="amt">{mult_txt}{" &middot; " + amt if amt else ""}</span>'
        f"{dist_html}{confirmed_tag}"
        f"</div>"
        f"{note_input}"
        f"</div>"
    )


def render_card(ticker: str, s: dict, rules: dict, rung_notes: dict | None = None) -> str:
    tier = s.get("tier", "?")
    currency = rules.get("currency", "SGD")
    price = s.get("display_price", s.get("price"))
    fired = s.get("fired_this_period", []) or []
    fired_by_id = {f["id"]: f for f in fired}
    tier_cfg = rules.get("tiers", {}).get(tier) or {}
    base_amount = tier_cfg.get("base_amount")
    is_single_trigger = len(tier_cfg.get("ma_ladder", [])) == 1
    has_open = len(fired) > 0
    ticker_notes = {
        normalize_rung_id(k): v for k, v in ((rung_notes or {}).get(ticker) or {}).items()
    }

    def note_for(rung_id):
        return ticker_notes.get(normalize_rung_id(rung_id))

    pills = []
    if not s.get("is_etf") and s.get("vs_target_pct") is not None:
        v = s["vs_target_pct"]
        cls = "good" if v > 0 else "bad"
        pills.append(pill(f'{v:+.1f}% vs target', cls))
    if not s.get("is_etf") and s.get("vs_fair_value_pct") is not None:
        v = s["vs_fair_value_pct"]
        cls = "good" if v > 0 else "bad"
        pills.append(pill(f'{v:+.1f}% vs fair value', cls))
    valuation_line = ""
    if not s.get("is_etf") and (s.get("target_price") is not None or s.get("fair_value") is not None):
        parts = []
        if s.get("target_price") is not None:
            parts.append(f"Target {fmt_price(s.get('target_price'))}")
        if s.get("fair_value") is not None:
            parts.append(f"Fair value {fmt_price(s.get('fair_value'))}")
        valuation_line = f'<div class="valuation-line">{" &middot; ".join(parts)}</div>'
    if s.get("clustered"):
        pills.append(pill("2+ MAs merged into one support", "neutral"))
    # Surface an active per-stock ladder override, so a ladder that doesn't
    # look like the tier's default has its reason visible on the card rather
    # than only in stocks.yaml.
    lcfg = s.get("ladder_config") or {}
    if lcfg.get("drop_step_pct") is not None and lcfg["drop_step_pct"] != rules.get("drop_step_pct"):
        pills.append(pill(f'{lcfg["drop_step_pct"]:g}% steps (not {rules.get("drop_step_pct"):g}%)', "neutral"))
    if lcfg.get("start_ma"):
        pills.append(pill(f'ladder starts at MA{lcfg["start_ma"]}', "neutral"))
    if lcfg.get("skip_top_rungs"):
        pills.append(pill(f'top {lcfg["skip_top_rungs"]} rung(s) skipped', "neutral"))
    custom_rungs = s.get("custom_rungs_today") or []
    if custom_rungs:
        pills.append(pill(f'{len(custom_rungs)} your target(s)', "custom"))
    if s.get("data_stale"):
        pills.append(pill("stale data", "bad"))

    # Always show the full planned ladder for this period -- fired rungs as
    # actionable/checkable, not-yet-fired rungs as a dashed "pending" preview
    # with their distance from the current price -- so the whole plan is
    # visible up front, not just what's already triggered.
    ladder = s.get("ladder", []) or []
    ladder_ids = {r["id"] for r in ladder}
    next_rung = s.get("next_rung")

    if is_single_trigger:
        # T5/T9 are deliberately single-trigger: show just the one live
        # target (the MA level, or -- once that's fired -- wherever the
        # drop cascade currently sits) instead of every cascade step ever
        # fired, which used to blow the card up into a wall of rungs.
        if next_rung:
            note = note_for(next_rung["id"])
            preview = dict(next_rung)
            if base_amount is not None:
                preview["amount"] = round(base_amount * next_rung["multiplier"], 2)
            rungs_html = render_rung(ticker, tier, preview, False, extra_cls="pending", price=price, note=note)
        elif fired:
            last_fired = fired[-1]
            rungs_html = render_rung(ticker, tier, last_fired, True, note=note_for(last_fired["id"]))
        else:
            rungs_html = ""
    else:
        plan_rows = []
        for rung in ladder:
            note = note_for(rung["id"])
            fired_entry = fired_by_id.get(rung["id"])
            if fired_entry:
                plan_rows.append(render_rung(ticker, tier, fired_entry, True, note=note))
            else:
                preview = dict(rung)
                if base_amount is not None:
                    preview["amount"] = round(base_amount * rung["multiplier"], 2)
                plan_rows.append(render_rung(ticker, tier, preview, False, extra_cls="pending", price=price, note=note))
        extra_fired = [f for f in fired if f["id"] not in ladder_ids]
        plan_rows += [render_rung(ticker, tier, f, True, note=note_for(f["id"])) for f in extra_fired]
        rungs_html = "".join(plan_rows)

    fired_custom_ids = {f["id"] for f in (s.get("fired_custom") or [])}
    custom_html = ""
    if custom_rungs:
        rows = []
        for r in custom_rungs:
            is_fired = r["id"] in fired_custom_ids
            rows.append(render_rung(ticker, tier, r, is_fired, extra_cls="custom", price=price))
        custom_html = f'<div class="card-sub-title">Your targets (always-on, no period reset)</div><div class="rungs">{"".join(rows)}</div>'

    # Only surface "Next" separately when it's a below-the-ladder cascade
    # projection not already shown as a pending rung above (avoids showing
    # the same level twice). Single-trigger tiers already show that
    # projection as their one rung, so they never need this line.
    next_html = ""
    if is_single_trigger:
        pass
    elif next_rung and price and next_rung["id"] not in ladder_ids:
        dist = (next_rung["level"] - price) / price * 100 if price else None
        dist_txt = f" ({dist:+.1f}% away)" if dist is not None else ""
        next_html = f'<div class="next-hint">Next: {next_rung["source"]} at {fmt_price(next_rung["level"])} ×{next_rung["multiplier"]}{dist_txt}</div>'
    elif not next_rung and ladder:
        next_html = '<div class="next-hint">All rungs for this period have fired.</div>'

    mas = s.get("mas") or {}
    ma_strip = "".join(
        f'<span>MA{p}: <b>{fmt_price(mas.get(str(p)))}</b></span>' for p in [60, 100, 150, 200, 250] if mas.get(str(p)) is not None
    )

    period = s.get("period", {})
    period_txt = f'{period.get("type","-")} · resets after {period.get("start_date","-")}'

    err_html = f'<div class="err">{s.get("error")}</div>' if s.get("error") else ""

    if s.get("is_live"):
        time_label = format_et_label(s.get("intraday_price_at"))
        price_sub = (
            f'<div class="price-date"><span class="live-tag">live</span>{time_label}</div>'
            f'<div class="price-date" style="opacity:.65">close {fmt_price(s.get("price"))} &middot; {s.get("price_date","-")}</div>'
        )
    else:
        price_sub = f'<div class="price-date">{s.get("price_date","-")}</div>'

    return f"""<div class="card {'has-open' if has_open else ''}" data-ticker="{ticker}" data-tier="{tier}" data-close="{s.get('price') if s.get('price') is not None else ''}" data-close-date="{s.get('price_date','-')}">
  <div class="card-head">
    <div><div class="name">{ticker} <span class="sub">{s.get('name','')}</span></div><div class="sub">{tier} &middot; {period_txt}</div></div>
    <div class="price-box" style="text-align:right;"><div class="price">{fmt_price(price)}</div><div class="price-sub">{price_sub}</div></div>
  </div>
  <div class="pills">{''.join(pills)}</div>
  {valuation_line}
  <div class="ma-strip">{ma_strip}</div>
  <div class="rungs">{rungs_html if rungs_html else '<div class="next-hint">No ladder available (missing MA data).</div>'}</div>
  {next_html}
  {custom_html}
  {err_html}
</div>"""


def pct_diff(price: float | None, ref: float | None) -> float | None:
    """Upside (positive) or downside (negative) from the current price to
    a reference (target/fair value), e.g. price 360 vs fair value 650 is
    +80.6% -- 80.6% upside if it reaches fair value."""
    if price is None or ref is None or price == 0:
        return None
    return round((ref - price) / price * 100, 2)


def collect_valuation_rows(stocks_cfg: dict, stocks_state: dict, tiers: set) -> list[dict]:
    """Build valuation rows straight from config, independent of whether
    run_check.py has ever produced a state.json entry for that ticker yet
    (a freshly-added stock has no price until the next real price fetch --
    still worth showing target/fair value for, with the % columns pending)."""
    rows = []
    for ticker, cfg in stocks_cfg.items():
        if cfg.get("tier") not in tiers or cfg.get("is_etf"):
            continue
        if cfg.get("target_price") is None and cfg.get("fair_value") is None:
            continue
        s = stocks_state.get(ticker) or {}
        price = s.get("display_price", s.get("price"))
        rows.append(
            {
                "ticker": ticker,
                "name": cfg.get("name", ticker),
                "tier": cfg.get("tier"),
                "price": price,
                "target_price": cfg.get("target_price"),
                "fair_value": cfg.get("fair_value"),
                "vs_target_pct": pct_diff(price, cfg.get("target_price")),
                "vs_fair_value_pct": pct_diff(price, cfg.get("fair_value")),
            }
        )
    return rows


def render_val_row(s: dict, max_abs: float) -> str:
    ticker = s["ticker"]
    pct = s["vs_fair_value_pct"]
    if pct is None:
        return f"""<div class="val-row">
  <div class="val-label"><b>{ticker}</b><span>{s.get('tier','')} &middot; fair {fmt_price(s.get('fair_value'))}</span></div>
  <div class="val-track"><div class="zero"></div></div>
  <div class="val-pct" style="color:var(--text-muted)">pending</div>
</div>"""
    cls = "good" if pct > 0 else "bad"
    half_pct = min(abs(pct) / max_abs * 50, 50) if max_abs else 0
    if pct > 0:
        style = f"right:50%; width:{half_pct:.2f}%;"
    else:
        style = f"left:50%; width:{half_pct:.2f}%;"
    return f"""<div class="val-row">
  <div class="val-label"><b>{ticker}</b><span>{s.get('tier','')} &middot; fair {fmt_price(s.get('fair_value'))}</span></div>
  <div class="val-track"><div class="zero"></div><div class="val-bar {cls}" style="{style}"></div></div>
  <div class="val-pct {cls}">{pct:+.1f}%</div>
</div>"""


def render_val_table_row(s: dict) -> str:
    tp, fp = s["vs_target_pct"], s["vs_fair_value_pct"]
    tp_txt = f'<td class="{"good" if tp > 0 else "bad"}">{tp:+.1f}%</td>' if tp is not None else '<td style="color:var(--text-muted)">pending</td>'
    fp_txt = f'<td class="{"good" if fp > 0 else "bad"}">{fp:+.1f}%</td>' if fp is not None else '<td style="color:var(--text-muted)">pending</td>'
    return (
        f"<tr><td>{s['ticker']} <span style='color:var(--text-muted)'>{s.get('name','')}</span></td>"
        f"<td>{s.get('tier','')}</td>"
        f"<td>{fmt_price(s.get('display_price', s.get('price')))}</td>"
        f"<td>{fmt_price(s.get('target_price'))}</td>"
        f"{tp_txt}"
        f"<td>{fmt_price(s.get('fair_value'))}</td>"
        f"{fp_txt}</tr>"
    )


def render_valuation_section(title: str, note: str, rows: list[dict]) -> str:
    if not rows:
        return ""
    rows = sorted(rows, key=lambda s: (s["vs_fair_value_pct"] is None, -(s["vs_fair_value_pct"] or 0)))
    available = [s["vs_fair_value_pct"] for s in rows if s["vs_fair_value_pct"] is not None]
    max_abs = max((abs(v) for v in available), default=1.0) or 1.0

    chart_rows = "".join(render_val_row(s, max_abs) for s in rows)
    table_rows = "".join(render_val_table_row(s) for s in rows)

    return f"""
<div class="section-title">{title}</div>
<div class="val-caption">{note}</div>
<div class="val-chart">
  {chart_rows}
  <div class="val-legend"><span><span class="sw" style="background:var(--good)"></span>undervalued vs fair value</span><span><span class="sw" style="background:var(--bad)"></span>overvalued vs fair value</span></div>
</div>
<table class="val-table">
  <thead><tr><th>Stock</th><th>Tier</th><th>Price</th><th>Target</th><th>vs Target</th><th>Fair Value</th><th>vs Fair Value</th></tr></thead>
  <tbody>{table_rows}</tbody>
</table>
"""


def render_valuation_tab(stocks_state: dict, stocks_cfg: dict, rules: dict) -> str:
    fund_dates = {stocks_cfg[t].get("fundamentals_updated") for t in stocks_cfg if stocks_cfg[t].get("fundamentals_updated")}
    sources = {stocks_cfg[t].get("fundamentals_source") for t in stocks_cfg if stocks_cfg[t].get("fundamentals_source")}
    fund_date = max(fund_dates) if fund_dates else "not yet set"
    source_txt = ", ".join(sorted(s for s in sources if s)) or "not yet set"
    common_note = f"Sorted most-undervalued (green, left) to most-overvalued (red, right) vs each stock's fair value estimate. Source: <b>{source_txt}</b>, last updated <b>{fund_date}</b>. \"pending\" means no price fetched for that stock yet -- fills in on the next daily refresh."

    main_rows = collect_valuation_rows(stocks_cfg, stocks_state, {"T1", "T2", "T3", "T3.5"})
    t5t9_rows = collect_valuation_rows(stocks_cfg, stocks_state, {"T5", "T9"})

    sections = [
        render_valuation_section(
            "T1 – T3.5 (full ladder tiers)",
            common_note + " Use this to sanity-check whether a stock's tier assignment / MA ladder still matches how cheap or expensive it actually looks.",
            main_rows,
        ),
        render_valuation_section(
            "T5 &amp; T9 (single MA250-trigger tiers)",
            common_note + " Same chart/table as above, broken out separately since these tiers use just one trigger (MA250) instead of the full 3-rung ladder.",
            t5t9_rows,
        ),
    ]
    body = "".join(s for s in sections if s)
    return body or '<div class="empty-log">No fair value / target price data yet. Add it to config/stocks.yaml.</div>'


def warn_orphan_notes(rung_notes: dict, stocks_state: dict) -> list[str]:
    """Report note keys in config/rung_notes.yaml that match no current rung.

    Rung ids are derived from the MAs, so they move: a merge or split of a
    support cluster (MA100 drifting within cluster_merge_pct of MA200 and
    back) renames the rung, and a note keyed on the old id then renders
    nowhere -- silently, which is how a note can look lost. Ordering flips
    are handled by normalize_rung_id; anything left over is printed here so
    the key can be re-pointed by hand.
    """
    orphans = []
    for ticker, notes in (rung_notes or {}).items():
        s = stocks_state.get(ticker)
        if not s:
            orphans.append(f"{ticker}: ticker not in state.json")
            continue
        known = {
            normalize_rung_id(r["id"])
            for group in ("ladder", "full_ladder_today", "fired_this_period", "custom_rungs_today")
            for r in (s.get(group) or [])
        }
        for key in notes or {}:
            if normalize_rung_id(key) not in known:
                orphans.append(f"{ticker}|{key}")
    for orphan in orphans:
        print(f"[rung_notes] note key matches no rung today: {orphan}", file=sys.stderr)
    return orphans


def build() -> str:
    rules = load_rules()
    state = load_state()
    stocks_cfg = {s["ticker"]: s for s in load_stocks()}
    stocks_state = state.get("stocks", {})
    rung_notes = load_rung_notes()
    warn_orphan_notes(rung_notes, stocks_state)

    # Recompute target/fair-value figures from the current config against the
    # last known price, rather than trusting whatever run_check.py baked into
    # state.json -- this way editing config/stocks.yaml (e.g. after you paste
    # fresh moomoo numbers) shows up on rebuild even without a fresh network
    # fetch of prices.
    for ticker, s in stocks_state.items():
        cfg = stocks_cfg.get(ticker, {})
        s["ticker"] = ticker
        live_price = s.get("intraday_price")
        s["is_live"] = live_price is not None
        s["display_price"] = live_price if live_price is not None else s.get("price")
        if cfg.get("is_etf"):
            continue
        price = s["display_price"]
        s["target_price"] = cfg.get("target_price")
        s["fair_value"] = cfg.get("fair_value")
        s["vs_target_pct"] = pct_diff(price, cfg.get("target_price"))
        s["vs_fair_value_pct"] = pct_diff(price, cfg.get("fair_value"))

    open_count = sum(len(s.get("fired_this_period", []) or []) for s in stocks_state.values())
    stale_count = sum(1 for s in stocks_state.values() if s.get("data_stale"))
    price_dates = [s.get("price_date") for s in stocks_state.values() if s.get("price_date")]
    price_date = max(price_dates) if price_dates else "-"
    live_times = [s.get("intraday_price_at") for s in stocks_state.values() if s.get("intraday_price_at")]
    live_snapshot_html = (
        f' &middot; live snapshot <b>{format_et_label(max(live_times))}</b>' if live_times else ""
    )
    fund_dates = [
        stocks_cfg[t].get("fundamentals_updated") for t in stocks_cfg if stocks_cfg[t].get("fundamentals_updated")
    ]
    fund_date = max(fund_dates) if fund_dates else "not yet run"

    stale_banner = ""
    if stale_count:
        stale_banner = f'<div class="stale-banner">{stale_count} stock(s) have stale or missing price data — check the card for details.</div>'

    sections = []
    for tier in TIER_ORDER:
        tickers = [t for t, s in stocks_cfg.items() if s.get("tier") == tier]
        if not tickers:
            continue
        tier_cfg = rules["tiers"].get(tier, {})
        meta = f'base {fmt_money(tier_cfg.get("base_amount"), rules.get("currency","SGD"))} &middot; refresh {tier_cfg.get("refresh","-")} &middot; MA{"/".join(str(m) for m in tier_cfg.get("ma_ladder",[]))}'
        cards = []
        for ticker in sorted(tickers):
            s = stocks_state.get(ticker, {"tier": tier, "error": "no data yet"})
            cards.append(render_card(ticker, s, rules, rung_notes))
        sections.append(
            f'<div class="tier-section"><div class="tier-head"><h2>{tier}</h2><span class="meta">{meta}</span></div>'
            f'<div class="cards">{"".join(cards)}</div></div>'
        )

    valuation_html = render_valuation_tab(stocks_state, stocks_cfg, rules)

    html = TEMPLATE
    html = html.replace("__TITLE__", "DCA Alert Dashboard")
    html = html.replace("__PRICE_DATE__", str(price_date))
    html = html.replace("__LIVE_SNAPSHOT__", live_snapshot_html)
    html = html.replace("__GENERATED_AT__", state.get("generated_at") or "-")
    html = html.replace("__FUND_DATE__", str(fund_date))
    html = html.replace("__STALE_BANNER__", stale_banner)
    html = html.replace("__OPEN_COUNT__", str(open_count))
    html = html.replace("__STOCK_COUNT__", str(len(stocks_cfg)))
    html = html.replace("__CURRENCY__", rules.get("currency", "SGD"))
    html = html.replace("__STALE_COUNT__", str(stale_count))
    html = html.replace("__TIER_SECTIONS__", "".join(sections))
    html = html.replace("__VALUATION_TAB__", valuation_html)
    html = html.replace("__STATE_JSON__", json.dumps(state).replace("</", "<\\/"))
    return html


def main():
    html = build()
    out_dir = ROOT / "dashboard"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(html)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
