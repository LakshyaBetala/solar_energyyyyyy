// Solara co-pilot panel, inside the operator's own browser.
// - MSEDCL upload page: attaches Solara's six documents to the right rows.
// - Any portal form (PM Surya Ghar, DCR): fills fields by their visible label, attaches the
//   customer's documents and the signed agreement, saves the application number to Solara.
// It never types an OTP, CAPTCHA or password, never ticks a consent box, never presses Submit,
// and never overwrites something already typed.
(() => {
  // after the extension is reloaded or updated, an already-open page keeps a dead copy of this script;
  // every chrome.* call then throws "Extension context invalidated". These never throw.
  const alive = () => { try { return !!chrome.runtime.id; } catch (e) { return false; } };
  const store = {
    get: async k => { try { return alive() ? await chrome.storage.local.get(k) : {}; } catch (e) { return {}; } },
    set: async o => { try { if (alive()) await chrome.storage.local.set(o); } catch (e) { /* page needs a reload */ } },
    remove: async k => { try { if (alive()) await chrome.storage.local.remove(k); } catch (e) { /* same */ } },
  };
  // a closed or reloaded extension, or a stopped server, must show a message and never throw
  const ask = async msg => {
    try { return (await chrome.runtime.sendMessage(msg)) || { ok: false, error: 'No answer from Solara.' }; }
    catch (e) { return { ok: false, error: 'The co-pilot was updated or restarted. Reload this page (F5).' }; }
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
    [/capacity|\bk ?wp\b/, 'capacity'],                              // "Proposed kWp", read as "k wp"
    [/category/, 'category'],
    [/\bgender\b/, 'gender'],                                         // from the Aadhaar QR
    [/ifsc/, 'ifsc'],                                                 // subsidy bank details, from the passbook
    [/account holder/, 'account_holder'],
    [/account type/, 'account_type'],                                 // Savings, flagged for a check
    [/bank name|select bank/, 'bank_name'],
    [/module (technology|type)|panel type/, 'module_type'],
    [/total cost|cost of rts|installation cost|project cost|quotation amount/, 'rts_cost'],
  ];
  const FILES = [[/agreement/, 'agreement'], [/bill/, 'bill'], [/aadhaar|identity/, 'aadhaar'],
                 [/passbook|bank|cheque/, 'passbook'], [/roof|site photo|pre ?installation/, 'roof']];

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
  const has = v => v != null && String(v).trim() !== '';
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
  let lastCands = [];   // the choices the last pick saw, for the fallback popup
  const optName = o => (o.getAttribute('aria-label') || o.innerText || '').trim();
  async function pickCustom(el, value, mode) {
    const box = boxOf(el), want = norm(value);
    for (let i = 0; i < 20 && isLocked(box); i++) await sleep(150);   // waits for the field above it
    if (isLocked(box)) return false;
    // the list above may still be fading out (PrimeNG animates the close); its options must not be read as this one's
    for (let i = 0; i < 15 && [...document.querySelectorAll(OPTS)].some(visible); i++) await sleep(100);
    box.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    let opts = [];
    for (let i = 0; i < 25 && !opts.length; i++) { await sleep(150); opts = [...document.querySelectorAll(OPTS)].filter(visible); }
    lastCands = opts.map(optName).filter(n => n && !/^no (results|records|data)/i.test(n));
    if (mode === 'list') {   // only read the choices, then close the list again
      if ([...document.querySelectorAll(OPTS)].some(visible)) box.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      return lastCands;
    }
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

  // ---------- the customer login's tracker ----------
  // Ten stages, each "Upload Agreement / Completed / 07-11-2026 7:23 pm" (seen 7 Nov 2026). Turned into
  // the same "Stage (State)" words as the vendor's list, for the first stage not Completed.
  const STAGES = ['Registration', 'Application', 'Feasibility', 'Vendor Selection', 'Upload Agreement', 'Installation',
    'Inspection', 'Project Commissioning', 'Subsidy Request', 'Subsidy Disbursal'];
  const STAGE_RE = new RegExp(`\\b(${STAGES.map(s => s.replace(' ', '\\s+')).join('|')})\\s*` +
    '(Completed|In\\s+Progress|Pending|Rejected|Returned?|Not\\s+Redeemed|Redeemed|Disbursed)\\b', 'gi');
  const APP_RE = /\bNP-[A-Z0-9]+-\d{6,}\b/g;
  function trackerRows() {
    const cards = new Set(), w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (w.nextNode()) {
      if (!/^\s*Subsidy\s+Disbursal\s*$/i.test(w.currentNode.nodeValue) || panel.contains(w.currentNode)) continue;
      let p = w.currentNode.parentElement;   // up to the card that also shows its application number
      while (p && p !== document.body && !(p.innerText.match(APP_RE) || []).length) p = p.parentElement;
      if (p && p !== document.body) cards.add(p);
    }
    return [...cards].map(card => {
      const nums = new Set(card.innerText.match(APP_RE));
      const st = [...card.innerText.matchAll(STAGE_RE)].map(m => [m[1], m[2]].map(s => s.replace(/\s+/g, ' ')));
      if (nums.size !== 1 || st.length < 5) return null;   // not a tracker we can read for sure: leave it
      const cur = st.find(([, s]) => !/^completed$/i.test(s)) || st[st.length - 1];
      return { app_no: [...nums][0], status: `${cur[0]} (${cur[1]})` };
    }).filter(Boolean);
  }

  // ---------- the two logins side by side ----------
  // The vendor and the customer login open in two tabs; what one finishes, the other is told.
  const APPROVE_STEPS = 'In the customer login: Action &rarr; Submit Agreement Details &rarr; Approve &rarr; tick the declaration ' +
    '&rarr; the customer reads you the SMS code &rarr; you press Verify &amp; Approve.';
  const here = location.host + '/' + location.pathname.split('/')[1];
  let handoff = null;
  const banner = () => handoff && handoff.from !== here && Date.now() - handoff.at < 30 * 60 * 1000 ?
    `<div id="solaraHandoff" style="margin-top:6px;padding:8px;border-radius:7px;background:#12303A;color:#BFE9D9">${esc(handoff.text)}</div>` : '';
  const tell = text => store.set({ handoff: { text, from: here, at: Date.now() } });
  async function markApproved(cid, name, el) {
    const rep = await ask({ type: 'report', body: { customer_id: cid, event: 'customer_approved' } });
    el.textContent = rep.ok ? 'Saved in Solara: approved by the customer' : 'NOT saved: ' + rep.error;
    if (rep.ok) tell(`${name} approved the agreement. Milestone 1 is done; installation can start.`);
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
      (d.seen || []).filter(s => s.next && s.next.act === 'approve').map(s =>
        `<div style="margin-top:8px;padding:8px;border-radius:7px;background:#12303A"><b>${esc(s.name)}: the customer approves next</b>` +
        `<div style="margin-top:3px;color:#BFE9D9">${APPROVE_STEPS}</div>` +
        `<button data-approved="${esc(s.id)}" data-name="${esc(s.name)}" style="display:block;width:100%;margin-top:8px;padding:8px;border:0;border-radius:7px;cursor:pointer;font-weight:700;background:#24343F;color:#E8EEF2">I pressed Verify &amp; Approve: mark it approved</button></div>`).join('') +
      '</div>');
    panel.querySelectorAll('[data-approved]').forEach(b => b.onclick = () => markApproved(b.dataset.approved, b.dataset.name, b));
    if ((d.updated || []).some(u => /approved/.test(u.what))) tell(d.updated.filter(u => /approved/.test(u.what)).map(u => u.name).join(', ') +
      ' approved the agreement on the portal. Installation can start.');
    // the customer login shows one customer: the approval dialog opened from here is theirs
    if (list.rows.length === 1 && (d.seen || []).length === 1)
      store.set({ current: { cid: d.seen[0].id, at: Date.now(), picked: true } });
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
    `<span id="solaraRescan" style="cursor:pointer;color:#8FA3B2" title="Read this page again">&#8635;</span></div>` + banner() + html +
    `<div style="margin-top:8px;text-align:right"><a href="#" id="solaraLayout" style="color:#8FA3B2;font-size:11px">Send this page's layout to Solara</a></div>`; };
  document.body.appendChild(panel);
  panel.addEventListener('click', e => { if (e.target.id === 'solaraRescan') scan(); if (e.target.id === 'solaraLayout') { e.preventDefault(); sendLayout(e.target); } });

  // For mapping a real portal page in the live session: field names, types and list choices only.
  // What is typed in a field is never read; neither is the page's text.
  async function sendLayout(link) {
    const short = s => String(s ?? '').trim().slice(0, 80);
    const els = [...document.querySelectorAll('input,select,textarea,' + CUSTOM)].filter(el => visible(el) && !panel.contains(el) &&
      el.type !== 'hidden' && !(el.matches(CUSTOM) && el.querySelector('input,select')));
    const fields = els.slice(0, 200).map(el => ({ tag: el.tagName.toLowerCase(), type: short(el.type || el.getAttribute('role')),
      label: short(shown(el)), all_labels: short(labelOf(el)), rule: (k => k === null ? 'never' : k || 'no rule')(ruleFor(labelOf(el))), id: short(el.id),
      name: short(el.name || el.getAttribute('formcontrolname')), placeholder: short(el.placeholder), required: !!el.required,
      options: el.tagName === 'SELECT' ? [...el.options].slice(0, 60).map(o => short(o.text)) : undefined }));
    const buttons = [...document.querySelectorAll('button,[role=button],input[type=submit]')].filter(b => visible(b) && !panel.contains(b))
      .slice(0, 40).map(b => short(b.innerText || b.value || b.getAttribute('aria-label')));
    link.textContent = 'Sending…';
    const r = await ask({ type: 'report', body: { event: 'page_layout', page: short(location.host + location.pathname + location.hash),
      title: short(document.title), fields, buttons } });
    link.textContent = r.ok ? `Sent: ${fields.length} fields` : 'Not sent: ' + r.error;
  }

  // ---------- the fallback popup at the bottom ----------
  // Anything the co-pilot cannot fill by itself lands here: a typed value for a field Solara has no data
  // for, and a choice from the page's own list for a dropdown (also when several options match).
  // Everything in it is the owner's own input; it fills the page and, where Solara has a field, Solara.
  // ---------- suggestions ("mini AI", all plain rules, no model) ----------
  // For a field Solara has no exact value for: look through everything Solara knows about the customer and
  // offer the values whose names share words with the field's label. A dropdown is also matched against the
  // customer's address: a district named in the address is the likely district.
  const STOP = new Set(['the', 'of', 'no', 'number', 'enter', 'select', 'please', 'name', 'and', 'for', 'your']);
  const words = t => norm(t).split(' ').filter(w => w.length > 2 && !STOP.has(w));
  function suggestFor(c, label) {
    const want = new Set(words(label)); if (!want.size) return [];
    const pool = [...(c.fields || []).map(f => [f.label, f.value]), ...Object.entries(c.values || {}).map(([k, v]) => [k.replace(/_/g, ' '), v])];
    const seen = new Set(), out = [];
    pool.map(([k, v]) => ({ v: String(v ?? '').trim(), hits: words(k).filter(w => want.has(w)).length }))
      .filter(x => x.hits && x.v && x.v.length < 80).sort((a, b) => b.hits - a.hits)
      .forEach(x => { if (!seen.has(x.v)) { seen.add(x.v); out.push(x.v); } });
    return out.slice(0, 3);
  }
  const addressText = c => norm([c.values && c.values.address, c.values && c.values.place,
    ...(c.fields || []).filter(f => /address|place/i.test(f.label)).map(f => f.value)].join(' '));
  let fallbackItems = [];
  // retry the dropdowns that have a Solara value but could not be chosen yet (the portal lists the
  // distribution companies only after the district is picked)
  async function retryPending(c, customs) {
    for (const x of customs) {
      if (x.key && has(c.values[x.key]) && isEmpty(x.el) && await pickCustom(x.el, c.values[x.key])) {
        fallbackItems.forEach(it => { if (it.el === x.el) it.done = true; });
        panel.querySelector('#solaraFilled')?.insertAdjacentHTML('beforeend', `<div style="margin-top:4px;color:#5FD3A8">${esc(x.label)}: filled.</div>`);
      }
    }
    showFallback(c);
  }
  ['focusin', 'focusout', 'keydown', 'keyup', 'keypress', 'mousedown'].forEach(t => window.addEventListener(t, e => {
    const b = document.getElementById('solaraFallback'); if (b && b.contains(e.target)) e.stopImmediatePropagation();   // a modal dialog would steal the focus back
  }, true));
  const fbBox = () => {
    let b = document.getElementById('solaraFallback');
    if (!b) {
      b = document.createElement('div'); b.id = 'solaraFallback';
      b.style.cssText = 'position:fixed;left:14px;bottom:14px;z-index:2147483646;width:min(520px,calc(100vw - 370px));min-width:300px;max-height:46vh;overflow:auto;' +
        'background:#3A2E12;color:#F7E3B0;font:14px/1.4 system-ui,Arial,sans-serif;border-radius:10px;box-shadow:0 8px 28px rgba(0,0,0,.4);padding:12px';
      document.body.appendChild(b);
    }
    return b;
  };
  const fbInput = 'flex:1;min-width:0;padding:8px;border-radius:6px;border:0;color:#04150D;font-size:15px';
  function showFallback(c) {
    const box = fbBox();
    fallbackItems = fallbackItems.filter(i => !i.done);
    if (!fallbackItems.length) { box.remove(); return; }
    const typed = {};   // keep what is being typed or chosen across a redraw
    box.querySelectorAll('[data-fbv],[data-fbf]').forEach(e => { typed[e.dataset.fbv !== undefined ? 'v' + e.dataset.fbv : 'f' + e.dataset.fbf] = e.value; });
    box.innerHTML = `<div style="display:flex;justify-content:space-between"><b>Solara needs your help with ${fallbackItems.length} field(s)</b>` +
      `<span id="fbClose" style="cursor:pointer" title="Hide">&#10005;</span></div>` + fallbackItems.map((it, i) =>
      `<div style="margin-top:8px"><div style="font-size:12px">${esc(it.label)}${it.why ? ` &middot; <span style="opacity:.8">${esc(it.why)}</span>` : ''}</div><div style="display:flex;gap:6px;margin-top:3px">` +
      (it.type === 'text' ? `<input data-fbv="${i}" style="${fbInput}" autocomplete="off">`
        : it.options ? `<input data-fbf="${i}" placeholder="type to narrow the list" style="width:36%;${fbInput}"><select data-fbv="${i}" style="${fbInput}">${it.options.map(o => `<option>${esc(o)}</option>`).join('')}</select>`
        : `<button data-fbload="${i}" style="${fbInput};cursor:pointer;font-weight:700">Show the choices</button>`) +
      (it.type === 'text' || it.options ? `<button data-fbgo="${i}" style="border:0;border-radius:6px;padding:6px 14px;cursor:pointer;font-weight:700;font-size:15px">Fill</button>` : '') +
      '</div>' + ((it.suggest || []).length ? `<div style="margin-top:4px;font-size:12px">Suggested: ${it.suggest.map((v, j) =>
        `<button data-fbs="${i}|${j}" style="border:0;border-radius:12px;padding:3px 10px;margin-right:4px;cursor:pointer;background:#F2C879;color:#04150D;font-weight:700">${esc(v)}</button>`).join('')}</div>` : '') +
      '<div data-fbmsg="' + i + '" style="font-size:12px;margin-top:2px"></div></div>').join('');
    box.querySelectorAll('[data-fbv],[data-fbf]').forEach(e => { const k = e.dataset.fbv !== undefined ? 'v' + e.dataset.fbv : 'f' + e.dataset.fbf; if (typed[k] !== undefined && typed[k] !== '') e.value = typed[k]; });
    box.querySelector('#fbClose').onclick = () => box.remove();
    const note = (i, t, bad) => { const m = box.querySelector(`[data-fbmsg="${i}"]`); m.textContent = t; m.style.color = bad ? '#F2A6A0' : '#9FE3C1'; };
    box.querySelectorAll('[data-fbs]').forEach(b => b.onclick = () => {   // one tap on a suggestion fills it
      const [i, j] = b.dataset.fbs.split('|').map(Number), field = box.querySelector(`[data-fbv="${i}"]`), v = fallbackItems[i].suggest[j];
      if (field.tagName === 'SELECT') { const o = [...field.options].find(x => x.text === v); if (o) field.value = o.value; else return; } else field.value = v;
      box.querySelector(`[data-fbgo="${i}"]`).onclick();
    });
    box.querySelectorAll('[data-fbf]').forEach(f => f.oninput = () => {   // narrow a long list (36 states) while typing
      const sel = box.querySelector(`[data-fbv="${f.dataset.fbf}"]`), q = norm(f.value);
      [...sel.options].forEach(o => { o.hidden = !!q && !norm(o.text).includes(q); });
      const first = [...sel.options].find(o => !o.hidden); if (first) sel.value = first.value;
    });
    box.querySelectorAll('[data-fbload]').forEach(b => b.onclick = async () => {
      const it = fallbackItems[+b.dataset.fbload]; b.textContent = 'Reading the list…';
      const names = await pickCustom(it.el, '', 'list');
      if (names && names.length) { it.options = names; showFallback(c); } else b.textContent = 'The page would not show its list. Pick it on the page.';
    });
    box.querySelectorAll('[data-fbgo]').forEach(b => b.onclick = async () => {
      const i = +b.dataset.fbgo, it = fallbackItems[i], v = box.querySelector(`[data-fbv="${i}"]`).value.trim();
      if (!v) { note(i, 'Type or choose a value first.', true); return; }
      let ok;
      if (it.type === 'text') { ok = setVal(it.el, v); if (ok) it.el.dataset.solaraHuman = '1'; }
      else ok = await pickCustom(it.el, v);
      if (!ok) { note(i, 'The page did not take that. Pick it on the page itself.', true); return; }
      it.done = true;
      if (it.type === 'select' && c._customs) await retryPending(c, c._customs);
      const rep = await ask({ type: 'report', body: { customer_id: c.customer_id, event: 'detail', key: it.key, value: v } });
      note(i, rep.ok ? 'Filled' + (rep.data && rep.data.saved ? ', and saved in Solara.' : '.') : 'Filled. Solara did not save it: ' + rep.error);
      setTimeout(() => showFallback(c), 900);
    });
  }

  // `picked` means the owner chose this customer in the panel on purpose; that choice is respected
  const remember = async c => { const { current } = await store.get('current');
    // a finished registration is not carried to the next blank form; only an explicit pick keeps it
    if (c.application_no && !(current && current.cid === c.customer_id && current.picked)) {
      if (current && current.cid === c.customer_id) store.remove('current');
      return;
    }
    store.set({ current: { cid: c.customer_id, at: Date.now(), picked: !!(current && current.cid === c.customer_id && current.picked) } }); };
  const recalled = async () => { const { current } = await store.get('current');
    return current && Date.now() - current.at < 45 * 60 * 1000 ? { cid: current.cid, picked: !!current.picked } : null; };

  // After Start, the owner has typed the OTP and CAPTCHA and is signed in. Exactly three buttons are
  // ever pressed for the owner, each once per page address, and none of them submits anything:
  //   card  : the "Apply for Solar Rooftop" card (opens the form)
  //   vendor: "Yes" on "do you want your vendor to fill the application" (the owner's standing answer)
  //   fetch : "Fetch Details", which only loads the bill's data into the form
  const PRESS = {
    card: { find: 'a,button,[role=button],div,span,h1,h2,h3,h4,p', text: /apply\s+for\s+(a\s+)?solar\s+roof\s*top/i, up: 'a,button,[role=button],[routerlink],.card,[class*=card]' },
    vendor: { find: 'button,[role=button]', text: /^\s*yes\s*$/i, needs: /vendor[^.]{0,40}fill/i },
    fetch: { find: 'button,[role=button]', text: /^\s*fetch\s+details\s*$/i },
  };
  function openApplyCard(kind) {
    const spec = PRESS[kind], seenKey = 'solaraPress:' + kind + ':' + location.href;
    if (!spec || sessionStorage.getItem(seenKey)) return false;
    if (spec.needs && !spec.needs.test(scope().innerText)) return false;
    const hit = [...document.querySelectorAll(spec.find)]
      .filter(el => visible(el) && !panel.contains(el) && !el.disabled && spec.text.test((el.innerText || '').trim()) && (el.innerText || '').length < 120)
      .sort((x, y) => x.innerText.length - y.innerText.length)[0];
    if (!hit) return false;
    sessionStorage.setItem(seenKey, '1');
    (spec.up && hit.closest(spec.up) || hit).click();
    return true;
  }
  const running = async () => { const { run, vendorFills } = await store.get({ run: null, vendorFills: true });
    return run && Date.now() - run.at < 60 * 60 * 1000 ? { run, vendorFills } : null; };

  async function scan() {
    const go = await running();
    if (go && go.vendorFills && openApplyCard('vendor')) { say('<div style="margin-top:4px">Answering <b>Yes</b>: the vendor fills the form.</div>'); return; }
    if (go && openApplyCard('card')) { say('<div style="margin-top:4px">Opening <b>Apply for Solar Rooftop</b>…</div>'); return; }
    const root = scope();
    if (/want (the |your )?vendor to fill/i.test(root.innerText) && !(await running())) {
      const { vendorFills } = await store.get({ vendorFills: true });
      say(`<div style="margin-top:4px"><b>Answer ${vendorFills ? 'Yes' : 'No'}.</b> ${vendorFills ? 'The vendor fills the application.' : 'You fill it here yourself.'} Press Start and Solara answers for you.</div>`);
      return;
    }
    const track = root === document.body ? trackerRows() : [];
    if (track.length) return listMode({ status: true, rows: track });
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
      if (rep.ok) { c.application_no = app; store.remove('current'); }
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
      await store.set({ current: { cid: b.dataset.pick, at: Date.now(), picked: true } });
      const x = r.data.find(y => y.id === b.dataset.pick);
      say(`<div style="margin-top:4px"><b>${esc(x.name)}</b> &middot; ${esc(x.id)}</div>` +
        '<div style="margin-top:6px;color:#8FA3B2">Start fills the phone number. You type the OTP and CAPTCHA. Then Solara opens "Apply for Solar Rooftop" and fills the forms.</div>' +
        btn('solaraStart', 'Start', true));
      panel.querySelector('#solaraStart').onclick = async () => {
        await store.set({ run: { cid: x.id, at: Date.now() } }); scan(); };
    });
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
    const customsAll = [...root.querySelectorAll(CUSTOM)].filter(el => visible(el) && !el.closest('select') &&
      !el.querySelector('input:not([type=hidden]),select')).map(el => {
        const key = ruleFor(labelOf(el)); return key === null ? null : { el, key, label: shown(el) || key }; })
      .filter(Boolean);
    const customs = customsAll.filter(x => x.key && has(c.values[x.key]));
    const lackCustoms = customsAll.filter(x => (!x.key || !has(c.values[x.key])) && isEmpty(x.el));
    const issues = c.issues || [];
    const issueHtml = (issues.length ? `<div style="margin-top:8px;padding:8px;border-radius:7px;background:#3A2E12;color:#F2C879">` +
      `<b>${issues.length} to sort out in Solara first</b>` + issues.map(i => `<div style="margin-top:3px"><b>${esc(i.kind)}</b>: ${esc(i.field)} &mdash; ${esc(i.message)}</div>`).join('') + '</div>' : '') +
      (c.build_error ? `<div style="margin-top:6px;color:#F2A6A0">${esc(c.build_error)}</div>` : '');
    c._customs = customs;
    const plan = els.map(el => ({ el, key: ruleFor(labelOf(el)) }));
    const fillable = plan.filter(p => p.key && has(c.values[p.key]));
    // fields the page asks for that Solara knows by name but has no data for: the owner types them here
    const lacking = plan.filter(p => p.key !== null && (!p.key || !has(c.values[p.key])) && !p.el.value && p.el.tagName !== 'SELECT');   // also fields with no rule at all
    const lackHtml = '';
    fallbackItems = [...lacking.map(p => ({ type: 'text', el: p.el, key: p.key, label: shown(p.el) || p.key, why: p.key ? 'Solara has no data' : 'Solara does not know this field', suggest: suggestFor(c, shown(p.el) || p.key || '') })),
      ...lackCustoms.map(x => ({ type: 'select', el: x.el, key: x.key || '', label: x.label, why: x.key ? 'Solara has no data' : 'Solara does not know this field', suggest: suggestFor(c, x.label) }))];
    showFallback(c);
    const suggestLists = async () => {   // read each empty dropdown's list; a name that appears in the customer's address is the likely answer
      const hay = addressText(c), going = !!(await running());
      for (const it of fallbackItems.filter(i => i.type === 'select' && !i.options)) {
        const names = await pickCustom(it.el, '', 'list');
        if (!names || !names.length) continue;
        it.options = names;
        const inAddr = names.filter(n => norm(n).length > 3 && hay.includes(norm(n)));
        it.suggest = [...new Set([...inAddr, ...(it.suggest || []).filter(v => names.includes(v))])].slice(0, 3);
        if (going && inAddr.length === 1 && await pickCustom(it.el, inAddr[0])) {   // one clear match in the address: take it
          it.done = true;
          panel.querySelector('#solaraFilled')?.insertAdjacentHTML('beforeend', `<div style="margin-top:4px;color:#F2C879">${esc(it.label)}: chose <b>${esc(inAddr[0])}</b> from the customer's address. Check it.</div>`);
        }
      }
      showFallback(c);
      await retryPending(c, customs);   // a company list that was empty until the district was chosen
    };
    suggestLists();
    const files = [...root.querySelectorAll('input[type=file]')].filter(el => !el.disabled).map(el => {
      const lab = labelOf(el) + ' ' + norm((el.closest('tr,.upr,.fg,.form-group') || el.parentElement).innerText);
      const hit = FILES.find(([re]) => re.test(lab));
      return hit && { el, kind: hit[1] };
    }).filter(Boolean);
    // after Submit the portal locks the box, which is exactly when the owner marks it done
    const agreementBox = [...root.querySelectorAll('input[type=file]')].some(el => /agreement/.test(labelOf(el)));
    const agreementReady = c.files.some(f => f.key === 'agreement');
    // the customer login's Submit Agreement Details dialog: the OTP and Verify & Approve are the person's
    const approveBox = !agreementBox && /verify\s*&\s*approve|submit agreement details/i.test(root.innerText);
    // a blank form says nothing about whose it is: the button names the customer, so a carried-over
    // customer is seen before anything is filled
    const pickable = customs.filter(x => isEmpty(x.el));
    say(head + saved + issueHtml + lackHtml + (fillable.length || files.length || pickable.length ? btn('solaraFill', (issues.length ? 'Fill anyway: ' : 'Fill ') + `${fillable.length + pickable.length} field(s) for ${esc((c.name || '').split(' ')[0])}` +
      (files.length ? ` and attach ${files.length} file(s)` : ''), !issues.length) : '<div style="margin-top:6px;color:#8FA3B2">No field here that Solara knows.</div>') +
      (agreementBox && c.agreement_draft ? '<div style="margin-top:6px;color:#F2C879">This agreement is a DRAFT format; the client has not approved the wording yet.</div>' : '') +
      (agreementBox ? btn('solaraMarkUploaded', 'I pressed Submit: mark agreement uploaded') : '') +
      (approveBox ? `<div style="margin-top:8px;color:#BFE9D9">${APPROVE_STEPS}</div>` + btn('solaraMarkApproved', 'I pressed Verify &amp; Approve: mark it approved') : '') +
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
      if (rep.ok) tell(`${c.name}'s agreement is uploaded. Now the customer approves it: ${APPROVE_STEPS.replace(/&rarr;/g, '>').replace(/&amp;/g, '&')}`);
    };
    const appr = panel.querySelector('#solaraMarkApproved');
    if (appr) appr.onclick = () => markApproved(c.customer_id, c.name, appr);
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
        else {
          const cands = lastCands.slice(), want = norm(c.values[key]);
          const several = cands.filter(o => norm(o).includes(want) || want.includes(norm(o))).length > 1;
          left.push(`${label} (${several ? 'several match; choose below' : 'choose below'})`);
          fallbackItems.push({ type: 'select', el, key, label, options: cands.length ? cands : null,
            why: several ? `several options match “${c.values[key]}”` : `“${c.values[key]}” is not in the list` });
        }
      }
      const fillTexts = () => {
        for (const { el, key } of plan) {
          const label = shown(el);
          if (key === null) continue; // OTP, CAPTCHA: the person types these
          if (!key || !has(c.values[key])) { if (!el.value) left.push(label); continue; }
          // never overwrite what a person typed or chose
          if ((el.value && el.tagName !== 'SELECT') || el.dataset.solaraHuman) { kept += 1; continue; }
          if (setVal(el, c.values[key]) && (el.tagName === 'SELECT' || el.value === String(c.values[key]))) { filled += 1; done.push(label); }
          else { left.push(label); failed.push(label); }   // the page refused or changed the value
        }
      };
      fillTexts();
      const checkNames = plan.filter(p => (c.derived || []).includes(p.key) && done.includes(labelOf(p.el).split(' | ')[0]))
        .map(p => labelOf(p.el).split(' | ')[0]);
      for (const { el, kind } of files) {
        if (kind === 'agreement' && !agreementReady) { left.push('agreement (not signed yet)'); continue; }
        if (el.files && el.files.length) { kept += 1; continue; }   // a file you chose stays
        const ok = kind === 'agreement' ? await attach(el, { type: 'file', cid: c.customer_id, key: 'agreement' })
          : c.docs.includes(kind) && await attach(el, { type: 'doc', cid: c.customer_id, kind });
        if (ok) attached += 1; else left.push(kind + (c.docs.includes(kind) || kind === 'agreement' ? ' (could not be fetched from Solara)' : ' (not on file)'));
      }
      await retryPending(c, customs);
      await suggestLists();
      await retryPending(c, customs);
      fillTexts();   // the portal clears the CA number when a dropdown above it changes: fill it last
      panel.dataset.filled = String(filled);
      panel.dataset.attached = String(attached);
      fill.outerHTML = `<div id="solaraFilled" style="margin-top:8px"><b>Filled ${filled}${attached ? `, attached ${attached}` : ''}.</b>` +
        (kept ? ` Kept ${kept} you had typed.` : '') +
        (failed.length ? `<br><span style="color:#F2A6A0">The page did not accept: ${esc(failed.join(', '))}</span>` : '') +
        (done.length ? `<div style="margin-top:4px;color:#8FA3B2">Filled: ${esc(done.join(', '))}</div>` : '') +
        (checkNames.length ? `<div style="margin-top:4px;color:#F2C879">Check these, Solara worked them out: ${esc(checkNames.join(', '))}</div>` : '') +
        (left.length ? `<br><span style="color:#F2C879">Left for you: ${esc([...new Set(left)].join(', '))}</span>` : '') +
        '<br>Check the page, then press the portal\'s button yourself.</div>';
      const mine = [...root.querySelectorAll('input')].filter(el => visible(el) && !el.value && !el.readOnly && humanOnly(el) && el.type !== 'password');
      if (mine.length) {
        mine.forEach(el => { el.style.outline = '2px solid #F2C879'; });
        mine[0].focus();
        panel.querySelector('#solaraFilled').insertAdjacentHTML('beforeend',
          `<div style="margin-top:6px;padding:6px;border-radius:6px;background:#3A2E12;color:#F2C879"><b>Your turn:</b> type the ${esc(mine.map(el => labelOf(el).split(' | ')[0] || 'code').join(' and '))}, then press the portal's button. Solara fills the next page by itself.</div>`);
      }
      if (await running() && root.querySelector('input') && plan.some(p => p.key === 'consumer_no' && p.el.value) && openApplyCard('fetch'))
      {
        panel.querySelector('#solaraFilled').insertAdjacentHTML('beforeend', '<div id="solaraFetch" style="margin-top:6px;color:#5FD3A8">Pressed <b>Fetch Details</b>…</div>');
        // the portal answers in a few seconds: details, or "Data not Available" (seen live with an unknown CA number)
        for (let i = 0; i < 30; i++) {
          await sleep(300);
          const dlg = (document.querySelector('.p-dialog, [role=dialog]') || document.body).innerText, note = panel.querySelector('#solaraFetch');
          if (/data\s+not\s+available/i.test(dlg)) {
            note.style.color = '#F2A6A0';
            note.innerHTML = 'The portal has <b>no data for this consumer number</b>. Check the CA number on the bill and type the right one below.';
            const ca = plan.find(p => p.key === 'consumer_no');
            if (ca) { fallbackItems.push({ type: 'text', el: ca.el, key: 'consumer_no', label: shown(ca.el) || 'Consumer number', why: 'the portal found no data for ' + ca.el.value }); showFallback(c); }
            break;
          }
          if (!/fetch\s+details/i.test(dlg) || /^\s*next\s*$/im.test(dlg) && !/please fill required/i.test(dlg)) { note.innerHTML = 'Fetch Details done. Check the details that appear, then press Next yourself.'; break; }
        }
      }
      ask({ type: 'report', body: { customer_id: c.customer_id, portal: location.host, attached: filled + attached,
        page: location.host + location.pathname, left: [...new Set(left)] } }).then(r => {
        if (!r.ok) panel.querySelector('#solaraFilled').insertAdjacentHTML('beforeend',
          `<br><span style="color:#F2A6A0">Solara could not be told what was filled: ${esc(r.error)}</span>`); });
    };
    // hands-free mode (options page): fill as soon as the page opens, then ask the owner for the
    // OTP / CAPTCHA, which only a person types. Never submits, never types the OTP or CAPTCHA.
    store.get({ auto: false, run: null }).then(({ auto, run }) => {
      const going = run && run.cid === c.customer_id && Date.now() - run.at < 60 * 60 * 1000;
      if ((auto || going) && !issues.length) fill.onclick();
    });
  }

  store.get('handoff').then(x => { handoff = x.handoff || null; }).finally(scan);
  try { chrome.storage.onChanged.addListener((ch, area) => {
    if (area !== 'local' || !ch.handoff) return;
    handoff = ch.handoff.newValue || null;
    panel.querySelector('#solaraHandoff')?.remove();
    panel.firstElementChild?.insertAdjacentHTML('afterend', banner());
  }); } catch (e) { /* dead page */ }
  // single-page portals change screens without reloading; read the page again when they do
  let last = location.href;
  setInterval(() => { if (location.href !== last) { last = location.href; setTimeout(scan, 800); } }, 700);
})();
