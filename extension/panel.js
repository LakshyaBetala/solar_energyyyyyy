// Solara co-pilot panel, inside the operator's own browser.
// - MSEDCL upload page: attaches Solara's six documents to the right rows.
// - Any portal form (PM Surya Ghar, DCR): fills fields by their visible label, attaches the
//   customer's documents and the signed agreement, saves the application number to Solara.
// It never types an OTP, CAPTCHA or password, never ticks a consent box, never presses Submit,
// and never overwrites something already typed.
(() => {
  // a closed or reloaded extension, or a stopped server, must show a message and never throw
  const ask = async msg => {
    try { return (await chrome.runtime.sendMessage(msg)) || { ok: false, error: 'No answer from Solara.' }; }
    catch (e) { return { ok: false, error: 'The co-pilot lost its connection. Reload this page.' }; }
  };
  const esc = s => String(s ?? '').replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
  const norm = s => String(s ?? '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  const MSEDCL = [['wcr', /work completion/i], ['annexure1', /annexure/i], ['dcr_decl', /declaration of dcr/i],
                  ['net_agreement', /net agreement/i], ['datasheet', /brochure|datasheet/i],
                  ['site_photo', /photo of installed/i]];
  // first match wins; null means "never touch"
  // labels are taken from the client's real portal screens (tests/real_labels.py checks them)
  const RULES = [
    [/otp|captcha|human check|password|security code|verification code/, null],
    [/user ?id|username|register email|login/, null],         // the vendor's own login, never the customer's
    [/employee|contact person|contact number/, null],         // the vendor's site staff, not the customer
    [/application (no|number)/, 'application_no'],
    [/consumer (account )?(no|number)|ca number|consumer id/, 'consumer_no'],
    [/mobile|phone/, 'mobile'],
    [/e ?mail/, 'email'],
    [/latitude/, 'lat'],
    [/longitude/, 'lng'],
    [/distribution|discom|electricity company|utility/, 'discom'],
    [/\bdistrict\b/, 'district'],
    [/\bstate\b/, 'state'],
    [/pin ?code|pincode|postal code/, 'pin'],
    [/address/, 'address'],
    [/name of (the )?vendor|vendor name|registered vendor|select vendor/, 'vendor'],
    [/(applicant|consumer|customer|full|beneficiary) name|^name\b/, 'name'],
    [/sanctioned|connected load/, 'sanctioned_load'],
    [/capacity/, 'capacity'],
    [/category/, 'category'],
    [/module (technology|type)|panel type/, 'module_type'],
    [/total cost|cost of rts|installation cost|project cost|quotation amount/, 'rts_cost'],
  ];
  const FILES = [[/agreement/, 'agreement'], [/bill/, 'bill'], [/aadhaar|identity/, 'aadhaar'],
                 [/passbook|bank|cheque/, 'passbook'], [/roof|site photo/, 'roof']];

  // anything the person changed with their own keyboard or mouse is theirs: isTrusted is false for our events
  const touch = e => { if (e.isTrusted && e.target && e.target.dataset) e.target.dataset.solaraHuman = '1'; };
  ['input', 'change'].forEach(t => document.addEventListener(t, touch, true));
  // defence in depth beside RULES: whatever the label says, these are for the person only
  const HUMAN_ONLY = /otp|captcha|one-?time|passw|security ?code|verification/i;
  const humanOnly = el => el.type === 'password' ||
    HUMAN_ONLY.test([el.id, el.name, el.autocomplete, el.getAttribute('aria-label'), el.placeholder].join(' '));
  const CUSTOM = '[role=combobox],[role=listbox],mat-select,.mat-select,.ng-select,.select2-selection,.dropdown-toggle';

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
    (el.getAttribute('aria-labelledby') || '').split(' ').forEach(id => { const x = id && document.getElementById(id); if (x) t.push(x.innerText); });
    if (el.getAttribute('aria-label')) t.push(el.getAttribute('aria-label'));
    const explicit = t.length > 0;  // a field that names itself is not named by its neighbours
    ['placeholder', 'formcontrolname', 'name'].forEach(a => el.getAttribute(a) && t.push(el.getAttribute(a)));
    let p = el.parentElement;
    for (let i = 0; i < 3 && p && !explicit; i++, p = p.parentElement) {
      const lab = p.querySelector('label, mat-label, .form-label');
      if (lab && !lab.contains(el)) { t.push(lab.innerText); break; }
    }
    const td = el.closest('td'); if (td && td.previousElementSibling) t.push(td.previousElementSibling.innerText);
    return norm(t.join(' | ').replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[_-]/g, ' '));
  }

  // the field's name as the owner sees it on the page, for "Filled" and "Left for you"
  const shown = el => ((el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`)?.innerText) ||
    el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.closest('.form-group,.fg,.f')?.querySelector('label')?.innerText ||
    el.name || labelOf(el)).replace(/[:*\s]+$/, '').replace(/^(enter|select)\s+/i, '').trim().slice(0, 50);
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

  // ---------- custom dropdowns (PrimeNG on the live PM Surya Ghar portal) ----------
  // Open the list with a click, pick the one option whose text matches, check the box now shows it.
  // Proven on the live site's public State and District filter (7 Nov 2026): clicks sent from a page
  // script open the list and the form takes the choice; District unlocks once State is picked.
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const boxOf = el => el.closest('.p-dropdown, .p-select, mat-select, .mat-select, .ng-select') || el;
  const OPTS = '.p-dropdown-panel li[role=option], .p-select-overlay li[role=option], .cdk-overlay-pane mat-option, .ng-dropdown-panel .ng-option, [role=listbox] [role=option]';
  const optText = o => norm(o.getAttribute('aria-label') || o.innerText);
  const isLocked = box => box.matches('.p-disabled, .disable-input, [aria-disabled=true]') ||
    !!box.closest('.p-disabled, .disable-input') || box.querySelector('[aria-disabled=true]') !== null;
  // still showing its placeholder ("Select State"): nothing chosen yet, by anyone
  const isEmpty = el => !!boxOf(el).querySelector('.p-placeholder, .mat-select-placeholder, .ng-placeholder') ||
    /^(select|choose|--)/i.test(boxOf(el).innerText.trim());
  async function pickCustom(el, value) {
    const box = boxOf(el), want = norm(value);
    for (let i = 0; i < 20 && isLocked(box); i++) await sleep(150);   // waits for the field above it
    if (isLocked(box)) return false;
    // the list above may still be fading out (PrimeNG animates the close); its options must not be read as this one's
    for (let i = 0; i < 15 && [...document.querySelectorAll(OPTS)].some(visible); i++) await sleep(100);
    box.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    let opts = [];
    for (let i = 0; i < 25 && !opts.length; i++) { await sleep(150); opts = [...document.querySelectorAll(OPTS)].filter(visible); }
    let hit = opts.filter(o => optText(o) === want);
    if (hit.length !== 1) hit = opts.filter(o => optText(o).length > 3 && (optText(o).includes(want) || want.includes(optText(o))));
    if (hit.length !== 1) {   // none or several: close the list again and leave it to the owner
      if ([...document.querySelectorAll(OPTS)].some(visible)) box.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      return false;
    }
    const chosen = optText(hit[0]);
    hit[0].dispatchEvent(new MouseEvent('click', { bubbles: true }));
    for (let i = 0; i < 10 && !norm(box.innerText).includes(chosen); i++) await sleep(100);
    if (!norm(box.innerText).includes(chosen)) return false;
    box.style.outline = '2px solid #2BB673';
    return true;
  }

  // ---------- the vendor's application lists ----------
  // My Application and Vendor Consent: read every row and bring the customers Solara knows up to date.
  function listRows(table) {
    const head = [...table.rows[0].cells].map(c => norm(c.innerText));
    const ai = head.findIndex(h => /application (no|number)/.test(h)), si = head.findIndex(h => /^status/.test(h));
    if (ai < 0) return null;
    return { status: si >= 0, rows: [...table.rows].slice(1).map(r => ({ app_no: (r.cells[ai] || {}).innerText?.trim(),
      status: si >= 0 ? (r.cells[si] || {}).innerText?.trim() : '' })).filter(r => /^NP-/i.test(r.app_no || '')) };
  }
  async function listMode(list) {
    if (!list.status) {   // Vendor Consent: these are waiting for the owner's approval, nothing to save yet
      say(`<div style="margin-top:4px">${list.rows.length} application(s) waiting for your approval here.</div>` +
        '<div style="margin-top:6px;color:#8FA3B2">Approve each one yourself. Then open My Application: Solara reads it and updates every customer.</div>');
      return;
    }
    say('Reading the list for Solara…');
    const r = await ask({ type: 'report', body: { event: 'portal_list', page: location.host + location.pathname, rows: list.rows } });
    if (!r.ok) { say(`<span style="color:#F2A6A0">Solara was not updated: ${esc(r.error)}</span>` + btn('solaraRetry', 'Try again'));
      panel.querySelector('#solaraRetry').onclick = scan; return; }
    const d = r.data || {};
    say(`<div id="solaraList" style="margin-top:4px">` +
      ((d.updated || []).length ? `<b>Solara updated:</b>` + d.updated.map(u => `<div style="margin-top:3px">${esc(u.name)}: ${esc(u.what)}</div>`).join('')
        : `Read ${list.rows.length} application(s). Nothing new for Solara.`) +
      ((d.problems || []).length ? `<div style="margin-top:6px;color:#F2C879">` + d.problems.map(u => `${esc(u.name)}: ${esc(u.what)}`).join('<br>') + '</div>' : '') +
      ((d.unknown || []).length ? `<div style="margin-top:6px;color:#8FA3B2">Statuses Solara does not know yet (nothing changed): ${esc(d.unknown.join(', '))}</div>` : '') +
      '</div>');
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

  // `picked` means the owner chose this customer in the panel on purpose; that choice is respected
  const remember = async c => { const { current } = await chrome.storage.local.get('current');
    // a finished registration is not carried to the next blank form; only an explicit pick keeps it
    if (c.application_no && !(current && current.cid === c.customer_id && current.picked)) {
      if (current && current.cid === c.customer_id) chrome.storage.local.remove('current');
      return;
    }
    chrome.storage.local.set({ current: { cid: c.customer_id, at: Date.now(), picked: !!(current && current.cid === c.customer_id && current.picked) } }); };
  const recalled = async () => { const { current } = await chrome.storage.local.get('current');
    return current && Date.now() - current.at < 45 * 60 * 1000 ? { cid: current.cid, picked: !!current.picked } : null; };

  async function scan() {
    const root = scope();
    const consumer = labelled('Consumer Number', root, /^\d{9,14}$/) || one(/\b\d{12}\b/g, root);
    const app = labelled('Application Number', root, /^NP-/) || one(/\bNP-[A-Z0-9]+-\d{6,}\b/g, root);
    const fields = [...root.querySelectorAll('input,select,textarea')].filter(el => visible(el) &&
      !['hidden', 'checkbox', 'radio', 'submit', 'button', 'password'].includes(el.type));
    const list = !consumer && !app && root === document.body &&
      [...document.querySelectorAll('table')].filter(t => t.rows.length > 1).map(listRows).find(x => x && x.rows.length);
    if (list) return listMode(list);
    let cid = '';
    if (!consumer && !app) {
      if (!fields.length) { say('<span style="color:#8FA3B2">Nothing to do on this page.</span>'); return; }
      const rec = await recalled();
      if (!rec) return pick();
      cid = rec.cid;
    }
    say('Looking up this customer…');
    const r = await ask({ type: 'lookup', consumer_no: consumer, app_no: app, cid });
    if (!r || !r.ok) { say(`<span style="color:#F2A6A0">${esc((r && r.error) || 'No answer from Solara.')}</span>` + (fields.length ? btn('solaraPick', 'Choose the customer') : '') + btn('solaraRetry', 'Try again'));
      const p = panel.querySelector('#solaraPick'); if (p) p.onclick = pick;
      panel.querySelector('#solaraRetry').onclick = scan; return; }
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
      // this registration is finished: the next blank form must ask who it is for, never assume
      if (rep.ok) { c.application_no = app; chrome.storage.local.remove('current'); }
      saved = rep.ok ? `<div style="margin-top:6px;color:#5FD3A8">Application number <b>${esc(app)}</b> saved in Solara.</div>`
        : `<div style="margin-top:6px;color:#F2A6A0">Application number <b>${esc(app)}</b> was NOT saved: ${esc(rep.error)}. Type it into Solara yourself.</div>`;
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
      await chrome.storage.local.set({ current: { cid: b.dataset.pick, at: Date.now(), picked: true } }); scan(); });
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
      !['hidden', 'checkbox', 'radio', 'submit', 'button', 'password', 'file'].includes(el.type) && !humanOnly(el));
    // custom dropdowns are picked by their visible option text; one that cannot be matched is named for the owner
    const customs = [...root.querySelectorAll(CUSTOM)].filter(el => visible(el) && !el.closest('select') &&
      !el.querySelector('input:not([type=hidden]),select')).map(el => {
        const key = ruleFor(labelOf(el)); return key ? { el, key, label: labelOf(el).split(' | ')[0] || key } : null; })
      .filter(x => x && c.values[x.key] != null);
    const issues = c.issues || [];
    const issueHtml = (issues.length ? `<div style="margin-top:8px;padding:8px;border-radius:7px;background:#3A2E12;color:#F2C879">` +
      `<b>${issues.length} to sort out in Solara first</b>` + issues.map(i => `<div style="margin-top:3px"><b>${esc(i.kind)}</b>: ${esc(i.field)} &mdash; ${esc(i.message)}</div>`).join('') + '</div>' : '') +
      (c.build_error ? `<div style="margin-top:6px;color:#F2A6A0">${esc(c.build_error)}</div>` : '');
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
    // a blank form says nothing about whose it is: the button names the customer, so a carried-over
    // customer is seen before anything is filled
    const pickable = customs.filter(x => isEmpty(x.el));
    say(head + saved + issueHtml + (fillable.length || files.length || pickable.length ? btn('solaraFill', (issues.length ? 'Fill anyway: ' : 'Fill ') + `${fillable.length + pickable.length} field(s) for ${esc((c.name || '').split(' ')[0])}` +
      (files.length ? ` and attach ${files.length} file(s)` : ''), !issues.length) : '<div style="margin-top:6px;color:#8FA3B2">No field here that Solara knows.</div>') +
      (agreementBox && c.agreement_draft ? '<div style="margin-top:6px;color:#F2C879">This agreement is a DRAFT format; the client has not approved the wording yet.</div>' : '') +
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
      mark.textContent = rep.ok ? 'Saved in Solara: agreement uploaded' : 'NOT saved: ' + rep.error;
    };
    const fill = panel.querySelector('#solaraFill');
    if (!fill) return;
    fill.onclick = async () => {
      let filled = 0, kept = 0, attached = 0;
      const left = [], done = [], failed = [];
      // dropdowns first, top to bottom: a later box (District) often waits for the one above it (State)
      for (const { el, key } of customs) {
        const label = shown(el);
        if (!isEmpty(el)) { kept += 1; continue; }   // someone already chose; theirs stays
        if (await pickCustom(el, c.values[key])) { filled += 1; done.push(label); }
        else left.push(`${label} (pick “${c.values[key]}” yourself)`);
      }
      for (const { el, key } of plan) {
        const label = shown(el);
        if (key === null) continue; // OTP, CAPTCHA: the person types these
        if (!key || c.values[key] == null) { if (!el.value) left.push(label); continue; }
        // never overwrite what a person typed or chose
        if ((el.value && el.tagName !== 'SELECT') || el.dataset.solaraHuman) { kept += 1; continue; }
        if (setVal(el, c.values[key]) && (el.tagName === 'SELECT' || el.value === String(c.values[key]))) { filled += 1; done.push(label); }
        else { left.push(label); failed.push(label); }   // the page refused or changed the value
      }
      const checkNames = plan.filter(p => (c.derived || []).includes(p.key) && done.includes(labelOf(p.el).split(' | ')[0]))
        .map(p => labelOf(p.el).split(' | ')[0]);
      for (const { el, kind } of files) {
        if (kind === 'agreement' && !agreementReady) { left.push('agreement (not signed yet)'); continue; }
        if (el.files && el.files.length) { kept += 1; continue; }   // a file you chose stays
        const ok = kind === 'agreement' ? await attach(el, { type: 'file', cid: c.customer_id, key: 'agreement' })
          : c.docs.includes(kind) && await attach(el, { type: 'doc', cid: c.customer_id, kind });
        if (ok) attached += 1; else left.push(kind + (c.docs.includes(kind) || kind === 'agreement' ? ' (could not be fetched from Solara)' : ' (not on file)'));
      }
      panel.dataset.filled = String(filled);
      panel.dataset.attached = String(attached);
      fill.outerHTML = `<div id="solaraFilled" style="margin-top:8px"><b>Filled ${filled}${attached ? `, attached ${attached}` : ''}.</b>` +
        (kept ? ` Kept ${kept} you had typed.` : '') +
        (failed.length ? `<br><span style="color:#F2A6A0">The page did not accept: ${esc(failed.join(', '))}</span>` : '') +
        (done.length ? `<div style="margin-top:4px;color:#8FA3B2">Filled: ${esc(done.join(', '))}</div>` : '') +
        (checkNames.length ? `<div style="margin-top:4px;color:#F2C879">Check these, Solara worked them out: ${esc(checkNames.join(', '))}</div>` : '') +
        (left.length ? `<br><span style="color:#F2C879">Left for you: ${esc([...new Set(left)].join(', '))}</span>` : '') +
        '<br>Check the page, then press the portal\'s button yourself.</div>';
      ask({ type: 'report', body: { customer_id: c.customer_id, portal: location.host, attached: filled + attached,
        page: location.host + location.pathname, left: [...new Set(left)] } }).then(r => {
        if (!r.ok) panel.querySelector('#solaraFilled').insertAdjacentHTML('beforeend',
          `<br><span style="color:#F2A6A0">Solara could not be told what was filled: ${esc(r.error)}</span>`); });
    };
  }

  scan();
  // single-page portals change screens without reloading; read the page again when they do
  let last = location.href;
  setInterval(() => { if (location.href !== last) { last = location.href; setTimeout(scan, 800); } }, 700);
})();
