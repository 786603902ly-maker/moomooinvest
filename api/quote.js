// Live quotes, fetched server-side when the dashboard page loads.
//
// Why this exists: the page used to depend entirely on GitHub Actions
// committing an intraday snapshot into data/state.json. GitHub starts
// scheduled runs hours late (measured at 3.5-5h for this repo), so at best
// that gave one stale snapshot a day. A serverless function has outbound
// network access and runs on demand, so asking it at page load gives a
// price that is seconds old instead of hours.
//
// This is display-only. The MA/ladder math stays keyed off the daily close
// (plus the intraday low the hourly snapshot workflow records) in
// data/state.json, which run_check.py owns -- nothing here is persisted or
// feeds a trigger decision.
//
// No auth, same tradeoff as api/ticks.js: whoever has the dashboard link
// can call it. It only reads public market data and writes nothing.

const { fetchQuote } = require("../lib/quote");

const MAX_TICKERS = 60;

// Yahoo serves these symbols with a dash where moomoo shows a dot (BRK.B ->
// BRK-B); config/stocks.yaml already stores the dash form, so the ticker
// arrives ready to use and only needs validating, not rewriting.
const TICKER_RE = /^[A-Z][A-Z0-9.\-]{0,9}$/;

module.exports = async (req, res) => {
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    res.status(405).json({ error: "method not allowed" });
    return;
  }

  const raw = (req.query && req.query.tickers) || "";
  const asked = String(Array.isArray(raw) ? raw.join(",") : raw)
    .split(",")
    .map((t) => t.trim().toUpperCase())
    .filter(Boolean);

  const tickers = [...new Set(asked)].filter((t) => TICKER_RE.test(t)).slice(0, MAX_TICKERS);
  if (!tickers.length) {
    res.status(400).json({ error: "pass ?tickers=NVDA,TSM,..." });
    return;
  }

  const settled = await Promise.allSettled(tickers.map(fetchQuote));
  const quotes = {};
  const errors = {};
  settled.forEach((outcome, i) => {
    if (outcome.status === "fulfilled") quotes[tickers[i]] = outcome.value;
    else errors[tickers[i]] = String((outcome.reason && outcome.reason.message) || outcome.reason);
  });

  // Let Vercel's edge serve repeat loads for 30s rather than re-hitting
  // Yahoo once per visitor per refresh tick.
  res.setHeader("Cache-Control", "public, s-maxage=30, stale-while-revalidate=60");
  // 200 even with partial failures: the page renders whatever came back and
  // leaves the rest on the committed close, which is the useful behavior.
  res.status(Object.keys(quotes).length ? 200 : 502).json({
    fetched_at: new Date().toISOString(),
    quotes,
    errors,
  });
};
