// Live quote fetch shared by api/quote.js (the page's live prices) and
// api/notify.js (push notifications). Kept outside api/ so Vercel doesn't
// deploy it as an endpoint of its own.

const UPSTREAM = "https://query1.finance.yahoo.com/v8/finance/chart/";
const PER_REQUEST_TIMEOUT_MS = 8000;

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

    // The session's low so far, so the page can tell a rung was touched
    // intraday even when price has since recovered above it.
    let dayLow = typeof meta.regularMarketDayLow === "number" ? meta.regularMarketDayLow : null;
    if (dayLow === null) {
      const lows =
        ((result.indicators && result.indicators.quote && result.indicators.quote[0] &&
          result.indicators.quote[0].low) || []).filter((v) => typeof v === "number");
      if (lows.length) dayLow = Math.min(...lows);
    }
    if (dayLow !== null) dayLow = Math.min(dayLow, price);

    let dayHigh = typeof meta.regularMarketDayHigh === "number" ? meta.regularMarketDayHigh : null;
    if (dayHigh !== null) dayHigh = Math.max(dayHigh, price);

    return {
      price,
      dayLow,
      dayHigh,
      at: at ? new Date(at * 1000).toISOString() : null,
      state: meta.marketState || null,
      currency: meta.currency || null,
    };
  } finally {
    clearTimeout(timer);
  }
}

module.exports = { fetchQuote };
