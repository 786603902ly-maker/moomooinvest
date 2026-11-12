// Push-notification subscriptions for the installed dashboard.
//
//   GET                      -> { publicKey, devices }
//   POST { subscription }    -> store this device
//   POST { test: true }      -> send a test notification to every device
//   DELETE { endpoint }      -> forget a device
//
// No auth, same tradeoff as api/ticks.js. The worst a stranger with the link
// can do is subscribe their own browser or trigger a test push, and test
// pushes are limited to one a minute.
const { kv } = require("@vercel/kv");
const { vapidKeys, saveSub, removeSub, sendAll, loadSubs } = require("../lib/push");

function body(req) {
  let b = req.body;
  if (typeof b === "string") {
    try { b = JSON.parse(b); } catch (e) { b = null; }
  }
  return b || {};
}

module.exports = async (req, res) => {
  try {
    if (req.method === "GET") {
      const keys = await vapidKeys();
      const devices = Object.keys(await loadSubs()).length;
      res.status(200).json({ publicKey: keys.publicKey, devices });
      return;
    }
    if (req.method === "POST") {
      const b = body(req);
      if (b.test) {
        const ok = await kv.set("moomooinvest:push:test-lock", 1, { nx: true, ex: 60 });
        if (!ok) { res.status(429).json({ error: "one test a minute" }); return; }
        const r = await sendAll([{ title: "moomooinvest", body: "Test notification: alerts are on for this device.", tag: "test", url: "/" }], req.headers.host);
        res.status(200).json(r);
        return;
      }
      const sub = b.subscription;
      if (!sub || typeof sub.endpoint !== "string" || !sub.keys) {
        res.status(400).json({ error: "missing subscription" });
        return;
      }
      const devices = await saveSub(sub);
      res.status(200).json({ ok: true, devices });
      return;
    }
    if (req.method === "DELETE") {
      const b = body(req);
      if (b.endpoint) await removeSub(b.endpoint);
      res.status(200).json({ ok: true });
      return;
    }
    res.setHeader("Allow", "GET, POST, DELETE");
    res.status(405).json({ error: "method not allowed" });
  } catch (e) {
    res.status(500).json({ error: "push backend unavailable", detail: String((e && e.message) || e) });
  }
};
