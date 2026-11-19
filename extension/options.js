const $ = id => document.getElementById(id);
const DEFAULTS = { url: 'http://127.0.0.1:8900', key: '', mode: 'auto', vendorSearch: '', vendorFills: true, autoSubmit: false, certify: false, classic: false, speed: 'fast', islandV: 'top', islandH: 'center', panelV: 'bottom', panelH: 'right', gap: 14 };
const POS = ['islandV', 'islandH', 'panelV', 'panelH', 'speed'];

chrome.storage.local.get(DEFAULTS, v => {
  $('url').value = v.url; $('key').value = v.key;
  ['vendorFills', 'autoSubmit', 'classic', 'certify'].forEach(k => { $(k).checked = !!v[k]; });
  $('vendorSearch').value = v.vendorSearch;
  $('mode_' + (v.mode === 'manual' ? 'manual' : 'auto')).checked = true;
  POS.forEach(k => { $(k).value = v[k]; }); $('gap').value = v.gap; $('gapv').textContent = v.gap;
});

const say = (text, ok) => { const m = $('msg'); m.textContent = text; m.className = ok ? 'ok' : 'bad'; };

$('show').onclick = () => { const k = $('key'); const hide = k.type === 'text'; k.type = hide ? 'password' : 'text'; $('show').textContent = hide ? 'Show' : 'Hide'; };

// the switches save as they are flipped
['mode_auto', 'mode_manual'].forEach(id => { $(id).onchange = () => chrome.storage.local.set({ mode: $(id).value }); });
$('vendorSearch').oninput = () => chrome.storage.local.set({ vendorSearch: $('vendorSearch').value.trim() });
['vendorFills', 'autoSubmit', 'classic', 'certify'].forEach(k => { $(k).onchange = () => chrome.storage.local.set({ [k]: $(k).checked }); });

$('save').onclick = async () => {
  const url = $('url').value.trim().replace(/\/+$/, ''), key = $('key').value.trim();
  if (!url || !key) { say('Enter the Solara address and the key.', false); return; }
  try {
    const origin = new URL(url).origin + '/*';
    // a hosted Solara needs the browser's permission to be called; local ones are declared already
    if (origin.startsWith('https://') && !(await chrome.permissions.request({ origins: [origin] }))) {
      say('Permission refused, so the co-pilot cannot reach Solara.', false); return;
    }
    await chrome.storage.local.set({ url, key });
    const r = await fetch(`${url}/api/copilot/lookup?consumer_no=000000000000`, { headers: { 'X-Solara-Key': key } });
    if (r.status === 401) say('Saved, but Solara does not recognise this key. Create a new one in Solara.', false);
    else say('Connected to Solara. Open a portal and pick a customer.', true);
  } catch (e) { say('Could not reach that address: ' + e.message, false); }
};

POS.forEach(k => { $(k).onchange = () => chrome.storage.local.set({ [k]: $(k).value }); });

// the other sites Solara was switched on for (the Solara button in the toolbar), and what it was taught there
async function showSites() {
  const box = $('sites'); if (!box) return;
  const scripts = await chrome.scripting.getRegisteredContentScripts().catch(() => []);
  const { learned } = await chrome.storage.local.get({ learned: {} });
  const hosts = [...new Set([...scripts.map(s => new URL(s.matches[0].replace('/*', '/')).host), ...Object.keys(learned).map(k => k.split('|')[0])])].sort();
  box.textContent = '';
  if (!hosts.length) { box.textContent = 'None yet. Open a site and click the Solara button in the browser toolbar.'; return; }
  hosts.forEach(host => {
    const row = document.createElement('div'), n = Object.keys(learned).filter(k => k.startsWith(host + '|')).length, b = document.createElement('button');
    row.className = 'site'; row.append(`${host}: ${n} taught box(es) `);
    b.textContent = 'Forget this site'; b.type = 'button';
    b.onclick = async () => {
      const s = scripts.find(x => x.matches[0].includes('//' + host + '/'));
      if (s) { await chrome.scripting.unregisterContentScripts({ ids: [s.id] }).catch(() => {}); await chrome.permissions.remove({ origins: s.matches }).catch(() => {}); }
      const kept = Object.fromEntries(Object.entries(learned).filter(([k]) => !k.startsWith(host + '|')));
      await chrome.storage.local.set({ learned: kept }); showSites();
    };
    row.append(b); box.append(row);
  });
}
showSites();
$('gap').oninput = () => { $('gapv').textContent = $('gap').value; chrome.storage.local.set({ gap: +$('gap').value }); };
