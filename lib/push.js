// Web Push plumbing shared by api/push.js (subscribe, test) and
// api/notify.js (decide and send).
//
// No secrets to configure: the VAPID key pair is generated on first use and
// kept in the same KV store as the ticks. Only these functions can read it.
const { kv } = require("@vercel/kv");
const webpush = require("web-push");

const VAPID_KEY = "moomooinvest:push:vapid";
const SUBS_KEY = "moomooinvest:push:subs";

async function vapidKeys() {
  let keys = await kv.get(VAPID_KEY);
  if (!keys || !keys.publicKey || !keys.privateKey) {
    keys = webpush.generateVAPIDKeys();
    // nx: if two first calls race, both end up using whichever was stored.
    await kv.set(VAPID_KEY, keys, { nx: true });
    keys = await kv.get(VAPID_KEY);
  }
  return keys;
}

async function loadSubs() {
  return (await kv.get(SUBS_KEY)) || {};
}

async function saveSub(sub) {
  const subs = await loadSubs();
  subs[sub.endpoint] = { ...sub, savedAt: new Date().toISOString() };
  await kv.set(SUBS_KEY, subs);
  return Object.keys(subs).length;
}

async function removeSub(endpoint) {
  const subs = await loadSubs();
  delete subs[endpoint];
  await kv.set(SUBS_KEY, subs);
}

// Sends each message to every subscribed device. A device whose
// subscription is gone (404/410, e.g. the app was uninstalled) is dropped.
async function sendAll(messages, host) {
  const keys = await vapidKeys();
  const subs = await loadSubs();
  const opts = {
    // VAPID wants a contact; the site's own URL avoids sending anyone's
    // email address to the browser vendors' push services.
    vapidDetails: { subject: `https://${host}`, publicKey: keys.publicKey, privateKey: keys.privateKey },
    TTL: 6 * 3600,
  };
  let delivered = 0;
  const gone = [];
  for (const sub of Object.values(subs)) {
    for (const msg of messages) {
      try {
        await webpush.sendNotification(sub, JSON.stringify(msg), opts);
        delivered++;
      } catch (e) {
        if (e && (e.statusCode === 404 || e.statusCode === 410)) {
          gone.push(sub.endpoint);
          break;
        }
      }
    }
  }
  for (const endpoint of gone) await removeSub(endpoint);
  return { devices: Object.keys(subs).length - gone.length, delivered };
}

module.exports = { vapidKeys, saveSub, removeSub, sendAll, loadSubs };
