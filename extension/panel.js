// Solara co-pilot panel. Reads which customer the portal page is about, then either attaches
// Solara's documents to the page's upload boxes (MSEDCL) or shows the customer's details with
// copy buttons (any other portal page). It never presses Submit or Upload.
(async () => {
  const ask = msg => chrome.runtime.sendMessage(msg);
  const DOCS = [['wcr', /work completion/i], ['annexure1', /annexure/i], ['dcr_decl', /declaration of dcr/i],
                ['net_agreement', /net agreement/i], ['datasheet', /brochure|datasheet/i],
                ['site_photo', /photo of installed/i]];

  // the value shown beside a label cell such as "Consumer Number :"
  function labelled(name) {
    const want = name.toLowerCase();
    for (const cell of document.querySelectorAll('td,th,label,span,div')) {
      if (cell.children.length > 1) continue;
      if (cell.textContent.replace(/[:*\s]+$/, '').trim().toLowerCase() !== want) continue;
      const next = cell.nextElementSibling;
      const v = next && ((next.querySelector('input') || {}).value || next.textContent);
      if (v && v.trim()) return v.trim();
    }
    return '';
  }

  const text = document.body.innerText;
  // a list page shows many customers; only act on a page about exactly one
  const one = re => { const all = new Set(text.match(re) || []); return all.size === 1 ? [...all][0] : ''; };
  const consumer = labelled('Consumer Number') || one(/\b\d{12}\b/g);
  const app = one(/\bNP-[A-Z0-9]+-\d+\b/g);
  if (!consumer && !app) return;

  const panel = document.createElement('div');
  panel.id = 'solaraPanel';
  panel.style.cssText = 'position:fixed;right:14px;bottom:14px;z-index:2147483647;width:300px;max-height:70vh;' +
    'overflow:auto;background:#0F1B24;color:#E8EEF2;font:13px/1.4 system-ui,Arial,sans-serif;' +
    'border-radius:10px;box-shadow:0 8px 28px rgba(0,0,0,.35);padding:12px';
  const say = html => { panel.innerHTML = '<b style="color:#5FD3A8">Solara co-pilot</b><br>' + html; };
  document.body.appendChild(panel);
  say('Looking up this customer…');

  const r = await ask({ type: 'lookup', consumer_no: consumer, app_no: app });
  if (!r || !r.ok) { say(`<span style="color:#F2A6A0">${(r && r.error) || 'No answer from Solara.'}</span>`); return; }
  const c = r.data;
  const esc = s => String(s).replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));

  const rows = [...document.querySelectorAll('input[type=file]')].map(input => {
    const rowText = (input.closest('tr') || input.parentElement).innerText;
    const hit = DOCS.find(([, re]) => re.test(rowText));
    return hit && { input, key: hit[0] };
  }).filter(Boolean);

  if (rows.length) {
    const have = new Set(c.files.map(f => f.key));
    const ready = rows.filter(x => have.has(x.key));
    say(`${esc(c.name)} &middot; ${esc(c.customer_id)}<br>${ready.length} of ${rows.length} documents ready in Solara.` +
      (c.not_ready.length ? `<br><span style="color:#F2C879">Not ready: ${c.not_ready.map(n => esc(n.title)).join(', ')}</span>` : '') +
      `<button id="solaraAttach" style="display:block;width:100%;margin-top:9px;padding:9px;border:0;border-radius:7px;` +
      `background:#2BB673;color:#04150D;font-weight:700;cursor:pointer">Attach ${ready.length} file(s)</button>`);
    panel.querySelector('#solaraAttach').onclick = async () => {
      let n = 0;
      for (const { input, key } of ready) {
        const f = await ask({ type: 'file', cid: c.customer_id, key });
        if (!f.ok) continue;
        const bin = Uint8Array.from(atob(f.b64), ch => ch.charCodeAt(0));
        const dt = new DataTransfer();
        dt.items.add(new File([bin], f.name, { type: 'application/pdf' }));
        input.files = dt.files;
        input.dispatchEvent(new Event('change', { bubbles: true }));
        n += 1;
      }
      panel.dataset.attached = String(n);
      say(`${esc(c.name)}<br><b>${n} file(s) attached.</b> Check each row, then press the portal's Upload button yourself.`);
      ask({ type: 'report', body: { customer_id: c.customer_id, portal: 'msedcl', attached: n } });
    };
    return;
  }

  // after an upload the rows show the portal's own status; tell Solara what is now on file
  const uploaded = [...document.querySelectorAll('tr')]
    .filter(tr => /verification pending|approved/i.test(tr.innerText))
    .map(tr => (DOCS.find(([, re]) => re.test(tr.innerText)) || [])[0]).filter(Boolean);
  if (uploaded.length) {
    ask({ type: 'report', body: { customer_id: c.customer_id, portal: 'msedcl', uploaded } });
    say(`${esc(c.name)}<br>${uploaded.length} of 6 documents are on the portal. Solara has been updated.`);
    return;
  }

  // any other page: the customer's details, one tap to copy each
  say(`${esc(c.name)} &middot; ${esc(c.customer_id)}<div style="margin-top:6px">` + c.fields.map((f, i) =>
    `<div style="display:flex;gap:6px;align-items:center;padding:3px 0;border-top:1px solid #23323E">` +
    `<div style="flex:1;min-width:0"><div style="color:#8FA3B2;font-size:11px">${esc(f.label)}</div>` +
    `<div style="word-break:break-all">${esc(f.value)}</div></div>` +
    `<button data-copy="${i}" style="border:0;border-radius:5px;padding:4px 8px;cursor:pointer">Copy</button></div>`).join('') + '</div>');
  panel.addEventListener('click', e => {
    const b = e.target.closest('[data-copy]'); if (!b) return;
    navigator.clipboard.writeText(c.fields[+b.dataset.copy].value).then(() => { b.textContent = 'Copied'; });
  });
})();
