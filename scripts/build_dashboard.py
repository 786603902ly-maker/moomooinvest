#!/usr/bin/env python3
"""Render dashboard/index.html from data/state.json + config.

Pure templating, no network needed. Run after run_check.py (and, on Mondays,
after the Morningstar fair-value refresh) to produce the file that then gets
published as the Artifact dashboard.
"""
import datetime as dt
import json
from zoneinfo import ZoneInfo

from common import DATA_DIR, ROOT, load_rules, load_state, load_stocks

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
  __STALE_BANNER__
  <div class="tabs">
    <button class="tab-btn active" data-tab="alerts">Alerts &amp; ladder</button>
    <button class="tab-btn" data-tab="valuation">Valuation overview</button>
  </div>
  <div class="tabpanel active" id="tab-alerts">
    <div class="summary-row">
      <div class="stat hot"><div class="n">__OPEN_COUNT__</div><div class="l">open triggers</div></div>
      <div class="stat"><div class="n">__STOCK_COUNT__</div><div class="l">stocks tracked</div></div>
      <div class="stat"><div class="n">__STALE_COUNT__</div><div class="l">stale data</div></div>
    </div>
    __TIER_SECTIONS__
    <div class="section-title">Action log</div>
    <div class="actions-bar">
      <button class="export" id="export-btn">Export CSV</button>
      <span class="next-hint" id="export-hint"></span>
    </div>
    <div id="log-wrap"><div class="empty-log">Nothing ticked yet.</div></div>
  </div>
  <div class="tabpanel" id="tab-valuation">
    __VALUATION_TAB__
  </div>
  <footer>
    Ticks are stored locally in this browser only (not synced back to the repo). Rule assumptions that still need your confirmation are noted in <b>README.md</b> / <b>config/rules.yaml</b>.
  </footer>
</div>
<script>
const STATE = __STATE_JSON__;
const STORE_KEY = "moomooinvest-ticks-v1";

