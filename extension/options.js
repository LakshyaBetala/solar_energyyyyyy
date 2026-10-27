const $ = id => document.getElementById(id);
chrome.storage.local.get({ url: 'http://127.0.0.1:8900', key: '' }, v => { $('url').value = v.url; $('key').value = v.key; });

$('save').onclick = async () => {
  const url = $('url').value.trim().replace(/\/+$/, ''), key = $('key').value.trim();
  try {
    const origin = new URL(url).origin + '/*';
    // a hosted Solara needs the browser's permission to be called; local ones are declared already
    if (origin.startsWith('https://') && !(await chrome.permissions.request({ origins: [origin] }))) {
      $('msg').textContent = 'Permission refused, so the co-pilot cannot reach Solara.'; return;
    }
    await chrome.storage.local.set({ url, key });
    const r = await fetch(`${url}/api/copilot/lookup?consumer_no=000000000000`, { headers: { 'X-Solara-Key': key } });
    $('msg').textContent = r.status === 401 ? 'Saved, but Solara does not recognise this key.'
      : 'Saved. Connected to Solara.';
  } catch (e) { $('msg').textContent = 'Could not reach that address: ' + e.message; }
};
