// Tiny key-value backend for the "I did this buy" checkboxes on the
// dashboard. The whole tick map is one JSON document under a single KV key
// -- this tracker is single-user and only ever holds a few dozen entries,
// so there's no need for per-row storage or any real query capability.
//
// No auth: whoever has the dashboard link can read and write this. That's
// an accepted tradeoff for a personal tracker with no login system yet --
// don't share the link if that's not okay.
const { kv } = require("@vercel/kv");

const TICKS_KEY = "moomooinvest:ticks";

module.exports = async (req, res) => {
  try {
    if (req.method === "GET") {
      const ticks = (await kv.get(TICKS_KEY)) || {};
      res.status(200).json(ticks);
      return;
    }

    if (req.method === "POST") {
      let body = req.body;
      if (typeof body === "string") {
        try {
          body = JSON.parse(body);
        } catch (e) {
          body = null;
        }
      }
      const id = body && body.id;
      if (!id || typeof id !== "string") {
        res.status(400).json({ error: "missing or invalid 'id'" });
        return;
      }

      const ticks = (await kv.get(TICKS_KEY)) || {};
      if (body.remove) {
        delete ticks[id];
      } else {
        if (!body.entry || typeof body.entry !== "object") {
          res.status(400).json({ error: "missing 'entry'" });
          return;
        }
        ticks[id] = body.entry;
      }
      await kv.set(TICKS_KEY, ticks);
      res.status(200).json(ticks);
      return;
    }

    res.setHeader("Allow", "GET, POST");
    res.status(405).json({ error: "method not allowed" });
  } catch (e) {
    res.status(500).json({ error: "tick backend unavailable", detail: String((e && e.message) || e) });
  }
};
