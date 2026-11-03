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
  if (msg.type === 'lookup' || msg.type === 'pending') {
    const q = new URLSearchParams({ consumer_no: msg.consumer_no || '', app_no: msg.app_no || '', cid: msg.cid || '' });
    const r = await fetch(`${url}/api/copilot/${msg.type}?${q}`, { headers });
    const data = await r.json().catch(() => ({}));
    return r.ok ? { ok: true, data } : { ok: false, error: data.detail || r.statusText };
  }
  if (msg.type === 'file' || msg.type === 'doc') {
    const path = msg.type === 'file' ? `file/${msg.cid}/${msg.key}` : `doc/${msg.cid}/${msg.kind}`;
    const r = await fetch(`${url}/api/copilot/${path}`, { headers });
    if (!r.ok) return { ok: false, error: `could not fetch ${msg.key || msg.kind}` };
    const name = (r.headers.get('content-disposition') || '').match(/filename="([^"]+)"/);
    return { ok: true, b64: b64(await r.arrayBuffer()), type: r.headers.get('content-type'),
             name: name ? name[1] : `${msg.cid}_${msg.key || msg.kind}.pdf` };
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
