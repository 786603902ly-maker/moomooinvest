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
// in data/state.json, which run_check.py owns -- nothing here is persisted
// or feeds a trigger decision.
//
// No auth, same tradeoff as api/ticks.js: whoever has the dashboard link
// can call it. It only reads public market data and writes nothing.

const UPSTREAM = "https://query1.finance.yahoo.com/v8/finance/chart/";
const MAX_TICKERS = 60;
const PER_REQUEST_TIMEOUT_MS = 8000;

// Yahoo serves these symbols with a dash where moomoo shows a dot (BRK.B ->
// BRK-B); config/stocks.yaml already stores the dash form, so the ticker
// arrives ready to use and only needs validating, not rewriting.
const TICKER_RE = /^[A-Z][A-Z0-9.\-]{0,9}$/;

async function fetchQuote(ticker) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PER_REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(`${UPSTREAM}${encodeURIComponent(ticker)}?range=1d&interval=1m`, {
      signal: controller.signal,
      headers: {
        // Yahoo rejects requests without a browser-ish UA.
        "User-Agent": "Mozilla/5.0 (compatible; moomooinvest-dashboard/1.0)",
        Accept: "application/json",
      },
    });
    if (!res.ok) throw new Error(`upstream ${res.status}`);
    const payload = await res.json();
    const result = payload && payload.chart && payload.chart.result && payload.chart.result[0];
    if (!result) throw new Error("no chart result");

    const meta = result.meta || {};
    // regularMarketPrice is the current print; fall back to the last non-null
    // minute bar, which is what scripts/fetch_prices.py reads.
    let price = typeof meta.regularMarketPrice === "number" ? meta.regularMarketPrice : null;
    let at = typeof meta.regularMarketTime === "number" ? meta.regularMarketTime : null;
    if (price === null) {
      const stamps = result.timestamp || [];
      const closes =
        (result.indicators && result.indicators.quote && result.indicators.quote[0] &&
          result.indicators.quote[0].close) || [];
      for (let i = closes.length - 1; i >= 0; i--) {
        if (typeof closes[i] === "number") {
          price = closes[i];
          at = stamps[i];
          break;
        }
      }
    }
    if (typeof price !== "number" || !isFinite(price)) throw new Error("no usable price");

    return {
      price,
      at: at ? new Date(at * 1000).toISOString() : null,
      state: meta.marketState || null,
      currency: meta.currency || null,
    };
  } finally {
    clearTimeout(timer);
  }
}

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
