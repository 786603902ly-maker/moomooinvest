// Decides which push notifications to send right now, and sends them.
//
// Safe to call as often as anyone likes -- each event is sent once (the
// keys already sent live in KV), so a call only ever sends what is new.
// Called by an external scheduler during US market hours (see README "Push
// notifications"), and best-effort by the GitHub workflows after each run.
//
// It applies the same rules as the order panel (renderOrderSheet in
// scripts/build_dashboard.py), using the live quote's price and day low:
//   - a rung counts as used only once a buy/skip tick exists for it (or a
//     placed order at or above it was reached); shallower rungs than the
//     deepest used one are skipped;
//   - the deepest unused rung the day's low reached is announced, once per
//     rung per refresh period;
//   - a sell target the day's high reached and not marked done, once.
// Rungs come from dashboard/plans.json, written by build_dashboard.py.
const { kv } = require("@vercel/kv");
const { fetchQuote } = require("../lib/quote");
const { sendAll } = require("../lib/push");

const TICKS_KEY = "moomooinvest:ticks";
const SENT_KEY = "moomooinvest:push:sent";
const KEEP_SENT_DAYS = 45;

function etDate(iso) {
  const d = iso ? new Date(iso) : new Date();
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(d);
}

const usd = (v) => "$" + Number(v).toFixed(2);

function events(ticker, plan, q, ticks, currency) {
  const out = [];
  const today = etDate(q.at);
  const price = q.price;
  const low = Math.min(typeof q.dayLow === "number" ? q.dayLow : price, price);
  const high = Math.max(typeof q.dayHigh === "number" ? q.dayHigh : price, price);
  const tickId = (r) => `${ticker}|${r.id}|${r.hit || today}`;
  const money = (v) => `${currency} ${Math.round(v).toLocaleString("en-US")}`;

  // Buys
  const used = plan.rungs.filter((r) => ticks[tickId(r)]).map((r) => r.level);
  const mark = ticks[`order|${ticker}`];
  const filled = mark && low <= mark.level;
  if (filled) used.push(mark.level);
  const floor = used.length ? Math.min(...used) : Infinity;
  const avail = plan.rungs.filter((r) => r.level < floor * (1 - 1e-9));
  const hits = avail.filter((r) => low <= r.level);

  if (filled) {
    out.push({
      key: `fill|${ticker}|${mark.rungId}|${mark.placedAt}`,
      title: `${ticker}: your ${usd(mark.level)} order should have filled`,
      body: `Day low ${usd(low)}, now ${usd(price)}. Open the dashboard to place the next order.`,
    });
  }
  if (hits.length) {
    const r = hits[hits.length - 1];
    const under = price <= r.level;
    out.push({
      key: `buy|${ticker}|${plan.period}|${r.id}`,
      title: under
        ? `${ticker} ${usd(price)} is under your ${usd(r.level)} rung`
        : `${ticker} dipped to ${usd(low)}, through your ${usd(r.level)} rung`,
      body: under
        ? `${plan.tier}: buy ${money(r.amount)} (x${r.mult}), or let a placed order fill.`
        : `${plan.tier}: now ${usd(price)}. Buy ${money(r.amount)} anyway, or skip and wait lower.`,
    });
  }

  // Sells
  for (const s of plan.sells || []) {
    if (high < s.level || ticks[tickId(s)]) continue;
    out.push({
      key: `sell|${ticker}|${s.id}`,
      title: `${ticker} reached ${usd(s.level)}: ${s.source}`,
      body: `Now ${usd(price)}${high > price ? ` (day high ${usd(high)})` : ""}.`,
    });
  }
  return out.map((e) => ({ ...e, tag: e.key, url: "/" }));
}

module.exports = async (req, res) => {
  try {
    const host = req.headers.host;
    const planRes = await fetch(`https://${host}/dashboard/plans.json`, { cache: "no-store" });
    if (!planRes.ok) throw new Error(`plans.json ${planRes.status}`);
    const plans = await planRes.json();
    const stocks = plans.stocks || {};
    const tickers = Object.keys(stocks);

    const [ticks, sent] = await Promise.all([kv.get(TICKS_KEY), kv.get(SENT_KEY)]);
    const sentMap = sent || {};
    const settled = await Promise.allSettled(tickers.map((t) => fetchQuote(t)));

    const fresh = [];
    settled.forEach((o, i) => {
      if (o.status !== "fulfilled") return;
      for (const e of events(tickers[i], stocks[tickers[i]], o.value, ticks || {}, plans.currency || "SGD")) {
        if (!sentMap[e.key]) fresh.push(e);
      }
    });

    let result = { devices: null, delivered: 0 };
    if (fresh.length) {
      result = await sendAll(fresh.map(({ key, ...msg }) => msg), host);
    }
    // Only count an event as sent once some device actually got it --
    // otherwise everything that happened before you subscribed would be
    // silently used up.
    if (fresh.length && result.delivered > 0) {
      const now = Date.now();
      for (const e of fresh) sentMap[e.key] = now;
      for (const [k, t] of Object.entries(sentMap)) {
        if (now - t > KEEP_SENT_DAYS * 86400e3) delete sentMap[k];
      }
      await kv.set(SENT_KEY, sentMap);
    }
    res.setHeader("Cache-Control", "no-store");
    res.status(200).json({
      checked: tickers.length,
      quoted: settled.filter((o) => o.status === "fulfilled").length,
      sent: fresh.map((e) => e.title),
      ...result,
    });
  } catch (e) {
    res.status(500).json({ error: "notify failed", detail: String((e && e.message) || e) });
  }
};

module.exports.events = events; // for tests
