// Cross-device sync for the per-rung note fields, mirroring ticks.js.
// One JSON document under a single KV key: {"TICKER|rung-id": "note text"}.
// Same no-auth tradeoff as ticks.js -- see that file's comment.
const { kv } = require("@vercel/kv");

const NOTES_KEY = "moomooinvest:notes";

module.exports = async (req, res) => {
  try {
    if (req.method === "GET") {
      const notes = (await kv.get(NOTES_KEY)) || {};
      res.status(200).json(notes);
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
      const key = body && body.key;
      if (!key || typeof key !== "string") {
        res.status(400).json({ error: "missing or invalid 'key'" });
        return;
      }

      const notes = (await kv.get(NOTES_KEY)) || {};
      const text = typeof body.text === "string" ? body.text.trim() : "";
      if (text) {
        notes[key] = text;
      } else {
        delete notes[key];
      }
      await kv.set(NOTES_KEY, notes);
      res.status(200).json(notes);
      return;
    }

    res.setHeader("Allow", "GET, POST");
    res.status(405).json({ error: "method not allowed" });
  } catch (e) {
    res.status(500).json({ error: "notes backend unavailable", detail: String((e && e.message) || e) });
  }
};
