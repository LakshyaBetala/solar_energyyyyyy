// Solara co-pilot panel, inside the operator's own browser.
// - Portal forms (PM Surya Ghar registration, feasibility report, the 5 installation steps, the DCR
//   certificate, Jan Samarth basic details): fills fields by their visible label, answers the Yes/No
//   questions Solara has on record, attaches the customer's files, saves the numbers the portal gives.
// - MSEDCL upload page: attaches Solara's six documents to the right rows.
// - Portal lists (My Application, MSEDCL consumer list): reads each row's status into Solara. Read only.
// It never types an OTP, CAPTCHA, password or Aadhaar number, never ticks a consent or declaration
// box, never presses Submit, Upload or Approve, and never overwrites something already typed.
(() => {
  // a closed or reloaded extension, or a stopped server, must show a message and never throw
  const ask = async msg => {
    try { return (await chrome.runtime.sendMessage(msg)) || { ok: false, error: 'No answer from Solara.' }; }
    catch (e) { return { ok: false, error: 'The co-pilot lost its connection. Reload this page.' }; }
  };
  const esc = s => String(s ?? '').replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
  const norm = s => String(s ?? '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  const NP = /\bNP-[A-Z0-9]+-\d{6,}\b/g;
  const MSEDCL = [['wcr', /work completion/i], ['annexure1', /annexure/i], ['dcr_decl', /declaration (of|for) dcr|dcr declaration/i],
                  ['net_agreement', /net agreement/i], ['datasheet', /brochure|datasheet/i],
                  ['site_photo', /photo(graph)?s? of installed/i]];
  // first match wins; null means "never touch". A third element limits a rule to pages whose text
  // matches it. Labels are the client's real screens (tests/real_labels.py checks every one).
  // boxes whose value never leaves the browser: not read, not filled, blanked in every receipt
  const SECRET = /otp|captcha|human check|password|security code|verification code|aadha?ar (no|number|card)|\buid\b|virtual id/;
  const RULES = [
    [/otp|captcha|human check|password|security code|verification code/, null],
    [/aadha?ar (no|number|card number)|\buid\b|virtual id/, null],    // the customer types their own Aadhaar
    [/user ?id|username|register email|login/, null],                 // the vendor's own login
    [/name of vendor employee|employee (who )?visited/, 'visitor_name'],
    [/contact number/, 'visitor_phone', /vendor employee/],
    [/employee|contact person|contact number/, null],                  // the vendor's site staff, not the customer
    [/purchase order|project name|remarks/, null],                     // the vendor's own optional references
    [/application (no|number)/, 'application_no'],
    [/certificate (no|number)|dcr cert/, 'dcr_cert_no'],
    [/consumer (account )?(no|number)|ca number|consumer id/, 'consumer_no'],
    [/\bbranch\b/, 'only_option'],                                     // filled only when there is one choice
    [/loan amount|date of birth|\bdob\b|\bpan\b/, null],              // the customer's own choices
    [/\bbank\b|ifsc/, null, /jan ?samarth|loan/],                     // on the loan form the customer picks the bank
    [/mobile|phone/, 'mobile'],
    [/e ?mail/, 'email'],
    [/latitude/, 'lat'],
    [/longitude/, 'lng'],
    [/(invoice|e ?way bill).*\bdate\b/, 'invoice_date'],            // DCR "Invoice / E-Way Bill Date": never the number
    [/invoice|e ?way bill/, 'invoice_no'],
    [/file name description/, null],                                  // the owner names an extra document
    [/item type/, 'item_type'],
    [/subsidy scheme|name of scheme/, 'scheme'],
    [/type of location|location type/, 'location_type'],
    [/phase/, 'phase'],
    [/(capacity|rating).*inverter|inverter.*(capacity|rating)/, 'inverter_kw'],
    [/quantity of (solar )?inverter|(no|number) of inverters?/, 'inverter_qty'],
    [/manufacturer of (solar )?inverter|inverter (make|manufacturer)/, 'inverter_make'],
    [/serial.*inverter|inverter serial/, 'inverter_serial'],
    [/(capacity|rating).*(wp|module)|module (capacity|wattage)/, 'module_wp'],
    [/quantity of (solar )?pv module|(no|number) of (pv )?modules|^quantity\b/, 'module_count'],
    [/manufacturer of (solar )?pv module|module (make|manufacturer)/, 'module_make'],
    [/almm|model (no|number)/, 'almm_model'],
    [/panel numbers|serial numbers?/, 'module_serials'],
    [/distribution|discom|electricity company|utility/, 'discom'],
    [/\bdistrict\b/, 'district'],
    [/\bstate\b/, 'state'],
    [/pin ?code|pincode|postal code/, 'pin'],
    [/address/, 'address'],
    [/name of (the )?vendor|vendor name|registered vendor|select vendor/, 'vendor'],
    [/name as per aadhaar/, 'aadhaar_name'],
    [/(applicant|consumer|customer|full|beneficiary) name|^name\b/, 'name'],
    [/shadow free roof area|roof area/, 'roof_area'],
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
  // Yes/No questions answered from the record (radio buttons). Checkboxes are declarations: never.
  const YESNO = [[/load bearing/, 'roof_load_ok'], [/shadow free roof for|availability of shadow/, 'shadow_free'],
                 [/vendor has visited|visited the installation site/, 'site_visited'],
                 [/surge|\bspd\b/, 'protection_checks'], [/\bmcb\b|circuit breaker/, 'protection_checks'],
                 [/earthing/, 'protection_checks'], [/lightning/, 'lightning_arrester']];
  // upload boxes: [label, what, where it comes from]
  const FILES = [[/agreement/, 'agreement', 'file'], [/quotation/, 'quotation', 'file'],
                 [/pre ?installation/, 'roof', 'doc'],
                 [/plant photo|pv plant|plant with consumer|geo ?co ?ordinates|installed (pv )?system/, 'site_photo', 'doc'],
                 [/excel|column a/, 'dcr', 'xlsx'],
                 [/bill/, 'bill', 'doc'], [/aadhaar|identity/, 'aadhaar', 'doc'],
                 [/passbook|bank|cheque/, 'passbook', 'doc'], [/roof|site photo/, 'roof', 'doc']];
  // pages that file a step the owner marks done after pressing the portal's own button
  const MARK = {
    sfr: 'I pressed Submit: mark the feasibility report filed',
    installation: 'I pressed Final Submit: mark the installation filed',
    agreement_uploaded: 'I pressed Submit: mark agreement uploaded',
  };
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
  // the portal's own examples ("e.g. NP-RJJOV25-5119272", "format: NP-...") are not this customer's number
  const noExamples = t => String(t || '').replace(/(e\.?\s?g\.?|example|format)[:\s]*\(?NP-[A-Z0-9-]+/gi, ' ');
  const secretField = el => el.type === 'password' || SECRET.test(labelOf(el));
  const textOf = root => noExamples(root.innerText + ' ' + [...root.querySelectorAll('input')].filter(i => !secretField(i)).map(i => i.value).join(' '));
  const one = (re, root) => { const all = new Set(textOf(root).match(re) || []); return all.size === 1 ? [...all][0] : ''; };
  const zeroish = v => /^\s*0+([.,]0+)?\s*$/.test(v || '');

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

  function tableOf(el) {
    const td = el.closest('td'); const table = td && td.closest('table');
    return table ? { td, table } : null;
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
    const tb = tableOf(el);
    if (tb) {
      // a grid of inputs: the column's header names the field, the heading above names the table
      const head = tb.table.querySelector('tr');
      const th = head && head !== tb.td.parentElement && head.children[tb.td.cellIndex];
      if (th) t.push(th.innerText);
      else if (tb.td.previousElementSibling) t.push(tb.td.previousElementSibling.innerText);
      let h = tb.table.previousElementSibling;
      while (h && !/^H[1-6]$/.test(h.tagName) && !h.querySelector('h1,h2,h3,h4,h5,h6')) h = h.previousElementSibling;
      if (h) t.push(h.innerText);
    }
    return norm(t.join(' | ').replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[_-]/g, ' '));
  }

  // the field's name as the owner sees it on the page, for "Filled" and "Left for you"
  const shown = el => ((el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`)?.innerText) ||
    el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.closest('.form-group,.fg,.f')?.querySelector('label')?.innerText ||
    el.name || labelOf(el)).replace(/[:*\s]+$/, '').replace(/^(enter|select)\s+/i, '').trim().slice(0, 50);
  const ruleFor = (label, page) => { const r = RULES.find(([re, , ctx]) => re.test(label) && (!ctx || ctx.test(page))); return r ? r[1] : undefined; };

  function setVal(el, v) {
    if (el.tagName === 'SELECT') {
      const want = norm(v), opts = [...el.options].filter(o => o.value !== '' && !/^select/i.test(o.text.trim()));
      const opt = v === '__only__' ? (opts.length === 1 ? opts[0] : null)
        : opts.find(o => norm(o.text) === want || norm(o.value) === want) ||
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

  // ---------- the problem cases (K4): said plainly, recorded once, nothing filed twice ----------
  // [kind, what the portal shows, what the owner does now]
  const TROUBLE = [
    ['session', /session\s+(has\s+)?(expired|timed?\s*out)|you have been logged out|please log\s?in again|login again to continue/i,
      'The portal logged you out. Log in again and open the same page. Solara still has everything, and it checks what is already filed before filling again.'],
    ['otp_wrong', /(incorrect|invalid|wrong|mismatch(ed)?)\s+(otp|code)|(otp|code)\s+(is\s+|has\s+)?(incorrect|invalid|wrong|expired)/i,
      'The code was not accepted. Ask the customer to read the newest SMS again, slowly; an older SMS will not work. Nothing was filed, and what is filled stays.'],
    ['otp_resend', /new (otp|code) has been sent|(otp|code) (has been )?re-?sent|resent successfully/i,
      'A new code is on its way. Use only the newest SMS.'],
  ];
  const told = new Set();
  const trouble = root => {
    const text = root.innerText || '';
    const hit = TROUBLE.find(([, re]) => re.test(text));
    if (!hit) return '';
    const key = hit[0] + '|' + location.href;
    if (!told.has(key)) {
      told.add(key);
      recalled().then(rec => ask({ type: 'report', body: { customer_id: rec ? rec.cid : '', event: 'problem', kind: hit[0], page: location.host + location.pathname } }));
    }
    return `<div id="solaraTrouble" data-kind="${hit[0]}" style="margin-top:8px;padding:8px;border-radius:7px;background:#3A2E12;color:#F2C879">${hit[2]}</div>`;
  };
  // an OTP box still empty, with the portal's own Resend button beside it
  const resendHint = root => {
    const otp = [...root.querySelectorAll('input')].find(el => visible(el) && /otp|one.?time/i.test(labelOf(el)) && !el.value);
    const btn = otp && [...root.querySelectorAll('button,a,input[type=submit]')].find(b => visible(b) && /resend/i.test(b.innerText || b.value || ''));
    return btn ? '<div style="margin-top:6px;color:#8FA3B2">No SMS after a minute? Press the portal\'s <b>Resend OTP</b> yourself and use only the newest code.</div>' : '';
  };
  // the internet went away mid-form: nothing is lost, and nothing is sent twice when it is back
  let offlineSince = 0;
  addEventListener('offline', () => {
    offlineSince = Date.now();
    say('<div id="solaraOffline" style="margin-top:6px;padding:8px;border-radius:7px;background:#3A2E12;color:#F2C879">' +
      '<b>The internet is off.</b> Nothing is lost: what is filled stays on this page. When it is back, Solara reads the page again and checks what the portal already has before anything is filled or marked again.</div>');
  });
  addEventListener('online', () => {
    if (!offlineSince) return;
    offlineSince = 0;
    recalled().then(rec => ask({ type: 'report', body: { customer_id: rec ? rec.cid : '', event: 'problem', kind: 'offline', page: location.host + location.pathname } }));
    safeScan();
  });

  // ---------- the two logins side by side ----------
  // The vendor and the customer login open in two tabs; what one finishes, the other is told.
  const APPROVE_STEPS = 'In the customer login: Action &rarr; Submit Agreement Details &rarr; Approve &rarr; tick the declaration ' +
    '&rarr; the customer reads you the SMS code &rarr; you press Verify &amp; Approve.';
  const here = location.host + '/' + location.pathname.split('/')[1];
  let handoff = null;
  const banner = () => handoff && handoff.from !== here && Date.now() - handoff.at < 30 * 60 * 1000 ?
    `<div id="solaraHandoff" style="margin-top:6px;padding:8px;border-radius:7px;background:#12303A;color:#BFE9D9">${esc(handoff.text)}</div>` : '';
  const tell = text => chrome.storage.local.set({ handoff: { text, from: here, at: Date.now() } }).catch(() => {});
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
      panel.querySelector('#solaraRetry').onclick = safeScan; return; }
    say(`<div id="solaraList" style="margin-top:4px">` + stepsHtml(r.data || {}, `Read ${list.rows.length} application(s). Nothing new for Solara.`) + '</div>');
    stepsWire(r.data || {}, list.rows.length);
  }
  // what reading a list changed in Solara, and the customer approvals that come next
  const stepsHtml = (d, nothing) =>
      ((d.updated || []).length ? `<b>Solara updated:</b>` + d.updated.map(u => `<div style="margin-top:3px">${esc(u.name)}: ${esc(u.what)}</div>`).join('')
        : nothing) +
      ((d.problems || []).length ? `<div style="margin-top:6px;color:#F2C879">` + d.problems.map(u => `${esc(u.name)}: ${esc(u.what)}`).join('<br>') + '</div>' : '') +
      ((d.unknown || []).length ? `<div style="margin-top:6px;color:#8FA3B2">Statuses Solara does not know yet (nothing changed): ${esc(d.unknown.join(', '))}</div>` : '') +
      (d.seen || []).filter(s => s.next && s.next.act === 'approve').map(s =>
        `<div style="margin-top:8px;padding:8px;border-radius:7px;background:#12303A"><b>${esc(s.name)}: the customer approves next</b>` +
        `<div style="margin-top:3px;color:#BFE9D9">${APPROVE_STEPS}</div>` +
        `<button data-approved="${esc(s.id)}" data-name="${esc(s.name)}" style="display:block;width:100%;margin-top:8px;padding:8px;border:0;border-radius:7px;cursor:pointer;font-weight:700;background:#24343F;color:#E8EEF2">I pressed Verify &amp; Approve: mark it approved</button></div>`).join('');
  function stepsWire(d, rows) {
    panel.querySelectorAll('[data-approved]').forEach(b => b.onclick = () => markApproved(b.dataset.approved, b.dataset.name, b));
    if ((d.updated || []).some(u => /approved/.test(u.what))) tell(d.updated.filter(u => /approved/.test(u.what)).map(u => u.name).join(', ') +
      ' approved the agreement on the portal. Installation can start.');
    // the customer login shows one customer: the approval dialog opened from here is theirs
    if (rows === 1 && (d.seen || []).length === 1)
      chrome.storage.local.set({ current: { cid: d.seen[0].id, at: Date.now(), picked: true } }).catch(() => {});
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

  // the radio questions on this page: [{question, radios}]
  function radioGroups(root) {
    const groups = new Map();
    for (const r of root.querySelectorAll('input[type=radio]')) {
      if (!visible(r) || r.disabled) continue;
      const k = r.name || r.closest('.fg,.form-group,fieldset,div')?.textContent;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(r);
    }
    return [...groups.values()].map(radios => {
      const box = radios[0].closest('.fg,.form-group,fieldset,mat-radio-group,[role=radiogroup],tr') || radios[0].parentElement.parentElement;
      return { radios, question: norm(box ? box.innerText : '') };
    });
  }
  const isYes = r => /^y(es)?$/i.test((r.value || '').trim()) || /^\s*yes\b/i.test(r.closest('label')?.innerText || r.nextSibling?.textContent || '');
  const isNo = r => /^no?$/i.test((r.value || '').trim()) || /^\s*no\b/i.test(r.closest('label')?.innerText || r.nextSibling?.textContent || '');

  // what the page is for, so the right customers and the right "mark done" button are offered
  function stepOf(root) {
    const t = (root.innerText || '').toLowerCase();
    if (/site feasibility report/.test(t)) return 'sfr';
    if (/submit solar rooftop installation|installation details/.test(t)) return 'installation';
    if (/dcr details|dcr verification/.test(t)) return 'dcr';
    if (/jansamarth|jan samarth/.test(t)) return 'loan';
    if (/upload agreement/.test(t)) return 'agreement_uploaded';
    return '';
  }

  // a copy of the page as the owner sees it, kept by Solara as the receipt; secrets blanked
  function snapshot() {
    const src = [...document.querySelectorAll('input,select,textarea')];
    const clone = document.documentElement.cloneNode(true);
    const dst = [...clone.querySelectorAll('input,select,textarea')];
    src.forEach((el, i) => {
      const d = dst[i]; if (!d) return;
      const secret = secretField(el);
      if (el.tagName === 'SELECT') [...d.options].forEach((o, j) => j === el.selectedIndex ? o.setAttribute('selected', '') : o.removeAttribute('selected'));
      else if (el.type === 'checkbox' || el.type === 'radio') el.checked ? d.setAttribute('checked', '') : d.removeAttribute('checked');
      else if (el.type === 'file') d.replaceWith(Object.assign(document.createElement('b'), { textContent: [...(el.files || [])].map(f => f.name).join(', ') || '(no file)' }));
      else if (el.tagName === 'TEXTAREA') d.textContent = secret ? '' : el.value;
      else d.setAttribute('value', secret ? '' : el.value);
    });
    clone.querySelectorAll('#solaraPanel,script,noscript,iframe').forEach(n => n.remove());
    let css = '';
    for (const sh of document.styleSheets) { try { css += [...sh.cssRules].map(r => r.cssText).join('\n'); } catch { /* another origin's stylesheet */ } }
    clone.querySelectorAll('link,style').forEach(n => n.remove());
    const head = clone.querySelector('head') || clone;
    head.insertAdjacentHTML('beforeend', `<style>${css.replace(/<\//g, '')}</style>`);
    return clone.outerHTML.slice(0, 2500000);
  }

  // ---------- portal lists: read each row's status (no clicks) ----------
  function statusLists(root) {
    const out = { pmsg: [], msedcl: [] };
    for (const table of root.querySelectorAll('table,[role=table],[role=grid]')) {
      const rows = [...table.querySelectorAll('tr,[role=row]')];
      const cells = r => [...r.querySelectorAll('th,td,[role=columnheader],[role=cell],[role=gridcell]')];
      const head = rows.find(r => r.querySelector('th,[role=columnheader]'));
      if (!head) continue;
      const h = cells(head).map(c => norm(c.innerText));
      const at = re => h.findIndex(x => re.test(x));
      const iApp = at(/application number/), iSt = at(/^status|workflow status/), iId = at(/application id/), iDoc = at(/document status/),
            iCon = at(/consumer number/);
      for (const r of rows) {
        if (r === head) continue;
        const c = cells(r);
        if (iApp >= 0 && iSt >= 0 && c[iSt]) {
          const app = (r.innerText.match(NP) || [])[0];
          if (app) out.pmsg.push({ ref: app, status: c[iSt].innerText.trim(), consumer_no: iCon >= 0 && c[iCon] ? c[iCon].innerText.trim() : '' });
        } else if (iId >= 0 && iDoc >= 0 && c[iDoc]) {
          out.msedcl.push({ ref: c[iId].innerText.trim(), status: c[iDoc].innerText.trim(), consumer_no: iCon >= 0 && c[iCon] ? c[iCon].innerText.trim() : '' });
        }
      }
    }
    return out;
  }

  let sentLists = '';
  async function statusMode(lists) {
    const key = JSON.stringify(lists);
    if (key === sentLists) return;
    sentLists = key;
    const parts = [];
    let steps = null;
    for (const portal of ['pmsg', 'msedcl']) {
      if (!lists[portal].length) continue;
      const r = await ask({ type: 'status', body: { portal, rows: lists[portal] } });
      if (!r || !r.ok) { say(`<span style="color:#F2A6A0">${esc((r && r.error) || 'No answer from Solara.')}</span>`); return; }
      parts.push(`Read ${lists[portal].length} status${lists[portal].length > 1 ? 'es' : ''}: <b>${r.data.matched.length}</b> updated in Solara` +
        (r.data.unknown.length ? `, <span style="color:#F2C879">${r.data.unknown.length} not in Solara</span>` : ''));
      if (r.data.steps) steps = r.data.steps;
    }
    panel.dataset.statuses = String(lists.pmsg.length + lists.msedcl.length);
    say(`<div style="margin-top:6px">${parts.join('<br>')}</div>` + (steps ? `<div id="solaraList" style="margin-top:6px">${stepsHtml(steps, '')}</div>` : '') +
      `<div style="margin-top:6px;color:#8FA3B2;font-size:11px">Read only. Nothing on the portal was clicked.</div>`);
    if (steps) stepsWire(steps, lists.pmsg.length);
  }

  // ---------- the panel ----------
  const panel = document.createElement('div');
  panel.id = 'solaraPanel';
  panel.style.cssText = 'position:fixed;right:14px;bottom:14px;z-index:2147483647;width:310px;max-height:72vh;' +
    'overflow:auto;background:#0F1B24;color:#E8EEF2;font:13px/1.4 system-ui,Arial,sans-serif;' +
    'border-radius:10px;box-shadow:0 8px 28px rgba(0,0,0,.35);padding:12px';
  const btn = (id, text, primary) => `<button id="${id}" style="display:block;width:100%;margin-top:8px;padding:8px;border:0;border-radius:7px;` +
    `cursor:pointer;font-weight:700;${primary ? 'background:#2BB673;color:#04150D' : 'background:#24343F;color:#E8EEF2'}">${text}</button>`;
  const say = html => { if (offlineSince && !/solaraOffline/.test(html)) return;
    const root = scope();
    html = trouble(root) + resendHint(root) + html;
    panel.innerHTML = `<div style="display:flex;justify-content:space-between;gap:10px"><b style="color:#5FD3A8">Solara co-pilot</b>` +
    `<span><span id="solaraMin" style="cursor:pointer;color:#8FA3B2;margin-right:10px" title="Make smaller or bigger">&#8211;</span>` +
    `<span id="solaraRescan" style="cursor:pointer;color:#8FA3B2" title="Read this page again">&#8635;</span></span></div>` +
    `<div id="solaraBody">${banner()}${html}` +
    `<div style="margin-top:8px;text-align:right"><a href="#" id="solaraLayout" style="color:#8FA3B2;font-size:11px">Send this page's layout to Solara</a></div></div>`; dodge(); };
  const note = (html, color) => `<div style="margin-top:6px;color:${color || '#8FA3B2'}">${html}</div>`;
  document.body.appendChild(panel);
  let minimised = false;
  panel.addEventListener('click', e => {
    if (e.target.id === 'solaraRescan') safeScan();
    if (e.target.id === 'solaraMin') { minimised = !minimised; dodge(); }
    if (e.target.id === 'solaraLayout') { e.preventDefault(); sendLayout(e.target); }
  });
  // the portal's own buttons stay reachable: the panel moves to the other corner, or folds to its
  // title bar, when it would cover a Submit, Save & Next, Upload or Approve button
  const portalButtons = () => [...document.querySelectorAll('button,input[type=submit],input[type=button],input[type=checkbox],a')].filter(b =>
    !panel.contains(b) && visible(b) && (b.type === 'checkbox' || /submit|next|save|upload|approve|final|login|search/i.test(b.innerText || b.value || '')));
  const CORNERS = [['right', 'bottom'], ['left', 'bottom'], ['right', 'top'], ['left', 'top']];
  function dodge() {
    const body = panel.querySelector('#solaraBody');
    const keep = portalButtons().map(b => b.getBoundingClientRect());
    const covers = () => { const p = panel.getBoundingClientRect();
      return keep.some(r => r.left < p.right && r.right > p.left && r.top < p.bottom && r.bottom > p.top); };
    const at = ([x, y]) => Object.assign(panel.style, { left: x === 'left' ? '14px' : 'auto', right: x === 'right' ? '14px' : 'auto',
      top: y === 'top' ? '14px' : 'auto', bottom: y === 'bottom' ? '14px' : 'auto' });
    if (body) body.style.display = minimised ? 'none' : '';
    for (const c of CORNERS) { at(c); if (!covers()) return; }
    if (body) body.style.display = 'none'; // folded to its title bar; press – to open it again
    for (const c of CORNERS) { at(c); if (!covers()) return; }
  }
  addEventListener('scroll', () => dodge(), { passive: true });
  addEventListener('resize', () => dodge());

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
  // the application number nearest to what the owner last clicked (a row's Action menu): the
  // dialog it opens often does not repeat whose it is
  document.addEventListener('click', e => {
    if (panel.contains(e.target)) return;
    for (let p = e.target; p && p !== document.body; p = p.parentElement) {
      const m = new Set(noExamples((p.innerText || '').slice(0, 4000)).match(NP) || []);
      if (m.size === 1) { chrome.storage.local.set({ clicked: { app: [...m][0], at: Date.now(), site: site() } }); return; }
      if (m.size > 1) return;
    }
  }, true);
  const site = () => location.host + '/' + location.pathname.split('/')[1];
  const clicked = async () => { const { clicked: c, current } = await chrome.storage.local.get(['clicked', 'current']);
    return c && c.site === site() && Date.now() - c.at < 10 * 60 * 1000 && !(current && current.at > c.at) ? c.app : ''; };

  let scanId = 0, busy = false, sig = '';
  const signature = () => { const r = scope(); return location.href + '|' + (r === document.body ? 'page' : 'dialog') + '|' +
    [...r.querySelectorAll('input,select,textarea')].filter(visible).length + '|' +
    ((r.innerText || '').match(/submitted successfully|generated successfully|reference no|not available in your stock/i) || [''])[0] + '|' +
    (TROUBLE.find(([, re]) => re.test(r.innerText || '')) || [''])[0]; };  // a portal message alone (wrong OTP, logged out) is a new page

  // a problem on a page the co-pilot has not seen before is shown, never swallowed
  const safeScan = () => scan().catch(err => { busy = false; panel.dataset.err = String(err && err.stack || err).slice(0, 400);
    say(note(`Co-pilot could not read this page: ${esc(err && err.message || err)}. Press &#8635; to try again.`, '#F2A6A0')); });
  async function scan() {
    const my = ++scanId;
    panel.dataset.scans = String(my);
    sig = signature();
    const root = scope();
    if (/want the vendor to fill/i.test(root.innerText)) {
      say('<div style="margin-top:4px"><b>Answer No.</b> You fill it here yourself; the Solara panel fills the form on the next page.</div>');
      return;
    }
    const track = root === document.body ? trackerRows() : [];
    if (track.length) return listMode({ status: true, rows: track });
    if (root === document.body) {
      const lists = statusLists(root);
      if (lists.pmsg.length || lists.msedcl.length) return statusMode(lists);
    }
    const step = stepOf(root);
    const consumer = labelled('Consumer Number', root, /^\d{9,14}$/) || one(/\b\d{12}\b/g, root);
    let app = labelled('Application Number', root, /^NP-/) || one(NP, root);
    const fields = [...root.querySelectorAll('input,select,textarea')].filter(el => visible(el) &&
      !['hidden', 'checkbox', 'submit', 'button', 'password'].includes(el.type));
    const result = /generated successfully|reference no|in-principle/i.test(root.innerText);
    // Vendor Consent (no status column): waiting for the owner; a plain list with a status: read it
    const list = !consumer && !app && root === document.body &&
      [...document.querySelectorAll('table')].filter(t => t.rows.length > 1).map(listRows).find(x => x && x.rows.length);
    if (list) return listMode(list);
    let cid = '';
    if (!consumer && !app) {
      app = await clicked();
      if (!app) {
        if (!fields.length && !result) { say('<span style="color:#8FA3B2">Nothing to do on this page.</span>'); return; }
        const rec = await recalled();
        if (!rec) return pick(step);
        cid = rec.cid;
      }
    }
    say('Looking up this customer…');
    const r = await ask({ type: 'lookup', consumer_no: consumer, app_no: app, cid });
    if (my !== scanId) return; // a newer scan took over
    if (!r || !r.ok) { say(`<span style="color:#F2A6A0">${esc((r && r.error) || 'No answer from Solara.')}</span>` + (fields.length ? btn('solaraPick', 'Choose the customer') : '') + btn('solaraRetry', 'Try again'));
      const p = panel.querySelector('#solaraPick'); if (p) p.onclick = () => pick(step);
      panel.querySelector('#solaraRetry').onclick = safeScan; return; }
    const c = r.data;
    remember(c);
    const head = `<div style="margin-top:4px"><b>${esc(c.name)}</b> &middot; ${esc(c.customer_id)} ` +
      `<a href="#" id="solaraChange" style="color:#8FA3B2;font-size:11px">not this customer?</a></div>` +
      (c.paused ? note(`Paused by ${esc(c.paused.by)}: ${esc(c.paused.reason)}`, '#F2C879') : '');
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
    let saved = '';
    // a page showing the application number this customer was just given: save it
    if (!c.application_no && app && consumer === (c.values.consumer_no || '') || (!c.application_no && app && !consumer && cid)) {
      const rep = await ask({ type: 'report', body: { customer_id: c.customer_id, event: 'app_no', app_no: app } });
      // this registration is finished: the next blank form must ask who it is for, never assume
      if (rep && rep.ok) { c.application_no = app; chrome.storage.local.remove('current'); }
      saved = rep && rep.ok ? note(`Application number <b>${esc(app)}</b> saved in Solara.`, '#5FD3A8')
        : note(`Application number <b>${esc(app)}</b> was NOT saved: ${esc((rep && rep.error) || 'no answer from Solara')}. Type it into Solara yourself.`, '#F2A6A0');
    }
    saved += await results(c, root);
    if (my !== scanId) return;
    formMode(c, root, head, saved, step);
  }

  // numbers and errors a portal shows after a submit
  async function results(c, root) {
    const t = root.innerText;
    const cert = labelled('Certificate Number', root, /^[A-Z0-9][A-Z0-9/-]{5,}$/) ||
      ((t.match(/certificate (?:no|number)\.?\s*[:.]?\s*([A-Z0-9][A-Z0-9/-]{5,})/i) || [])[1] || '');
    if (cert && /dcr|generated/i.test(t) && (c.values.dcr_cert_no || '') !== cert.toUpperCase()) {
      const rep = await ask({ type: 'report', body: { customer_id: c.customer_id, event: 'dcr_cert', ref: cert, receipt: snapshot(), page: location.href } });
      return rep && rep.ok ? note(`DCR certificate <b>${esc(cert)}</b> saved in Solara, with the page as the receipt.`, '#5FD3A8')
        : note(esc((rep && rep.error) || 'Could not save the certificate number'), '#F2A6A0');
    }
    if (/not available in your stock|not transferred|not credited|insufficient stock/i.test(t)) {
      await ask({ type: 'report', body: { customer_id: c.customer_id, event: 'dealer_wait', message: t.match(/[^\n]*(stock|transferred|credited)[^\n]*/i)?.[0] } });
      return note('The dealer has not transferred these panels yet. Solara now shows this customer as <b>waiting for the dealer</b>.', '#F2C879');
    }
    const ref = (t.match(/reference (?:no|number)\.?\s*[:.]?\s*([A-Z0-9][A-Z0-9/-]{5,})/i) || [])[1];
    if (ref && /loan|jansamarth|in-principle/i.test(t)) {
      panel.dataset.loanRef = ref;
      return note(`Loan reference <b>${esc(ref)}</b>.`) + btn('solaraLoan', 'Save the reference and the approval letter', true);
    }
    return '';
  }

  function wireChange() { const a = panel.querySelector('#solaraChange'); if (a) a.onclick = e => { e.preventDefault(); pick(stepOf(scope())); }; }

  async function pick(step) {
    const r = await ask({ type: 'pending', step });
    if (!r || !r.ok) { say(`<span style="color:#F2A6A0">${esc((r && r.error) || 'No answer from Solara.')}</span>`); return; }
    if (!r.data.length) { say(step ? 'No customer in Solara is at this step.' : 'No customer in Solara is waiting to be registered.'); return; }
    say('<div style="margin-top:4px">Fill this page for:</div>' + r.data.map(x =>
      `<button data-pick="${esc(x.id)}" style="display:block;width:100%;text-align:left;margin-top:6px;padding:7px 9px;border:0;border-radius:7px;background:#24343F;color:#E8EEF2;cursor:pointer">` +
      `<b>${esc(x.name)}</b><br><span style="color:#8FA3B2;font-size:11px">${esc(x.id)} &middot; consumer ${esc(x.consumer_no)}</span></button>`).join(''));
    panel.querySelectorAll('[data-pick]').forEach(b => b.onclick = async () => {
      await chrome.storage.local.set({ current: { cid: b.dataset.pick, at: Date.now(), picked: true }, clicked: null }); safeScan(); });
  }

  function msedclAttach(c, rows, head) {
    const have = new Set(c.files.map(f => f.key));
    const ready = rows.filter(x => have.has(x.key));
    say(head + `${ready.length} of ${rows.length} documents ready in Solara.` +
      (c.not_ready.length ? `<br><span style="color:#F2C879">Not ready: ${c.not_ready.map(n => esc(n.title)).join(', ')}</span>` : '') +
      btn('solaraAttach', `Attach ${ready.length} file(s)`, true));
    wireChange();
    panel.querySelector('#solaraAttach').onclick = async () => {
      busy = true;
      let n = 0;
      for (const { input, key } of ready) n += await attach(input, { type: 'file', cid: c.customer_id, key }) ? 1 : 0;
      panel.dataset.attached = String(n);
      say(head + `<b>${n} file(s) attached.</b> Check each row, then press the portal's Upload button yourself.`);
      wireChange();
      ask({ type: 'report', body: { customer_id: c.customer_id, portal: 'msedcl', attached: n } });
      sig = signature(); busy = false;
    };
  }

  function formMode(c, root, head, saved, step, opened) {
    const page = norm(root.innerText);
    const els = [...root.querySelectorAll('input,select,textarea')].filter(el => visible(el) && !el.readOnly && !el.disabled &&
      !['hidden', 'checkbox', 'radio', 'submit', 'button', 'password', 'file'].includes(el.type) && !humanOnly(el));
    // custom dropdowns are picked by their visible option text; one that cannot be matched is named for the owner
    const customs = [...root.querySelectorAll(CUSTOM)].filter(el => visible(el) && !el.closest('select') &&
      !el.querySelector('input:not([type=hidden]),select')).map(el => {
        const key = ruleFor(labelOf(el), page); return key ? { el, key, label: labelOf(el).split(' | ')[0] || key } : null; })
      .filter(x => x && c.values[x.key] != null);
    const issues = c.issues || [];
    const issueHtml = (issues.length ? `<div style="margin-top:8px;padding:8px;border-radius:7px;background:#3A2E12;color:#F2C879">` +
      `<b>${issues.length} to sort out in Solara first</b>` + issues.map(i => `<div style="margin-top:3px"><b>${esc(i.kind)}</b>: ${esc(i.field)} &mdash; ${esc(i.message)}</div>`).join('') + '</div>' : '') +
      (c.build_error ? `<div style="margin-top:6px;color:#F2A6A0">${esc(c.build_error)}</div>` : '');
    const seen = new Map(); // a repeating table (one row per make): fill its first row only
    const plan = els.map(el => {
      let key = ruleFor(labelOf(el), page);
      if (key === 'only_option' && el.tagName !== 'SELECT') key = undefined;  // a typed Branch Name is left for the person
      const tb = tableOf(el);
      if (tb && key) {
        const s = seen.get(tb.table) || new Set(); seen.set(tb.table, s);
        if (s.has(key) && key !== 'module_serials') return { el, key, extra: true };
        s.add(key);
      }
      return { el, key };
    });
    const valueOf = key => key === 'only_option' ? '__only__' : c.values[key];
    const fillable = plan.filter(p => !p.extra && p.key && valueOf(p.key) != null);
    const questions = radioGroups(root).map(g => ({ ...g, key: (YESNO.find(([re]) => re.test(g.question)) || [])[1] }));
    const answerable = questions.filter(q => q.key && /^(yes|no)$/i.test(c.values[q.key] || ''));
    const hasSerialBox = plan.some(p => p.key === 'module_serials' && !p.extra);
    const files = [...root.querySelectorAll('input[type=file]')].filter(el => !el.disabled).map(el => {
      const lab = labelOf(el) + ' ' + norm((el.closest('tr,.upr,.fg,.form-group') || el.parentElement).innerText);
      const hit = FILES.find(([re]) => re.test(lab));
      return hit && !(hit[2] === 'xlsx' && hasSerialBox) && { el, kind: hit[1], from: hit[2] };
    }).filter(Boolean);
    // "+ Add Serial Number" opens a row's serial box: tables whose first row's box is still closed
    const inert = b => b.tagName === 'BUTTON' ? b.type === 'button' : /^(#|javascript:)?$/.test(b.getAttribute('href') || '');
    const addSerial = t => [...t.querySelectorAll('button,a')].find(b => visible(b) && /add serial/i.test(b.innerText));
    const shut = [...root.querySelectorAll('table')].filter(t => addSerial(t) &&
      ![...t.querySelectorAll('textarea,input')].some(x => visible(x) && /serial/.test(labelOf(x))));
    const closedSerial = shut.filter(t => inert(addSerial(t)));
    const pressYourself = shut.length > closedSerial.length; // this portal's button might submit: the owner presses it
    const ready = new Set(c.files.map(f => f.key));
    // the customer's OTP (registration, Aadhaar) goes on Today as a call; the owner's own login OTP does not
    const ownLogin = root.querySelector('input[type=password]') || els.some(el => /user ?id|username|register email|login/.test(labelOf(el)));
    // all inputs: the OTP box itself is kept out of els (the co-pilot never fills it)
    const otpBox = !ownLogin && [...root.querySelectorAll('input')].find(el => visible(el) && /otp/.test(labelOf(el)) && !el.value);
    if (otpBox) ask({ type: 'report', body: { customer_id: c.customer_id, event: 'otp_waiting', page: location.host + location.pathname } });
    const ap = step && c.approvals && c.approvals[step];
    const apNote = ap ? (ap.current ? note(`&#10003; Reviewed and approved by ${esc(ap.by)}`, '#5FD3A8')
      : note(`Changed since ${esc(ap.by)} approved it. Review it again in Solara.`, '#F2C879')) : '';
    const markable = MARK[step] && (step !== 'installation' || /final submit|submitted successfully/i.test(root.innerText));
    const agreementBox = step === 'agreement_uploaded' || [...root.querySelectorAll('input[type=file]')].some(el => /agreement/.test(labelOf(el)));
    // the customer login's Submit Agreement Details dialog: the OTP and Verify & Approve are the person's
    const approveBox = !agreementBox && /verify\s*&\s*approve|submit agreement details/i.test(root.innerText);
    // a blank form says nothing about whose it is: the button names the customer, so a carried-over
    // customer is seen before anything is filled
    const pickable = customs.filter(x => isEmpty(x.el));
    const n = fillable.length + answerable.length + pickable.length, first = esc((c.name || '').split(' ')[0]);
    const filedAlready = markable && (c.done || {})[step];
    say(head + saved + apNote + issueHtml +
      (filedAlready ? note(`<b>Solara already has this filed.</b> Check My Application before filling it again; fill again only if the portal sent it back.`, '#F2C879') : '') +
      (n || files.length || closedSerial.length ? btn('solaraFill', (filedAlready ? 'Fill again anyway: ' : issues.length ? 'Fill anyway: ' : 'Fill ') + `${n} field(s)${first ? ' for ' + first : ''}` +
      (files.length ? ` and attach ${files.length} file(s)` : ''), !issues.length && !filedAlready) : note('No field here that Solara knows.')) +
      (agreementBox && (c.done || {}).customer_approved ? note('The customer already approved this agreement. A new upload sends it back to them to approve again.', '#F2A6A0') : '') +
      (agreementBox && c.agreement_draft ? note('This agreement is a DRAFT format; the client has not approved the wording yet.', '#F2C879') : '') +
      (markable && !(c.done || {})[step] ? btn(step === 'agreement_uploaded' ? 'solaraMarkUploaded' : 'solaraMark', MARK[step]) : '') +
      (!markable && agreementBox && !(c.done || {}).agreement_uploaded ? btn('solaraMarkUploaded', MARK.agreement_uploaded) : '') +
      (markable && (c.done || {})[step] ? note('&#10003; Solara has this step as filed.', '#5FD3A8') : '') +
      (approveBox ? `<div style="margin-top:8px;color:#BFE9D9">${APPROVE_STEPS}</div>` + btn('solaraMarkApproved', 'I pressed Verify &amp; Approve: mark it approved') : '') +
      `<details style="margin-top:8px"><summary style="cursor:pointer;color:#8FA3B2">Copy a value</summary>` +
      c.fields.map((f, i) => `<div style="display:flex;gap:6px;align-items:center;padding:3px 0;border-top:1px solid #23323E">` +
        `<div style="flex:1;min-width:0"><div style="color:#8FA3B2;font-size:11px">${esc(f.label)}</div><div style="word-break:break-all">${esc(f.value)}</div></div>` +
        `<button data-copy="${i}" style="border:0;border-radius:5px;padding:4px 8px;cursor:pointer">Copy</button></div>`).join('') + '</details>');
    wireChange();
    panel.querySelectorAll('[data-copy]').forEach(b => b.onclick = () =>
      navigator.clipboard.writeText(c.fields[+b.dataset.copy].value).then(() => { b.textContent = 'Copied'; }));
    const mark = panel.querySelector('#solaraMark,#solaraMarkUploaded');
    if (mark) mark.onclick = async () => {
      mark.disabled = true; mark.textContent = 'Saving the receipt…';
      const up = mark.id === 'solaraMarkUploaded';
      const body = up ? { event: 'agreement_uploaded' } : { event: 'filed', step };
      const rep = await ask({ type: 'report', body: { customer_id: c.customer_id, ...body, receipt: snapshot(), page: location.href } });
      mark.textContent = rep && rep.ok ? (up ? 'Saved in Solara: agreement uploaded, with the page as the receipt'
        : 'Saved in Solara, with the page as the receipt') : 'NOT saved: ' + ((rep && rep.error) || 'no answer from Solara');
      panel.dataset.marked = rep && rep.ok ? (up ? 'agreement_uploaded' : step) : '';
      if (up && rep && rep.ok) tell(`${c.name}'s agreement is uploaded. Now the customer approves it: ${APPROVE_STEPS.replace(/&rarr;/g, '>').replace(/&amp;/g, '&')}`);
    };
    const loan = panel.querySelector('#solaraLoan');
    if (loan) loan.onclick = async () => {
      loan.disabled = true;
      const a = [...root.querySelectorAll('a')].find(x => /approval letter|in-principle|sanction/i.test(x.innerText));
      let letter = '';
      if (a) try { // same site as the page, with the customer's session: the bank's PDF itself
        const buf = new Uint8Array(await (await fetch(a.href, { credentials: 'include' })).arrayBuffer());
        let s = ''; for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode(...buf.subarray(i, i + 0x8000));
        letter = btoa(s);
      } catch { /* the letter stays on the portal; the reference is still saved */ }
      const rep = await ask({ type: 'report', body: { customer_id: c.customer_id, event: 'loan_ref', ref: panel.dataset.loanRef, letter, receipt: snapshot(), page: location.href } });
      loan.textContent = rep && rep.ok ? `Saved: reference${letter ? ' and approval letter' : ''}` : (rep && rep.error) || 'Could not save';
    };
    const appr = panel.querySelector('#solaraMarkApproved');
    if (appr) appr.onclick = () => markApproved(c.customer_id, c.name, appr);
    const fill = panel.querySelector('#solaraFill');
    if (!fill) return;
    fill.onclick = () => doFill().catch(err => { // never leave the owner with a button that silently did nothing
      busy = false;
      const at = panel.querySelector('#solaraFill,#solaraFilled');
      if (at) at.outerHTML = note(`Could not finish filling: ${esc(err.message || err)}. Press &#8635; and try again, or type the rest.`, '#F2A6A0');
      ask({ type: 'report', body: { customer_id: c.customer_id, page: location.host + location.pathname, left: ['co-pilot error: ' + String(err.message || err).slice(0, 50)] } });
    });
    const doFill = async () => {
      panel.dataset.fill = 'start';
      busy = true;
      if (closedSerial.length && !opened) { // opens an input box only; nothing is submitted
        closedSerial.forEach(t => addSerial(t).click());
        await new Promise(r => setTimeout(r, 400));
        formMode(c, scope(), head, saved, step, true);
        busy = false;
        const again = panel.querySelector('#solaraFill');
        if (again) again.click();
        return;
      }
      panel.dataset.fill = 'fields';
      let filled = 0, kept = 0, attached = 0;
      const left = pressYourself ? ['press + Add Serial Number, then Fill again'] : [], done = [], failed = [];
      // dropdowns first, top to bottom: a later box (District) often waits for the one above it (State)
      for (const { el, key } of customs) {
        const label = shown(el);
        if (!isEmpty(el)) { kept += 1; continue; }   // someone already chose; theirs stays
        if (await pickCustom(el, c.values[key])) { filled += 1; done.push(label); }
        else left.push(`${label} (pick “${c.values[key]}” yourself)`);
      }
      const serialEls = plan.filter(p => p.key === 'module_serials' && p.el.tagName !== 'TEXTAREA');
      const list = (c.values.module_serials || '').split('\n').filter(Boolean);
      for (const { el, key, extra } of plan) {
        const label = shown(el);
        if (extra || key === null) continue; // OTP, CAPTCHA: the person types these
        const v = key === 'module_serials' && serialEls.length > 1 ? list[serialEls.findIndex(p => p.el === el)] : valueOf(key);
        if (!key || v == null) { if (!el.value && key !== 'only_option') left.push(label); continue; }
        const chosen = el.tagName === 'SELECT' ? el.value !== '' && !/^\s*(select|--|choose)/i.test(el.selectedOptions[0]?.text || '')
          : el.value && !zeroish(el.value);
        if (chosen || el.dataset.solaraHuman) { kept += 1; continue; } // never overwrite what a person typed or picked
        // the page refused the value when the box is empty again afterwards
        if (setVal(el, v) && (el.tagName === 'SELECT' || el.value !== '')) { filled += 1; done.push(label); }
        else if (key !== 'only_option') { left.push(label); failed.push(label); }
      }
      for (const q of questions) {
        if (q.radios.some(r => r.checked)) { kept += q.key ? 1 : 0; continue; }
        const want = q.key && c.values[q.key];
        const r = want && q.radios.find(x => /^yes$/i.test(want) ? isYes(x) : isNo(x));
        if (r) { r.click(); r.dispatchEvent(new Event('change', { bubbles: true })); filled += 1; }
        else left.push(q.question.slice(0, 60));
      }
      // values Solara worked out rather than read (bank name from the IFSC, account type): the owner checks them
      const checkNames = plan.filter(p => !p.extra && (c.derived || []).includes(p.key)).map(p => shown(p.el)).filter(l => done.includes(l));
      panel.dataset.fill = 'files';
      for (const { el, kind, from } of files) {
        if (from === 'file' && !ready.has(kind)) { left.push(kind === 'agreement' ? 'agreement (not signed yet)' : `${kind} (not made yet)`); continue; }
        if (el.files && el.files.length) { kept += 1; continue; }   // a file you chose stays
        const ok = from === 'file' ? await attach(el, { type: 'file', cid: c.customer_id, key: kind })
          : from === 'xlsx' ? await attach(el, { type: 'xlsx', cid: c.customer_id })
          : c.docs.includes(kind) && await attach(el, { type: 'doc', cid: c.customer_id, kind });
        if (ok) attached += 1; else left.push(kind.replace('_', ' ') + (from !== 'doc' || c.docs.includes(kind) ? ' (could not be fetched from Solara)' : ' (not on file)'));
      }
      panel.dataset.filled = String(filled);
      panel.dataset.attached = String(attached);
      if (!fill.isConnected) { busy = false; return; } // the page was read again meanwhile; the new panel stands
      fill.outerHTML = `<div id="solaraFilled" style="margin-top:8px"><b>Filled ${filled}${attached ? `, attached ${attached}` : ''}.</b>` +
        (kept ? ` Kept ${kept} you had typed.` : '') +
        (failed.length ? `<br><span style="color:#F2A6A0">The page did not accept: ${esc(failed.join(', '))}</span>` : '') +
        (done.length ? `<div style="margin-top:4px;color:#8FA3B2">Filled: ${esc(done.join(', '))}</div>` : '') +
        (checkNames.length ? `<div style="margin-top:4px;color:#F2C879">Check these, Solara worked them out: ${esc(checkNames.join(', '))}</div>` : '') +
        (left.length ? `<br><span style="color:#F2C879">Left for you: ${esc([...new Set(left)].join(', '))}</span>` : '') +
        '<br>Check the page, then press the portal\'s button yourself.</div>';
      ask({ type: 'report', body: { customer_id: c.customer_id, portal: location.host, attached: filled + attached,
        page: location.host + location.pathname, left: [...new Set(left)] } }).then(r => {
        if (r && !r.ok) panel.querySelector('#solaraFilled')?.insertAdjacentHTML('beforeend',
          `<br><span style="color:#F2A6A0">Solara could not be told what was filled: ${esc(r.error)}</span>`); });
      sig = signature(); busy = false;
    };
  }

  chrome.storage.local.get('handoff').then(x => { handoff = x.handoff || null; }, () => {}).finally(safeScan);
  // the other login's panel said something (an upload, an approval): show it here at once
  chrome.storage.onChanged.addListener((ch, area) => {
    if (area !== 'local' || !ch.handoff) return;
    handoff = ch.handoff.newValue || null;
    panel.querySelector('#solaraHandoff')?.remove();
    panel.querySelector('#solaraBody')?.insertAdjacentHTML('afterbegin', banner());
  });
  // single-page portals change screens without reloading, and wizard steps and dialogs appear in
  // place: read the page again whenever what is on it changes
  setInterval(() => { if (busy) return; const s = signature(); if (s !== sig) { sig = s; setTimeout(safeScan, 300); } }, 800);
})();
