// Solara co-pilot panel, inside the operator's own browser.
// - MSEDCL upload page: attaches Solara's six documents to the right rows.
// - Any portal form (PM Surya Ghar, DCR): fills fields by their visible label, attaches the
//   customer's documents and the signed agreement, saves the application number to Solara.
// It never types an OTP, CAPTCHA or password, never ticks a consent box, never presses Submit,
// and never overwrites something already typed.
(() => {
  const ask = msg => chrome.runtime.sendMessage(msg);
  const esc = s => String(s ?? '').replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
  const norm = s => String(s ?? '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  const MSEDCL = [['wcr', /work completion/i], ['annexure1', /annexure/i], ['dcr_decl', /declaration of dcr/i],
                  ['net_agreement', /net agreement/i], ['datasheet', /brochure|datasheet/i],
                  ['site_photo', /photo of installed/i]];
  // first match wins; null means "never touch"
  const RULES = [
    [/otp|captcha|human check|password|security code|verification code/, null],
    [/consumer (account )?(no|number)|ca number|consumer id/, 'consumer_no'],
    [/mobile|phone|contact (no|number)/, 'mobile'],
    [/e ?mail/, 'email'],
    [/distribution|discom|electricity company|utility/, 'discom'],
    [/\bdistrict\b/, 'district'],
    [/\bstate\b/, 'state'],
    [/pin ?code|pincode|postal code/, 'pin'],
    [/address/, 'address'],
    [/(applicant|consumer|customer|full|beneficiary) name|^name\b/, 'name'],
    [/sanctioned|connected load/, 'sanctioned_load'],
    [/proposed capacity|rts capacity|plant capacity|capacity kw/, 'capacity'],
    [/category/, 'category'],
    [/total cost|cost of rts|installation cost|project cost/, 'rts_cost'],
    [/vendor/, 'vendor'],
  ];
  const FILES = [[/agreement/, 'agreement'], [/bill/, 'bill'], [/aadhaar|identity/, 'aadhaar'],
                 [/passbook|bank|cheque/, 'passbook'], [/roof|site photo/, 'roof']];

  // ---------- reading the page ----------
  const visible = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const scope = () => [...document.querySelectorAll('[role=dialog],[aria-modal=true],.modal.show,.mat-dialog-container,.cdk-overlay-pane')]
    .filter(visible).pop() || document.body;
  const textOf = root => root.innerText + ' ' + [...root.querySelectorAll('input')].map(i => i.value).join(' ');
  const one = (re, root) => { const all = new Set(textOf(root).match(re) || []); return all.size === 1 ? [...all][0] : ''; };

  function labelled(name, root, valid) {
    const want = name.toLowerCase();
    for (const cell of root.querySelectorAll('td,th,label,span,div')) {
      if (cell.children.length > 1 || cell.textContent.replace(/[:*\s]+$/, '').trim().toLowerCase() !== want) continue;
      const next = cell.nextElementSibling;
      const v = next && ((next.querySelector('input') || next).value || next.textContent || '').trim();
      if (v && valid.test(v)) return v;
    }
    return '';
  }

  function labelOf(el) {
    const t = [];
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) t.push(l.innerText); }
    const wrap = el.closest('label'); if (wrap) t.push(wrap.innerText);
    ['aria-label', 'placeholder', 'formcontrolname', 'name'].forEach(a => el.getAttribute(a) && t.push(el.getAttribute(a)));
    (el.getAttribute('aria-labelledby') || '').split(' ').forEach(id => { const x = id && document.getElementById(id); if (x) t.push(x.innerText); });
    let p = el.parentElement;
    for (let i = 0; i < 3 && p; i++, p = p.parentElement) {
      const lab = p.querySelector('label, mat-label, .form-label');
      if (lab && !lab.contains(el)) { t.push(lab.innerText); break; }
    }
    const td = el.closest('td'); if (td && td.previousElementSibling) t.push(td.previousElementSibling.innerText);
    return norm(t.join(' | ').replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[_-]/g, ' '));
  }

  const ruleFor = label => { const r = RULES.find(([re]) => re.test(label)); return r ? r[1] : undefined; };

  function setVal(el, v) {
    if (el.tagName === 'SELECT') {
      const want = norm(v), opts = [...el.options].filter(o => o.value !== '');
      const opt = opts.find(o => norm(o.text) === want || norm(o.value) === want) ||
                  opts.find(o => norm(o.text).length > 3 && (norm(o.text).includes(want) || want.includes(norm(o.text))));
      if (!opt) return false;
      el.value = opt.value;
    } else {
      const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v); // frameworks watch the native setter
    }
    ['input', 'change', 'blur'].forEach(t => el.dispatchEvent(new Event(t, { bubbles: true })));
    el.style.outline = '2px solid #2BB673';
    return true;
  }

  async function attach(input, msg) {
    const f = await ask(msg);
    if (!f || !f.ok) return false;
    const bin = Uint8Array.from(atob(f.b64), ch => ch.charCodeAt(0));
    const dt = new DataTransfer();
    dt.items.add(new File([bin], f.name, { type: f.type || 'application/pdf' }));
    input.files = dt.files;
    input.dispatchEvent(new Event('change', { bubbles: true }));
    input.style.outline = '2px solid #2BB673';
    return true;
  }

  // ---------- the panel ----------
  const panel = document.createElement('div');
  panel.id = 'solaraPanel';
  panel.style.cssText = 'position:fixed;right:14px;bottom:14px;z-index:2147483647;width:310px;max-height:72vh;' +
    'overflow:auto;background:#0F1B24;color:#E8EEF2;font:13px/1.4 system-ui,Arial,sans-serif;' +
    'border-radius:10px;box-shadow:0 8px 28px rgba(0,0,0,.35);padding:12px';
  const btn = (id, text, primary) => `<button id="${id}" style="display:block;width:100%;margin-top:8px;padding:8px;border:0;border-radius:7px;` +
    `cursor:pointer;font-weight:700;${primary ? 'background:#2BB673;color:#04150D' : 'background:#24343F;color:#E8EEF2'}">${text}</button>`;
  const say = html => { panel.innerHTML = `<div style="display:flex;justify-content:space-between"><b style="color:#5FD3A8">Solara co-pilot</b>` +
    `<span id="solaraRescan" style="cursor:pointer;color:#8FA3B2" title="Read this page again">&#8635;</span></div>` + html; };
  document.body.appendChild(panel);
  panel.addEventListener('click', e => { if (e.target.id === 'solaraRescan') scan(); });

  const remember = c => chrome.storage.local.set({ current: { cid: c.customer_id, at: Date.now() } });
  const recalled = async () => { const { current } = await chrome.storage.local.get('current');
    return current && Date.now() - current.at < 45 * 60 * 1000 ? current.cid : ''; };

  async function scan() {
    const root = scope();
    const consumer = labelled('Consumer Number', root, /^\d{9,14}$/) || one(/\b\d{12}\b/g, root);
    const app = labelled('Application Number', root, /^NP-/) || one(/\bNP-[A-Z0-9]+-\d{6,}\b/g, root);
    const fields = [...root.querySelectorAll('input,select,textarea')].filter(el => visible(el) &&
      !['hidden', 'checkbox', 'radio', 'submit', 'button', 'password'].includes(el.type));
    let cid = '';
    if (!consumer && !app) {
      if (!fields.length) { say('<span style="color:#8FA3B2">Nothing to do on this page.</span>'); return; }
      cid = await recalled();
      if (!cid) return pick();
    }
    say('Looking up this customer…');
    const r = await ask({ type: 'lookup', consumer_no: consumer, app_no: app, cid });
    if (!r || !r.ok) { say(`<span style="color:#F2A6A0">${esc((r && r.error) || 'No answer from Solara.')}</span>` + (fields.length ? btn('solaraPick', 'Choose the customer') : ''));
      const p = panel.querySelector('#solaraPick'); if (p) p.onclick = pick; return; }
    const c = r.data;
    remember(c);
    const head = `<div style="margin-top:4px"><b>${esc(c.name)}</b> &middot; ${esc(c.customer_id)} ` +
      `<a href="#" id="solaraChange" style="color:#8FA3B2;font-size:11px">not this customer?</a></div>`;
    const msRows = [...root.querySelectorAll('input[type=file]')].map(input => {
      const hit = MSEDCL.find(([, re]) => re.test((input.closest('tr') || input.parentElement).innerText));
      return hit && { input, key: hit[0] };
    }).filter(Boolean);
    if (msRows.length) return msedclAttach(c, msRows, head);
    const uploaded = [...root.querySelectorAll('tr')].filter(tr => /verification pending|approved/i.test(tr.innerText))
      .map(tr => (MSEDCL.find(([, re]) => re.test(tr.innerText)) || [])[0]).filter(Boolean);
    if (uploaded.length) {
      ask({ type: 'report', body: { customer_id: c.customer_id, portal: 'msedcl', uploaded } });
      say(head + `${uploaded.length} of 6 documents are on the portal. Solara has been updated.`); wireChange(); return;
    }
    // a page showing the application number this customer was just given: save it
    let saved = '';
    if (!c.application_no && app && consumer === (c.values.consumer_no || '') || (!c.application_no && app && !consumer && cid)) {
      const rep = await ask({ type: 'report', body: { customer_id: c.customer_id, event: 'app_no', app_no: app } });
      saved = rep && rep.ok ? `<div style="margin-top:6px;color:#5FD3A8">Application number <b>${esc(app)}</b> saved in Solara.</div>` : '';
      c.application_no = app;
    }
    formMode(c, root, head, saved);
  }

  function wireChange() { const a = panel.querySelector('#solaraChange'); if (a) a.onclick = e => { e.preventDefault(); pick(); }; }

  async function pick() {
    const r = await ask({ type: 'pending' });
    if (!r || !r.ok) { say(`<span style="color:#F2A6A0">${esc((r && r.error) || 'No answer from Solara.')}</span>`); return; }
    if (!r.data.length) { say('No customer in Solara is waiting to be registered.'); return; }
    say('<div style="margin-top:4px">Fill this page for:</div>' + r.data.map(x =>
      `<button data-pick="${esc(x.id)}" style="display:block;width:100%;text-align:left;margin-top:6px;padding:7px 9px;border:0;border-radius:7px;background:#24343F;color:#E8EEF2;cursor:pointer">` +
      `<b>${esc(x.name)}</b><br><span style="color:#8FA3B2;font-size:11px">${esc(x.id)} &middot; consumer ${esc(x.consumer_no)}</span></button>`).join(''));
    panel.querySelectorAll('[data-pick]').forEach(b => b.onclick = async () => {
      await chrome.storage.local.set({ current: { cid: b.dataset.pick, at: Date.now() } }); scan(); });
  }

  function msedclAttach(c, rows, head) {
    const have = new Set(c.files.map(f => f.key));
    const ready = rows.filter(x => have.has(x.key));
    say(head + `${ready.length} of ${rows.length} documents ready in Solara.` +
      (c.not_ready.length ? `<br><span style="color:#F2C879">Not ready: ${c.not_ready.map(n => esc(n.title)).join(', ')}</span>` : '') +
      btn('solaraAttach', `Attach ${ready.length} file(s)`, true));
    wireChange();
    panel.querySelector('#solaraAttach').onclick = async () => {
      let n = 0;
      for (const { input, key } of ready) n += await attach(input, { type: 'file', cid: c.customer_id, key }) ? 1 : 0;
      panel.dataset.attached = String(n);
      say(head + `<b>${n} file(s) attached.</b> Check each row, then press the portal's Upload button yourself.`);
      wireChange();
      ask({ type: 'report', body: { customer_id: c.customer_id, portal: 'msedcl', attached: n } });
    };
  }

  function formMode(c, root, head, saved) {
    const els = [...root.querySelectorAll('input,select,textarea')].filter(el => visible(el) && !el.readOnly && !el.disabled &&
      !['hidden', 'checkbox', 'radio', 'submit', 'button', 'password', 'file'].includes(el.type));
    const plan = els.map(el => ({ el, key: ruleFor(labelOf(el)) }));
    const fillable = plan.filter(p => p.key && c.values[p.key] != null);
    const files = [...root.querySelectorAll('input[type=file]')].filter(el => !el.disabled).map(el => {
      const lab = labelOf(el) + ' ' + norm((el.closest('tr,.upr,.fg,.form-group') || el.parentElement).innerText);
      const hit = FILES.find(([re]) => re.test(lab));
      return hit && { el, kind: hit[1] };
    }).filter(Boolean);
    // after Submit the portal locks the box, which is exactly when the owner marks it done
    const agreementBox = [...root.querySelectorAll('input[type=file]')].some(el => /agreement/.test(labelOf(el)));
    const agreementReady = c.files.some(f => f.key === 'agreement');
    say(head + saved + (fillable.length || files.length ? btn('solaraFill', `Fill ${fillable.length} field(s)` +
      (files.length ? ` and attach ${files.length} file(s)` : ''), true) : '<div style="margin-top:6px;color:#8FA3B2">No field here that Solara knows.</div>') +
      (agreementBox ? btn('solaraMarkUploaded', 'I pressed Submit: mark agreement uploaded') : '') +
      `<details style="margin-top:8px"><summary style="cursor:pointer;color:#8FA3B2">Copy a value</summary>` +
      c.fields.map((f, i) => `<div style="display:flex;gap:6px;align-items:center;padding:3px 0;border-top:1px solid #23323E">` +
        `<div style="flex:1;min-width:0"><div style="color:#8FA3B2;font-size:11px">${esc(f.label)}</div><div style="word-break:break-all">${esc(f.value)}</div></div>` +
        `<button data-copy="${i}" style="border:0;border-radius:5px;padding:4px 8px;cursor:pointer">Copy</button></div>`).join('') + '</details>');
    wireChange();
    panel.querySelectorAll('[data-copy]').forEach(b => b.onclick = () =>
      navigator.clipboard.writeText(c.fields[+b.dataset.copy].value).then(() => { b.textContent = 'Copied'; }));
    const mark = panel.querySelector('#solaraMarkUploaded');
    if (mark) mark.onclick = async () => {
      const rep = await ask({ type: 'report', body: { customer_id: c.customer_id, event: 'agreement_uploaded' } });
      mark.textContent = rep && rep.ok ? 'Saved in Solara: agreement uploaded' : (rep && rep.error) || 'Could not save';
    };
    const fill = panel.querySelector('#solaraFill');
    if (!fill) return;
    fill.onclick = async () => {
      let filled = 0, kept = 0, attached = 0;
      const left = [];
      for (const { el, key } of plan) {
        const label = labelOf(el).split(' | ')[0];
        if (key === null) continue; // OTP, CAPTCHA: the person types these
        if (!key || c.values[key] == null) { if (!el.value) left.push(label); continue; }
        if (el.value && el.tagName !== 'SELECT') { kept += 1; continue; } // never overwrite what is typed
        if (setVal(el, c.values[key])) filled += 1; else left.push(label);
      }
      for (const { el, kind } of files) {
        if (kind === 'agreement' && !agreementReady) { left.push('agreement (not signed yet)'); continue; }
        const ok = kind === 'agreement' ? await attach(el, { type: 'file', cid: c.customer_id, key: 'agreement' })
          : c.docs.includes(kind) && await attach(el, { type: 'doc', cid: c.customer_id, kind });
        if (ok) attached += 1; else left.push(kind);
      }
      panel.dataset.filled = String(filled);
      panel.dataset.attached = String(attached);
      fill.outerHTML = `<div id="solaraFilled" style="margin-top:8px"><b>Filled ${filled}${attached ? `, attached ${attached}` : ''}.</b>` +
        (kept ? ` Kept ${kept} you had typed.` : '') +
        (left.length ? `<br><span style="color:#F2C879">Left for you: ${esc([...new Set(left)].join(', '))}</span>` : '') +
        '<br>Check the page, then press the portal\'s button yourself.</div>';
      ask({ type: 'report', body: { customer_id: c.customer_id, portal: location.host, attached: filled + attached } });
    };
  }

  scan();
  // single-page portals change screens without reloading; read the page again when they do
  let last = location.href;
  setInterval(() => { if (location.href !== last) { last = location.href; setTimeout(scan, 800); } }, 700);
})();