document.querySelectorAll(".tab-btn").forEach(btn=>{
  btn.addEventListener("click", ()=>{
    document.querySelectorAll(".tab-btn").forEach(b=>b.classList.remove("active"));
    document.querySelectorAll(".tabpanel").forEach(p=>p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
  });
});

function loadTicks(){
  try { return JSON.parse(localStorage.getItem(STORE_KEY) || "{}"); } catch(e){ return {}; }
}
function saveTicks(t){ localStorage.setItem(STORE_KEY, JSON.stringify(t)); }

function renderLog(){
  const ticks = loadTicks();
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

function onToggle(cb){
  const ticks = loadTicks();
  const id = cb.dataset.id;
  if(cb.checked){
    ticks[id] = {
      ticker: cb.dataset.ticker, tier: cb.dataset.tier, source: cb.dataset.source,
      level: cb.dataset.level, multiplier: cb.dataset.multiplier, amount: cb.dataset.amount,
      firstHit: cb.dataset.firsthit, tickedAt: new Date().toISOString()
    };
  } else {
    delete ticks[id];
  }
  saveTicks(ticks);
  const rungEl = cb.closest(".rung");
  if(rungEl){ rungEl.classList.toggle("done", cb.checked); }
  renderLog();
}

document.addEventListener("change", (e)=>{
  if(e.target.matches('input[type=checkbox][data-id]')) onToggle(e.target);
});

function applyStoredTicks(){
  const ticks = loadTicks();
  document.querySelectorAll('input[type=checkbox][data-id]').forEach(cb=>{
    if(ticks[cb.dataset.id]){
      cb.checked = true;
      const rungEl = cb.closest(".rung");
      if(rungEl){ rungEl.classList.add("done"); }
    }
  });
}

async function exportCsv(){
  const ticks = Object.values(loadTicks());
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

applyStoredTicks();
renderLog();
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


def render_rung(ticker: str, tier: str, rung: dict, is_open: bool, extra_cls: str = "", price: float | None = None) -> str:
    status_cls = ("open " + extra_cls).strip() if is_open else extra_cls
    checkbox = ""
    if is_open:
        rid = f"{ticker}|{rung.get('id')}|{rung.get('first_hit_date','')}"
        checkbox = (
            f'<input type="checkbox" data-id="{rid}" data-ticker="{ticker}" data-tier="{tier}" '
            f'data-source="{rung.get("source")}" data-level="{rung.get("level")}" '
            f'data-multiplier="{rung.get("multiplier","-")}" data-amount="{rung.get("amount","")}" '
            f'data-firsthit="{rung.get("first_hit_date","")}">'
        )
    amt = f'{rung.get("amount"):,.0f}' if rung.get("amount") is not None else ""
    mult_txt = f'x{rung.get("multiplier")}' if rung.get("multiplier") is not None else "your target"
    dist_html = ""
    if not is_open and price and rung.get("level"):
        dist = (rung["level"] - price) / price * 100
        dist_html = f'<span class="dist">{dist:+.1f}% away</span>'
    return (
        f'<div class="rung {status_cls}">{checkbox}'
        f'<span class="lvl">{fmt_price(rung.get("level"))}</span>'
        f'<span class="src">{rung.get("source")}</span>'
        f'<span class="amt">{mult_txt}{" &middot; " + amt if amt else ""}</span>'
        f"{dist_html}"
        f"</div>"
    )


def render_card(ticker: str, s: dict, rules: dict) -> str:
    tier = s.get("tier", "?")
    currency = rules.get("currency", "SGD")
    price = s.get("display_price", s.get("price"))
    fired = s.get("fired_this_period", []) or []
    fired_by_id = {f["id"]: f for f in fired}
    base_amount = (rules.get("tiers", {}).get(tier) or {}).get("base_amount")
    has_open = len(fired) > 0

    pills = []
    if not s.get("is_etf") and s.get("vs_target_pct") is not None:
        v = s["vs_target_pct"]
        cls = "good" if v < 0 else "bad"
        pills.append(pill(f'{v:+.1f}% vs target', cls))
    if not s.get("is_etf") and s.get("vs_fair_value_pct") is not None:
        v = s["vs_fair_value_pct"]
        cls = "good" if v < 0 else "bad"
        pills.append(pill(f'{v:+.1f}% vs fair value', cls))
    if s.get("clustered"):
        pills.append(pill("MA cluster → 5% cascade", "neutral"))
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
    plan_rows = []
    for rung in ladder:
        fired_entry = fired_by_id.get(rung["id"])
        if fired_entry:
            plan_rows.append(render_rung(ticker, tier, fired_entry, True))
        else:
            preview = dict(rung)
            if base_amount is not None:
                preview["amount"] = round(base_amount * rung["multiplier"], 2)
            plan_rows.append(render_rung(ticker, tier, preview, False, extra_cls="pending", price=price))
    extra_fired = [f for f in fired if f["id"] not in ladder_ids]
    plan_rows += [render_rung(ticker, tier, f, True) for f in extra_fired]
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
    # the same level twice).
    next_rung = s.get("next_rung")
    next_html = ""
    if next_rung and price and next_rung["id"] not in ladder_ids:
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

    return f"""<div class="card {'has-open' if has_open else ''}">
  <div class="card-head">
    <div><div class="name">{ticker} <span class="sub">{s.get('name','')}</span></div><div class="sub">{tier} &middot; {period_txt}</div></div>
    <div style="text-align:right;"><div class="price">{fmt_price(price)}</div>{price_sub}</div>
  </div>
  <div class="pills">{''.join(pills)}</div>
  <div class="ma-strip">{ma_strip}</div>
  <div class="rungs">{rungs_html if rungs_html else '<div class="next-hint">No ladder available (missing MA data).</div>'}</div>
  {next_html}
  {custom_html}
  {err_html}
</div>"""


def pct_diff(price: float | None, ref: float | None) -> float | None:
    if price is None or ref is None or ref == 0:
        return None
    return round((price - ref) / ref * 100, 2)


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
    cls = "good" if pct < 0 else "bad"
    half_pct = min(abs(pct) / max_abs * 50, 50) if max_abs else 0
    if pct < 0:
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
    tp_txt = f'<td class="{"good" if tp < 0 else "bad"}">{tp:+.1f}%</td>' if tp is not None else '<td style="color:var(--text-muted)">pending</td>'
    fp_txt = f'<td class="{"good" if fp < 0 else "bad"}">{fp:+.1f}%</td>' if fp is not None else '<td style="color:var(--text-muted)">pending</td>'
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
    rows = sorted(rows, key=lambda s: (s["vs_fair_value_pct"] is None, s["vs_fair_value_pct"]))
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


def build() -> str:
    rules = load_rules()
    state = load_state()
    stocks_cfg = {s["ticker"]: s for s in load_stocks()}
    stocks_state = state.get("stocks", {})

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
            cards.append(render_card(ticker, s, rules))
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
