// Talks to Solara on the page's behalf: content scripts cannot call another origin, the
// extension can. Files come back base64 because messages carry JSON only.
const cfg = () => chrome.storage.local.get({ url: 'http://127.0.0.1:8900', key: '' });

function b64(buf) {
  const bytes = new Uint8Array(buf); let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

async function handle(msg) {
  const { url, key } = await cfg();
  if (!key) return { ok: false, error: 'Open the Solara co-pilot options and paste your key.' };
  const headers = { 'X-Solara-Key': key };
  if (msg.type === 'lookup') {
    const q = new URLSearchParams({ consumer_no: msg.consumer_no || '', app_no: msg.app_no || '' });
    const r = await fetch(`${url}/api/copilot/lookup?${q}`, { headers });
    const data = await r.json().catch(() => ({}));
    return r.ok ? { ok: true, data } : { ok: false, error: data.detail || r.statusText };
  }
  if (msg.type === 'file') {
    const r = await fetch(`${url}/api/copilot/file/${msg.cid}/${msg.key}`, { headers });
    if (!r.ok) return { ok: false, error: `could not fetch ${msg.key}` };
    return { ok: true, b64: b64(await r.arrayBuffer()), name: `${msg.cid}_${msg.key}.pdf` };
  }
  if (msg.type === 'report') {
    await fetch(`${url}/api/copilot/report`, {
      method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify(msg.body)
    });
    return { ok: true };
  }
  return { ok: false, error: 'unknown request' };
}

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  handle(msg).then(reply, e => reply({ ok: false, error: 'Solara is not reachable: ' + (e.message || e) }));
  return true; // keep the channel open for the async reply
});
