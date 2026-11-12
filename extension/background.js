// Talks to Solara on the page's behalf: content scripts cannot call another origin, the
// extension can. Files come back base64 because messages carry JSON only.
const cfg = () => chrome.storage.local.get({ url: 'http://127.0.0.1:8900', key: '' });

function b64(buf) {
  const bytes = new Uint8Array(buf); let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

// every call to Solara gives up after 25 s, so a hung server shows an error instead of a frozen panel
async function call(url, opts) {
  const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), 25000);
  try { return await fetch(url, { ...opts, signal: ctl.signal }); } finally { clearTimeout(t); }
}

async function handle(msg) {
  const { url, key } = await cfg();
  if (!key) return { ok: false, error: 'Open the Solara co-pilot options and paste your key.' };
  const headers = { 'X-Solara-Key': key };
  const json = async r => { const data = await r.json().catch(() => ({})); return r.ok ? { ok: true, data } : { ok: false, error: data.detail || r.statusText }; };
  if (msg.type === 'lookup' || msg.type === 'pending') {
    const q = new URLSearchParams({ consumer_no: msg.consumer_no || '', app_no: msg.app_no || '', cid: msg.cid || '', step: msg.step || '' });
    return json(await call(`${url}/api/copilot/${msg.type}?${q}`, { headers }));
  }
  if (msg.type === 'file' || msg.type === 'doc' || msg.type === 'xlsx') {
    const path = msg.type === 'file' ? `file/${msg.cid}/${msg.key}` : msg.type === 'doc' ? `doc/${msg.cid}/${msg.kind}` : `xlsx/${msg.cid}`;
    // what the portal's box takes: PDF only, and its own size limit, when the page says so
    const box = new URLSearchParams({ to: msg.to || '', max_kb: String(msg.max_kb || 0) });
    const r = await call(`${url}/api/copilot/${path}?${box}`, { headers });
    if (!r.ok) { const e = await r.json().catch(() => ({})); return { ok: false, error: `could not fetch ${msg.key || msg.kind || 'the Excel'}: ${e.detail || r.statusText}` }; }
    const name = (r.headers.get('content-disposition') || '').match(/filename="([^"]+)"/);
    return { ok: true, b64: b64(await r.arrayBuffer()), type: r.headers.get('content-type'),
             name: name ? name[1] : `${msg.cid}_${msg.key || msg.kind}.pdf` };
  }
  if (msg.type === 'report' || msg.type === 'status') {
    // a refusal from Solara is a failure, never a silent success
    return json(await call(`${url}/api/copilot/${msg.type}`, {
      method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify(msg.body)
    }));
  }
  return { ok: false, error: 'unknown request' };
}

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  handle(msg).then(reply, async e => {
    const { url } = await cfg();
    reply({ ok: false, offline: true, error: e.name === 'AbortError' ? 'Solara took too long to answer.' :
      `Solara is not reachable at ${url}. Is it running? Check the address in the co-pilot options.` });
  });
  return true; // keep the channel open for the async reply
});
