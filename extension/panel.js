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
    [/roof has enough load|load bearing|roof ?load/, 'roof_load_ok'],
    [/shadow ?free roof area|roof area/, 'roof_area'],
    [/shadow ?free roof|availability of shadow/, 'shadow_free'],
    [/permissible/, 'permissible_kw'],
    [/vendor has visited|visited the installation site|vendor ?visited/, 'site_visited'],
    [/name of vendor employee|employee visited|vendor employee/, 'visitor_name'],
    [/user ?id|username|register email|login/, null],         // the vendor's own login, never the customer's
    [/employee|contact person|contact number/, null],         // the vendor's site staff, not the customer
    [/application (no|number)/, 'application_no'],
    [/consumer (account )?(no|number)|ca number|consumer id/, 'consumer_no'],
    [/mobile|phone/, 'mobile'],
    [/e ?mail/, 'email'],
    [/type of location|location type/, 'location_type'],   // Urban / Rural
    [/urban local ?bod/, 'ulb'],
    [/development block|taluka/, 'taluka'],
    [/panchayat/, 'panchayat'],
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
  const FILES = [[/quotation|quote/, 'quotation'], [/agreement/, 'agreement'], [/bill/, 'bill'], [/aadhaar|identity/, 'aadhaar'],
                 [/passbook|bank|cheque/, 'passbook'], [/roof|site photo|pre ?installation/, 'roof']];

  // anything the person changed with their own keyboard or mouse is theirs: isTrusted is false for our events
  const touch = e => { if (e.isTrusted && e.target && e.target.dataset) e.target.dataset.solaraHuman = '1'; };
  ['input', 'change'].forEach(t => document.addEventListener(t, touch, true));
  // defence in depth beside RULES: whatever the label says, these are for the person only
  const HUMAN_ONLY = /otp|captcha|one-?time|passw|security ?code|verification/i;
  const isSearch = el => el.type === 'search' || /search|filter|find/i.test([el.id, el.name, el.getAttribute('aria-label'), el.placeholder, el.className].join(' ')) || !!el.closest('[role=search],.p-datatable-header,.dataTables_filter');
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
    el.name || labelOf(el)).replace(/[:*\s]+$/, '').replace(/^(please\s+)?(enter|select)\s+/i, '').trim().slice(0, 50);
  const has = v => v != null && String(v).trim() !== '';
  const ruleFor = label => {
    if (/contact number/i.test(label) && /site feasibility/i.test(scope().innerText || '')) return 'visitor_phone';   // the visiting employee's number, only inside that form
    const r = RULES.find(([re]) => re.test(label)); return r ? r[1] : undefined; };

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
  const ME = String(Math.random()); document.documentElement.dataset.solaraOwner = ME;
  const isOwner = () => document.documentElement.dataset.solaraOwner === ME;
  const sleep = ms => new Promise((r, no) => setTimeout(() => isOwner() ? r() : no(new Error('replaced by a newer copy')), ms));   // an older copy stops mid-run
  // how fast it works: instant = no animation, fast (default) = quick, smooth = slow and easy to follow
  const PACES = { instant: { char: 0, step: 30, settle: 300, poll: 40 }, fast: { char: 6, step: 110, settle: 650, poll: 60 }, smooth: { char: 28, step: 450, settle: 1800, poll: 150 } };
  const PACE = { ...PACES.fast };
  let MODE = 'auto';   // 'auto': fills everything by itself. 'manual': shows each value with a Fill button
  store.get({ mode: 'auto' }).then(v => { MODE = v.mode === 'manual' ? 'manual' : 'auto'; });
  store.get({ speed: 'fast' }).then(v => Object.assign(PACE, PACES[v.speed] || PACES.fast));
  try { chrome.storage.onChanged.addListener(ch => { if (ch.mode) MODE = ch.mode.newValue === 'manual' ? 'manual' : 'auto'; if (ch.speed) Object.assign(PACE, PACES[ch.speed.newValue] || PACES.fast); }); } catch (e) { /* skip */ }
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
    for (let i = 0; i < 40 && isLocked(box); i++) await sleep(PACE.poll * 2);   // waits for the field above it
    if (isLocked(box)) return false;
    // the list above may still be fading out (PrimeNG animates the close); its options must not be read as this one's
    for (let i = 0; i < 30 && [...document.querySelectorAll(OPTS)].some(visible); i++) await sleep(PACE.poll);
    box.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    let opts = [];
    for (let i = 0; i < 50 && !opts.length; i++) { await sleep(PACE.poll); opts = [...document.querySelectorAll(OPTS)].filter(visible); }
    lastCands = opts.map(optName).filter(n => n && !/^no (results|records|data)/i.test(n));
    if (mode === 'list') {   // only read the choices, then close the list again
      if ([...document.querySelectorAll(OPTS)].some(visible)) box.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      return lastCands;
    }
    let hit = opts.filter(o => optText(o) === want);
    if (hit.length !== 1) hit = opts.filter(o => optText(o).length > 3 && (optText(o).includes(want) || want.includes(optText(o))));
    if (hit.length > 1 && new Set(hit.map(optText)).size === 1) hit = [hit[0]];   // the same name listed twice (Pune, Pune): one choice, take the first
    if (hit.length !== 1) {   // none or several: close the list again and leave it to the owner
      if ([...document.querySelectorAll(OPTS)].some(visible)) box.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      return false;
    }
    const chosen = optText(hit[0]);
    hit[0].dispatchEvent(new MouseEvent('click', { bubbles: true }));
    for (let i = 0; i < 20 && !norm(box.innerText).includes(chosen); i++) await sleep(PACE.poll);
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
    if (!f || !f.ok) { attach.err = (f && f.error) || ''; return false; }
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
  store.get({ classic: false }).then(v => { panel.style.display = v.classic ? '' : 'none'; });
  panel.addEventListener('click', e => { if (e.target.id === 'solaraRescan') { pbDone = false; pbAsked = false; sessionStorage.removeItem('solaraPress:fetch'); if (startModal()) { startModalFlow(true); } else scan(); } if (e.target.id === 'solaraLayout') { e.preventDefault(); sendLayout(e.target); } });

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

  // ---------- the co-pilot toast (top centre) ----------
  const toastCss = document.createElement('style');
  toastCss.textContent = '@keyframes solaraPulse{0%,100%{box-shadow:0 0 0 0 rgba(43,182,115,.55)}50%{box-shadow:0 0 0 9px rgba(43,182,115,0)}}' +
    '@keyframes solaraSpin{to{transform:rotate(360deg)}}.solara-ring{outline:3px solid #2BB673!important;outline-offset:3px;animation:solaraPulse 1.2s ease-in-out infinite}';
  document.head.appendChild(toastCss);
  // The island. Collapsed it is a small pill that says what is happening; a click opens a bento grid with the
  // customer, the steps, the values being filled and the buttons (Fill, Fetch Details, Next, Retry).
  let toastEl, toastTimer, hiddenNow = true;
  const LAYOUT = { islandV: 'top', islandH: 'center', panelV: 'bottom', panelH: 'right', gap: 14 };
  const ISL = { fresh: false, phase: 'idle', open: false, kind: 'idle', msg: '', progress: null, cust: null, steps: [], tiles: [], pend: null, actions: {} };
  const FONT = '-apple-system,BlinkMacSystemFont,"SF Pro Display","SF Pro Text",Inter,"Segoe UI",system-ui,sans-serif';
  const islCss = document.createElement('style');
  islCss.textContent = `
  #solaraToast{font-family:${FONT};-webkit-font-smoothing:antialiased;color:#F5F5F7;background:rgba(22,22,24,.82);backdrop-filter:blur(30px) saturate(180%);-webkit-backdrop-filter:blur(30px) saturate(180%);
    border:1px solid rgba(255,255,255,.12);box-shadow:0 22px 60px -18px rgba(0,0,0,.65),0 2px 6px rgba(0,0,0,.25);cursor:pointer;user-select:none}
  #solaraToast *{box-sizing:border-box}
  #solaraToast .si-head{display:flex;align-items:center;gap:10px}
  #solaraToast .si-msg{flex:1;font-weight:600;letter-spacing:-.01em}
  #solaraToast .si-chev{opacity:.55;transition:transform .35s cubic-bezier(.32,.72,0,1);font-size:12px}
  #solaraToast.open .si-chev{transform:rotate(180deg)}
  #solaraToast .si-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px;cursor:default}
  #solaraToast .si-tile{background:rgba(255,255,255,.07);border-radius:18px;padding:12px 14px;min-width:0}
  #solaraToast .fresh .si-tile{animation:siIn .5s cubic-bezier(.32,.72,0,1) both;animation-delay:calc(var(--i,0) * 45ms)}
  #solaraToast .si-2{grid-column:span 2}
  #solaraToast .si-k{font-size:11px;font-weight:500;color:rgba(245,245,247,.55);letter-spacing:.02em;text-transform:uppercase}
  #solaraToast .si-v{font-size:15px;font-weight:600;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  #solaraToast .si-cust{display:flex;align-items:center;gap:12px}
  #solaraToast .si-av{width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,#0A84FF,#5E5CE6);display:grid;place-items:center;font-weight:700;font-size:16px;flex:0 0 auto}
  #solaraToast .si-steps{display:flex;flex-wrap:wrap;gap:6px}
  #solaraToast .si-step{display:flex;align-items:center;gap:6px;padding:5px 10px;border-radius:99px;background:rgba(255,255,255,.08);font-size:12px;font-weight:500;color:rgba(245,245,247,.7);transition:all .3s}
  #solaraToast .si-step.doing{background:rgba(10,132,255,.25);color:#fff}
  #solaraToast .si-step.done{background:rgba(48,209,88,.2);color:#7CE8A0}
  #solaraToast .si-step.fail{background:rgba(255,69,58,.22);color:#FF8A80}
  #solaraToast .si-dot{width:8px;height:8px;border-radius:50%;background:rgba(255,255,255,.35);flex:0 0 auto}
  #solaraToast .doing .si-dot{background:#0A84FF;animation:siPulse 1s infinite}
  #solaraToast .done .si-dot{background:#30D158}
  #solaraToast .fail .si-dot{background:#FF453A}
  #solaraToast .si-tile.ok .si-v{color:#7CE8A0}
  #solaraToast .si-tile.warn .si-v{color:#FFB84D}
  #solaraToast .si-tile.doing .si-v{color:#64B5FF}
  #solaraToast .si-act{display:flex;gap:8px;flex-wrap:wrap}
  #solaraToast .si-btn{border:0;border-radius:99px;padding:9px 16px;font:600 13px ${FONT};cursor:pointer;background:rgba(255,255,255,.12);color:#F5F5F7;transition:transform .15s,background .2s}
  #solaraToast .si-btn:hover{background:rgba(255,255,255,.2)}
  #solaraToast .si-btn:active{transform:scale(.96)}
  #solaraToast .si-btn.pri{background:#0A84FF;color:#fff}
  #solaraToast .si-btn.pri:hover{background:#2B96FF}
  #solaraToast .si-btn.ok{background:#30D158;color:#06210F}
  #solaraToast .si-btn[disabled]{opacity:.4;cursor:not-allowed}
  #solaraToast .si-link{background:none;border:0;color:#64B5FF;font:500 12px ${FONT};cursor:pointer;padding:0}
  #solaraToast .si-pick{display:flex;align-items:center;gap:10px;width:100%;border:0;background:rgba(255,255,255,.07);color:#F5F5F7;border-radius:14px;padding:10px 12px;margin-top:6px;cursor:pointer;text-align:left;font:500 13px ${FONT}}
  #solaraToast .si-pick:hover{background:rgba(255,255,255,.14)}
  @keyframes siIn{from{opacity:0;transform:translateY(10px) scale(.96);filter:blur(4px)}}
  @keyframes siMsg{from{opacity:0;transform:translateY(6px);filter:blur(3px)}}
  @keyframes siPop{0%{transform:scale(.97);box-shadow:0 0 0 0 rgba(10,132,255,.45)}55%{transform:scale(1.025)}100%{transform:scale(1);box-shadow:0 0 0 10px rgba(10,132,255,0)}}
  @keyframes siPopOk{0%{transform:scale(.97);background:rgba(48,209,88,.42)}55%{transform:scale(1.03)}100%{transform:scale(1);background:rgba(255,255,255,.07)}}
  @keyframes siShine{to{background-position:-200% 0}}
  #solaraToast .si-msg.swap{animation:siMsg .5s cubic-bezier(.22,1,.36,1)}
  #solaraToast .si-tile.pop{animation:siPop .8s cubic-bezier(.22,1,.36,1)}
  #solaraToast .si-tile.ok.pop{animation:siPopOk .9s cubic-bezier(.22,1,.36,1)}
  #solaraToast .si-tile.doing{background:rgba(10,132,255,.16)}
  @keyframes siPulse{50%{box-shadow:0 0 0 5px rgba(10,132,255,0)}0%{box-shadow:0 0 0 0 rgba(10,132,255,.6)}}`;
  document.head.appendChild(islCss);

  function islandPlace(hidden) {
    if (!toastEl) return;
    const { islandV, islandH, gap } = LAYOUT, g = (+gap || 14) + 'px';
    toastEl.style.top = islandV === 'top' ? g : 'auto'; toastEl.style.bottom = islandV === 'bottom' ? g : 'auto';
    toastEl.style.left = islandH === 'left' ? g : islandH === 'center' ? '50%' : 'auto'; toastEl.style.right = islandH === 'right' ? g : 'auto';
    const x = islandH === 'center' ? '-50%' : '0', y = hidden ? (islandV === 'top' ? '-140px' : '140px') : '0';
    toastEl.style.transform = `translate(${x},${y}) scale(${hidden ? .92 : 1})`; toastEl.style.opacity = hidden ? '0' : '1';
  }
  const STEP_GLYPH = { todo: '', doing: '', done: '', fail: '' };
  let renderQ = 0;
  function islandRender() { if (!renderQ) renderQ = requestAnimationFrame(() => { renderQ = 0; islandDraw(); }); }
  function islandDraw() {
    if (!toastEl) {
      toastEl = document.createElement('div'); toastEl.id = 'solaraToast'; toastEl.setAttribute('role', 'status');
      toastEl.style.cssText = 'position:fixed;z-index:2147483647;display:flex;flex-direction:column;overflow:hidden;' +
        'transition:transform .8s cubic-bezier(.22,1,.36,1),opacity .45s ease,padding .6s cubic-bezier(.22,1,.36,1),border-radius .6s cubic-bezier(.22,1,.36,1),width .7s cubic-bezier(.22,1,.36,1)';
      toastEl.onclick = e => {
        if (e.target.closest('[data-isl="vendorgo"]')) { e.stopPropagation(); runVendorNow(); return; }
        if (e.target.closest('[data-isl="vendorlogin"]')) { e.stopPropagation(); window.open('https://vendor.pmsuryaghar.gov.in/', '_blank', 'noopener'); return; }
        const b = e.target.closest('[data-isl]');
        if (b) { e.stopPropagation(); const f = ISL.actions[b.dataset.isl]; if (f && !b.disabled) f(); return; }
        const f1 = e.target.closest('[data-fill1]');
        if (f1) { e.stopPropagation(); if (ISL.actions.fillOne) ISL.actions.fillOne(f1.dataset.fill1); return; }
        const pc = e.target.closest('[data-pickcust]');
        if (pc) { e.stopPropagation(); islandPick(pc.dataset.pickcust); return; }
        if (e.target.closest('.si-grid')) return;
        ISL.open = !ISL.open; ISL.fresh = ISL.open; islandRender();
      };
      document.body.appendChild(toastEl); islandPlace(true);
    }
    const k = ISL.kind, open = ISL.open, compact = !open && k === 'idle';
    const dot = { idle: '<span class="si-dot" style="background:#30D158;box-shadow:0 0 0 3px rgba(48,209,88,.25)"></span>',
      busy: '<span style="width:15px;height:15px;border:2px solid rgba(255,255,255,.25);border-top-color:#fff;border-radius:50%;animation:solaraSpin .8s linear infinite;flex:0 0 auto"></span>',
      ok: '<span style="width:20px;height:20px;border-radius:50%;background:#30D158;color:#06210F;display:grid;place-items:center;font-size:12px;font-weight:800;flex:0 0 auto">&#10003;</span>',
      warn: '<span style="width:20px;height:20px;border-radius:50%;background:#FF9F0A;color:#1A1203;display:grid;place-items:center;font-size:12px;font-weight:800;flex:0 0 auto">!</span>' }[k] || '';
    toastEl.classList.toggle('open', open);
    toastEl.style.padding = compact ? '7px 14px' : open ? '14px 16px 16px' : '11px 18px 12px';
    toastEl.style.borderRadius = open ? '32px' : compact ? '999px' : '26px';
    toastEl.style.width = open ? 'min(540px,94vw)' : 'auto'; toastEl.style.maxWidth = 'min(580px,94vw)';
    toastEl.style.fontSize = compact ? '12.5px' : '14px';
    const swap = ISL.lastMsg !== ISL.msg; ISL.lastMsg = ISL.msg;
    let html = `<div class="si-head">${dot}<span class="si-msg${swap ? ' swap' : ''}">${ISL.msg || 'Solara'}</span>` + (k === 'idle' && !open ? '' : '<span class="si-chev">&#9660;</span>') + '</div>';
    if (k === 'busy' && ISL.progress != null)
      html += `<div style="height:3px;border-radius:3px;background:rgba(255,255,255,.15);margin-top:7px"><div style="height:100%;width:${Math.round(ISL.progress * 100)}%;background:linear-gradient(90deg,#0A84FF,#64D2FF,#0A84FF);background-size:200% 100%;animation:siShine 1.6s linear infinite;border-radius:3px;transition:width .7s cubic-bezier(.22,1,.36,1)"></div></div>`;
    if (open) {
      let i = 0; const T = (cls, inner) => `<div class="si-tile ${cls}" style="--i:${i++}">${inner}</div>`;
      html += `<div class="si-grid${ISL.fresh ? ' fresh' : ''}">`; ISL.fresh = false;
      if (ISL.pend && !ISL.cust) {
        html += T('si-2', '<div class="si-k">Who are you filling for?</div>' + (ISL.pend.length ? ISL.pend.map(x => `<button class="si-pick" data-pickcust="${esc(x.id)}"><span class="si-av" style="width:32px;height:32px;font-size:13px">${esc((x.name || '?')[0])}</span><span><b>${esc(x.name)}</b><br><span style="opacity:.6;font-size:11.5px">${esc(x.id)} &middot; ${esc(x.consumer_no || '')}</span></span></button>`).join('') : '<div style="opacity:.6;margin-top:6px">No customer in Solara is waiting.</div>'));
      } else {
        if (ISL.cust) html += T('si-2', `<div class="si-cust"><div class="si-av">${esc((ISL.cust.name || '?')[0])}</div><div style="flex:1;min-width:0"><div class="si-k">Filling for</div><div class="si-v">${esc(ISL.cust.name)}</div><div style="opacity:.55;font-size:12px">${esc(ISL.cust.id)}</div></div><button class="si-link" data-isl="change">Change</button></div>`);
        if (ISL.steps.length) html += T('si-2', '<div class="si-steps">' + ISL.steps.map(x => `<span class="si-step ${x.s}"><span class="si-dot"></span>${esc(x.l)}</span>`).join('') + '</div>');
        ISL.tiles.forEach(t => { const b1 = ISL.actions.fillOne && t.v && t.s !== 'ok' && t.s !== 'doing' ? `<button class="si-btn pri" data-fill1="${esc(t.k)}" style="padding:6px 12px;font-size:12px">Fill</button>` : '';
          html += T((t.s || '') + (t.fx ? ' pop' : ''), `<div style="display:flex;align-items:center;gap:8px"><div style="min-width:0;flex:1"><div class="si-k">${esc(t.l)}</div><div class="si-v" title="${esc(t.v || '')}">${esc(t.v || '—')}</div></div>${b1}</div>`); t.fx = false; });
        const A = ISL.actions, btns = [];
        if (/#\/signed-in\/find-vendor/i.test(location.href) || /find a vendor/i.test(document.body.innerText)) btns.push('<button class="si-btn pri" data-isl="vendorgo">Find and select vendor</button>');
        if (A.fill) btns.push('<button class="si-btn pri" data-isl="fill">Fill now</button>');
        if (A.retry) btns.push('<button class="si-btn" data-isl="retry">Retry</button>');
        if (A.fetch) btns.push('<button class="si-btn" data-isl="fetch">Fetch Details</button>');
        if (A.next) btns.push('<button class="si-btn ok" data-isl="next">Next</button>');
        if (/pmsuryaghar\.gov\.in$/.test(location.host) && !/^vendor\./.test(location.host)) btns.push('<button class="si-btn" data-isl="vendorlogin">Vendor login</button>');
        if (A.more) btns.push('<button class="si-btn" data-isl="more">More</button>');
        if (btns.length) html += T('si-2', '<div class="si-act">' + btns.join('') + '</div>');
      }
      html += '</div>';
    }
    if (toastEl.__h !== html) { toastEl.__h = html; toastEl.innerHTML = html; }
    hiddenNow = false; islandPlace(false);
  }
  function tip(html, kind, ms, progress) {   // kind: 'idle' | 'busy' | 'ok' | 'warn'
    ISL.msg = html; ISL.kind = kind || 'busy'; ISL.progress = progress == null ? null : progress; islandRender();
    clearTimeout(toastTimer); if (ms) toastTimer = setTimeout(() => { if (!ISL.open) { hiddenNow = true; islandPlace(true); } }, ms);
  }
  const hideTip = () => { hiddenNow = true; islandPlace(true); };
  const setSteps = names => { ISL.steps = names.map(l => ({ l, s: 'todo' })); islandRender(); };
  const stepSet = (i, st) => { if (ISL.steps[i]) { ISL.steps[i].s = st; islandRender(); } };
  const TILE_KEYS = [['state', 'State'], ['district', 'District'], ['discom', 'Company'], ['consumer_no', 'Consumer no.']];
  const setTiles = c => { ISL.tiles = TILE_KEYS.map(([k, l]) => ({ k, l, v: (c.values && c.values[k]) || '', s: '' })); islandRender(); };
  const tileSet = (k, st, v) => { const t = ISL.tiles.find(x => x.k === k); if (t) { if (t.s !== st) t.fx = true; t.s = st; if (v != null) t.v = v; islandRender(); } };
  async function islandPick(id) {
    await store.set({ current: { cid: id, at: Date.now(), picked: true }, run: { cid: id, at: Date.now() } });
    ISL.pend = null; ISL.cust = null; pbDone = false; pbAsked = false; tip('Getting the customer ready…', 'busy');
    const r = await ask({ type: 'lookup', cid: id });
    if (r.ok) { try { sessionStorage.setItem('solaraCache:' + id, JSON.stringify({ t: Date.now(), data: r.data })); } catch (e) { /* skip */ } ISL.cust = { name: r.data.name, id }; setTiles(r.data); }
    sessionStorage.removeItem('solaraRun:' + id); sessionStorage.removeItem('solaraPress:fetch');   // choosing a customer on purpose is a new run
    if (startModal()) startModalFlow(true); else scan();
  }
  // where the panel and the bottom box sit comes from the options page (top / bottom, left / right, distance)
  function applyLayout() {
    const { panelV, panelH, gap } = LAYOUT, g = (+gap || 14) + 'px';
    panel.style.top = panelV === 'top' ? g : 'auto'; panel.style.bottom = panelV === 'bottom' ? g : 'auto';
    panel.style.left = panelH === 'left' ? g : 'auto'; panel.style.right = panelH === 'right' ? g : 'auto';
    const fb = document.getElementById('solaraFallback');   // the help box sits on the other side, so the two never overlap
    if (fb) { fb.style.top = panelV === 'top' ? g : 'auto'; fb.style.bottom = panelV === 'bottom' ? g : 'auto';
      fb.style.left = panelH === 'right' ? g : 'auto'; fb.style.right = panelH === 'left' ? g : 'auto'; }
    islandPlace(hiddenNow);
  }
  store.get({ islandV: 'top', islandH: 'center', panelV: 'bottom', panelH: 'right', gap: 14 }).then(v => { Object.assign(LAYOUT, v); applyLayout(); });
  // a field is found again by its meaning, because the portal re-draws parts of the dialog after a dropdown changes
  const freshInput = key => [...scope().querySelectorAll('input')].find(el => visible(el) && !el.readOnly && !el.disabled &&
    !['hidden', 'checkbox', 'radio', 'submit', 'button', 'password', 'file'].includes(el.type) && !humanOnly(el) && ruleFor(labelOf(el)) === key) || null;
  // Yes / No questions drawn as radio buttons: grouped by name, the question read from the nearest label, each option by its own label
  const radioText = r => {
    const own = ((r.id && document.querySelector(`label[for="${CSS.escape(r.id)}"]`)?.innerText) || r.closest('label')?.innerText || r.getAttribute('aria-label') || '').trim();
    if (own) return own;
    const w = r.closest('.p-radiobutton'), host = w && (w.parentElement || w);
    const sib = w && ((w.nextElementSibling && (w.nextElementSibling.innerText || '').trim()) || ((host.querySelector('label') || {}).innerText || '').trim());
    if (sib) return sib;
    return r.value === 'true' ? 'Yes' : r.value === 'false' ? 'No' : (r.value || '');
  };
  function radioGroups(root) {
    const all = [...root.querySelectorAll('input[type=radio]')], by = new Map();
    all.forEach((r, i) => { if (r.disabled) return; const k = r.name || (r.closest('[role=radiogroup]') || {}).id || 'g' + i; if (!by.has(k)) by.set(k, []); by.get(k).push(r); });
    return [...by.values()].map(rs => {
      let q = '', p = rs[0].closest('[role=radiogroup],fieldset,.p-field,.form-group,.field,.col,div');
      for (let i = 0; i < 5 && p && !q; i++, p = p.parentElement) {
        const l = [...p.querySelectorAll('label,legend,h5,h6,.p-field > span')].find(e => !rs.some(r => e.contains(r)) && !rs.some(r => radioText(r) === (e.innerText || '').trim()) && (e.innerText || '').trim().length > 6);
        if (l) q = l.innerText.trim();
      }
      const camel = (rs[0].name || '').replace(/([a-z])([A-Z])/g, '$1 $2');   // roofLoadCapacity -> roof Load Capacity
      return { key: ruleFor(norm(q)) || ruleFor(norm(camel)), q: q.replace(/[*:\s]+$/, '') || camel, rs, opts: rs.map(r => ({ el: r, text: radioText(r) })) };
    });
  }
  function pickRadio(g, value) {
    const o = g.opts.find(x => norm(x.text) === norm(value)); if (!o) return false;
    if (o.el.checked) return true;
    (o.el.closest('.p-radiobutton') || o.el).click(); if (!o.el.checked) o.el.click();   // a plain click: the portal's own handler picks it
    return o.el.checked;
  }
  // The vendor's equipment certification on the Site Feasibility Report. It is the one declaration that is ticked, and only
  // because the owner turned the switch on in the options; the customer's declarations are never ticked.
  const CERT_RE = /certify that the proposed equipment/i;
  function certBox(root) {
    return [...root.querySelectorAll('input[type=checkbox]')].find(el => {
      if (/certification/i.test((el.closest('p-checkbox') || {}).getAttribute?.('formcontrolname') || '')) return true;   // the portal's own name for it
      let p = el;
      for (let i = 0; i < 6 && p; i++, p = p.parentElement) { const t = p.innerText || ''; if (t.length < 600 && CERT_RE.test(t)) return true; }
      return false;
    }) || null;
  }
  function tickCert(el) {
    if (el.checked) return true;
    const w = el.closest('.p-checkbox');
    ((w && w.querySelector('.p-checkbox-box')) || w || el).click(); if (!el.checked) el.click();   // the portal's checkbox answers a click on its box
    return el.checked;
  }
  // Manual mode: the Fill button next to one value. Dropdowns are picked by their text, boxes are typed.
  async function fillOne(c, key) {
    if (key === 'certify') { const el = certBox(scope()); tileSet('certify', 'doing'); tileSet('certify', el && tickCert(el) ? 'ok' : 'warn'); return; }
    const v = c.values && c.values[key]; if (!has(v)) return;
    tileSet(key, 'doing');
    let ok = false;
    try {
      const rg = radioGroups(scope()).find(x => x.key === key), cu = rg ? null : customsIn(scope()).find(x => x.key === key);
      if (rg) ok = pickRadio(rg, v);
      else if (cu) ok = isEmpty(cu.el) ? await pickCustom(cu.el, v) : true;
      else { const el = freshInput(key); if (el) { ok = !el.value || el.value === String(v) ? true : false; if (!el.value) ok = !!(await typeInto(el, v)) && el.value === String(v); } }
    } catch (e) { ok = false; }
    tileSet(key, ok ? 'ok' : 'warn', ok ? null : 'not found or not accepted');
  }
  // type it in character by character, the way a person would, so it is easy to follow
  async function typeInto(el, value) {
    const v = String(value);
    el.scrollIntoView({ block: 'center', behavior: PACE.char > 10 ? 'smooth' : 'auto' }); el.focus && el.focus();
    if (PACE.char && v.length <= 24) for (let i = 1; i < v.length; i++) { setVal(el, v.slice(0, i)); await sleep(PACE.char); }
    return setVal(el, v);
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
      b.style.cssText = 'position:fixed;z-index:2147483646;width:min(520px,calc(100vw - 370px));min-width:300px;max-height:46vh;overflow:auto;' +
        'background:#3A2E12;color:#F7E3B0;font:14px/1.4 system-ui,Arial,sans-serif;border-radius:10px;box-shadow:0 8px 28px rgba(0,0,0,.4);padding:12px';
      document.body.appendChild(b); setTimeout(applyLayout, 0);
    }
    return b;
  };
  const FILE_NAMES = { bill: 'Electricity bill', aadhaar: 'Aadhaar', passbook: 'Bank passbook', roof: 'Roof photographs', agreement: 'Signed agreement', quotation: 'Quotation' };
  const fbInput = 'flex:1;min-width:0;padding:8px;border-radius:6px;border:0;color:#04150D;font-size:15px';
  function showFallback(c) {
    const box = fbBox();
    fallbackItems = fallbackItems.filter(i => !i.done);
    if (!fallbackItems.length) { box.remove(); if (lastFill) { lastFill.left = []; lastFill.failed = []; forwardStep(); } return; }
    const typed = {};   // keep what is being typed or chosen across a redraw
    box.querySelectorAll('[data-fbv],[data-fbf]').forEach(e => { typed[e.dataset.fbv !== undefined ? 'v' + e.dataset.fbv : 'f' + e.dataset.fbf] = e.value; });
    box.innerHTML = `<div style="display:flex;justify-content:space-between"><b>Solara needs your help with ${fallbackItems.length} field(s)</b>` +
      `<span id="fbClose" style="cursor:pointer" title="Hide">&#10005;</span></div>` + fallbackItems.map((it, i) =>
      `<div style="margin-top:8px"><div style="font-size:12px">${esc(it.label)}${it.why ? ` &middot; <span style="opacity:.8">${esc(it.why)}</span>` : ''}</div><div style="display:flex;gap:6px;margin-top:3px">` +
      (it.type === 'file' ? `<input type="file" data-fbfile="${i}" style="${fbInput};background:#fff">`
        : it.type === 'text' ? `<input data-fbv="${i}" style="${fbInput}" autocomplete="off">`
        : it.options ? `<input data-fbf="${i}" placeholder="type to narrow the list" style="width:36%;${fbInput}"><select data-fbv="${i}" style="${fbInput}">${it.options.map(o => `<option>${esc(o)}</option>`).join('')}</select>`
        : `<button data-fbload="${i}" style="${fbInput};cursor:pointer;font-weight:700">Show the choices</button>`) +
      (it.type === 'text' || it.options ? `<button data-fbgo="${i}" style="border:0;border-radius:6px;padding:6px 14px;cursor:pointer;font-weight:700;font-size:15px">Fill</button>` : '') +
      '</div>' + ((it.suggest || []).length ? `<div style="margin-top:4px;font-size:12px">Suggested: ${it.suggest.map((v, j) =>
        `<button data-fbs="${i}|${j}" style="border:0;border-radius:12px;padding:3px 10px;margin-right:4px;cursor:pointer;background:#F2C879;color:#04150D;font-weight:700">${esc(v)}</button>`).join('')}</div>` : '') +
      '<div data-fbmsg="' + i + '" style="font-size:12px;margin-top:2px"></div></div>').join('');
    box.querySelectorAll('[data-fbv],[data-fbf]').forEach(e => { const k = e.dataset.fbv !== undefined ? 'v' + e.dataset.fbv : 'f' + e.dataset.fbf; if (typed[k] !== undefined && typed[k] !== '') e.value = typed[k]; });
    box.querySelector('#fbClose').onclick = () => box.remove();
    const note = (i, t, bad) => { const m = box.querySelector(`[data-fbmsg="${i}"]`); m.textContent = t; m.style.color = bad ? '#F2A6A0' : '#9FE3C1'; };
    box.querySelectorAll('[data-fbfile]').forEach(inp => inp.onchange = () => {   // the owner picks the file; it goes into the portal's box
      const i = +inp.dataset.fbfile, it = fallbackItems[i], f = inp.files[0]; if (!f) return;
      const dt = new DataTransfer(); dt.items.add(f); it.el.files = dt.files; it.el.dispatchEvent(new Event('change', { bubbles: true }));
      it.el.style.outline = '2px solid #2BB673'; it.done = true; note(i, 'Attached ' + f.name); setTimeout(() => showFallback(c), 700);
    });
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
      if (it.type === 'select' && c._refill) {   // changing a dropdown makes the portal clear the fields below it: type them again, then fetch again
        tip('Filling the consumer number again…', 'busy'); await sleep(400);
        await c._refill();
        if (await running()) { sessionStorage.removeItem('solaraPress:fetch:' + location.href); if (openApplyCard('fetch')) { tip('Pressing <b>Fetch Details</b> again…', 'busy'); await sleep(1500); } }
      }
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
    forward: { find: 'button,[role=button],input[type=submit]', text: /^\s*(save\s*(&|and)\s*continue|upload\s*(&|and)?\s*(continue)?|next|submit(\s+application)?)\s*$/i },
  };
  function openApplyCard(kind) {
    const spec = PRESS[kind], seenKey = 'solaraPress:' + kind + (kind === 'fetch' ? '' : ':' + location.href);
    if (!spec || Date.now() - (+sessionStorage.getItem(seenKey) || 0) < (kind === 'fetch' ? 600000 : 1e12)) return false;   // Fetch is rate-limited by the portal: once, never because the URL changed
    if (spec.needs && !spec.needs.test(scope().innerText)) return false;
    const hit = [...document.querySelectorAll(spec.find)]
      .filter(el => visible(el) && !panel.contains(el) && !el.disabled && spec.text.test((el.innerText || '').trim()) && (el.innerText || '').length < 120)
      .sort((x, y) => x.innerText.length - y.innerText.length)[0];
    if (!hit) return false;
    sessionStorage.setItem(seenKey, String(Date.now()));
    (spec.up && hit.closest(spec.up) || hit).click();
    return true;
  }
  // The portal's forward button. Pressed only when the owner turned "Press Next / Submit for me" on in the
  // options AND the page is fully filled: nothing missing, nothing waiting in the popup, OTP and CAPTCHA typed,
  // and any declaration box ticked by the person (a consent is never ticked for them).
  function forwardButton(root) {
    const spec = PRESS.forward;
    return [...root.querySelectorAll(spec.find)].filter(el => visible(el) && !panel.contains(el) && !el.disabled &&
      spec.text.test(((el.innerText || el.value || '') + '').trim()))[0] || null;
  }
  function readyToPress(root, left, failed) {
    const pending = fallbackItems.filter(i => !i.done).map(i => i.label);
    if (pending.length) return pending.join(', ') + ' still to fill in the box below';
    if (left.length || failed.length) return 'some fields are still empty';
    if ([...root.querySelectorAll('input')].some(el => visible(el) && !el.value && !el.readOnly && humanOnly(el) && el.type !== 'password'))
      return 'the OTP or CAPTCHA is still to be typed';
    if ([...root.querySelectorAll('input[type=checkbox]')].some(el => visible(el) && !el.checked && /declar|agree|consent|guideline|terms/i.test(labelOf(el) + ' ' + (el.closest('label,div') || {}).innerText)))
      return 'the declaration is still to be ticked by you';
    return '';
  }
  // a click the way a mouse sends it, so the portal's framework reacts
  const realClick = el => { ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(t => el.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, view: window }))); };
  const waitFor = async (fn, ms) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { const v = fn(); if (v) return v; await sleep(250); } return ''; };
  const digits = v => String(v || '').replace(/\D/g, '');
  const customsIn = root => [...root.querySelectorAll(CUSTOM)].filter(el => visible(el) && !el.closest('select') && !el.querySelector('input:not([type=hidden]),select'))
    .map(el => { const key = ruleFor(labelOf(el)); return key === null ? null : { el, key, label: shown(el) || key }; }).filter(Boolean);
  const shownOf = el => (boxOf(el).innerText || '').trim().split('\n')[0];

  // ---- the rule for the "Start a new Application" box: what to do, in this order, each step confirmed and retried ----
  //   1 State  2 District  3 Company  (pause)  4 Consumer Account Number  5 Fetch Details  6 check all, fix, ready for Next
  const START_RE = /start a new application/i;
  const startModal = () => [...document.querySelectorAll('.p-dialog,[role=dialog],.p-dynamic-dialog,.modal.show')].filter(visible).find(d => START_RE.test(d.innerText || ''));
  let fillBusy = false, screensDone = new Set(), afterNextGo = false, pbStarting = false, pbActive = false, pbDone = false, pbAsked = false, pbAbsent = 0, pbLastRun = 0;   // pbDone: this opening of the box has been handled; it is not run again until Retry or the box is closed and reopened
  async function startAppPlaybook(c) {
    if (pbActive) return; pbActive = true; pbDone = false; pbLastRun = Date.now(); ISL.phase = 'filling';
    const v = c.values || {}, caWant = String(v.consumer_no || '');
    ISL.cust = { name: c.name, id: c.customer_id }; setSteps(['State', 'District', 'Company', 'Consumer no.', 'Fetch', 'Ready']); setTiles(c);
    const pressFetchNow = () => { const b = [...scope().querySelectorAll('button,[role=button]')].find(z => visible(z) && !z.disabled && PRESS.fetch.text.test((z.innerText || '').trim())); if (b) { tip('Pressing Fetch Details…', 'busy'); realClick(b); } };
    ISL.actions = { retry: () => { if (!pbActive) { pbDone = false; sessionStorage.removeItem('solaraRun:' + c.customer_id); sessionStorage.removeItem('solaraPress:fetch'); startAppPlaybook(c); } }, fetch: pressFetchNow, change: () => pick() };
    try {
      tip(`Start a new Application: filling for ${esc((c.name || '').split(' ')[0])}`, 'busy', 0, 0.02); await sleep(PACE.step);
      const dd = async (idx, key, label, want) => {
        stepSet(idx, 'doing'); tileSet(key, 'doing'); tip(`Filling ${esc(label)}…`, 'busy', 0, idx / 6);
        for (let a = 1; a <= 3; a++) {
          const x = customsIn(scope()).find(z => z.key === key); if (!x) { await sleep(PACE.step * 2); continue; }
          if (!isEmpty(x.el)) { tileSet(key, 'ok', shownOf(x.el)); stepSet(idx, 'done'); return true; }   // already chosen, by the portal or the owner
          x.el.scrollIntoView({ block: 'center', behavior: 'auto' }); await sleep(PACE.step / 2);
          if (has(want)) { if (await pickCustom(x.el, want)) { await sleep(PACE.step); tileSet(key, 'ok', shownOf(x.el)); stepSet(idx, 'done'); return true; } }
          else break;
          tip(`${esc(label)}: trying again (${a + 1} of 3)…`, 'busy', 0, idx / 6); await sleep(PACE.step * 2);
        }
        const x = customsIn(scope()).find(z => z.key === key); if (!x) { stepSet(idx, 'fail'); tileSet(key, 'warn', 'not found'); return false; }
        const names = (await pickCustom(x.el, '', 'list')) || [], hay = addressText(c), inAddr = names.filter(n => norm(n).length > 3 && hay.includes(norm(n)));
        if (inAddr.length === 1 && await pickCustom(x.el, inAddr[0])) { tileSet(key, 'ok', shownOf(x.el)); stepSet(idx, 'done'); return true; }   // the one named in the address
        const item = { type: 'select', el: x.el, key, label, options: names.length ? names : null, suggest: inAddr.slice(0, 3), why: has(want) ? `“${want}” is not in the list` : 'Solara has no data' };
        fallbackItems.push(item); showFallback(c); tileSet(key, 'warn', 'choose below'); ISL.open = false;
        tip(`Choose the ${esc(label.toLowerCase())} in the box below.`, 'warn');
        await waitFor(() => item.done, 300000);
        const y = customsIn(scope()).find(z => z.key === key);
        if (item.done && y) { tileSet(key, 'ok', shownOf(y.el)); stepSet(idx, 'done'); return true; }
        stepSet(idx, 'fail'); return false;
      };
      const caStep = async () => {
        stepSet(3, 'doing'); tileSet('consumer_no', 'doing'); tip('The portal needs a moment. The consumer number is next…', 'busy', 0, 0.5); await sleep(PACE.settle);
        for (let a = 1; a <= 3; a++) {
          tip(`Typing the consumer number${a > 1 ? ` (try ${a} of 3)` : ''}…`, 'busy', 0, 0.6);
          const el = freshInput('consumer_no'); if (!el) { await sleep(PACE.step * 2); continue; }
          if (digits(el.value) !== digits(caWant)) { setVal(el, ''); await typeInto(el, caWant); await sleep(PACE.step); }
          const e2 = freshInput('consumer_no'); if (e2 && digits(e2.value) === digits(caWant)) { tileSet('consumer_no', 'ok', caWant); stepSet(3, 'done'); return true; }
        }
        stepSet(3, 'fail'); tileSet('consumer_no', 'warn', 'could not type it'); return false;
      };
      const fetchStep = async () => {
        stepSet(4, 'doing'); let last = 'none';
        for (let a = 1; a <= 3; a++) {
          const b = [...scope().querySelectorAll('button,[role=button]')].find(z => visible(z) && PRESS.fetch.text.test((z.innerText || '').trim()));
          if (!b) { await sleep(PACE.step * 2); continue; }
          if (b.disabled) { await sleep(PACE.step * 3); continue; }
          tip(`Pressing Fetch Details${a > 1 ? ` (try ${a} of 3)` : ''}…`, 'busy', 0, 0.8); await sleep(PACE.step); sessionStorage.setItem('solaraPress:fetch', String(Date.now())); realClick(b);
          last = await waitFor(() => { const t = scope().innerText; return /data\s+not\s+available/i.test(t) ? 'nodata' : /consumer details/i.test(t) ? 'ok' : ''; }, 9000) || 'none';
          if (last === 'ok' || last === 'nodata') break;
        }
        if (last === 'ok') { stepSet(4, 'done'); return 'ok'; }
        stepSet(4, 'fail'); return last;
      };
      let okAll = (await dd(0, 'state', 'State', v.state)) && (await dd(1, 'district', 'District', v.district)) && (await dd(2, 'discom', 'Company', v.discom));
      let got = '';
      if (okAll) {
        if (await caStep()) {
          // one last look before Fetch: the portal clears the number when a dropdown changes
          const ca0 = freshInput('consumer_no'); if (!ca0 || digits(ca0.value) !== digits(caWant)) await caStep();
          got = await fetchStep();
        }
      }
      // Fetch Details has been pressed (or failed). From here nothing more is done until the person acts.
      if (got === 'nodata') { tip('The portal has no data for this consumer number. Check it on the bill and correct it.', 'warn'); stepSet(5, 'fail'); return; }
      const nextBtn = [...scope().querySelectorAll('button,[role=button]')].find(z => visible(z) && /^\s*next\s*$/i.test((z.innerText || '').trim()));
      if (okAll && got === 'ok' && nextBtn) {
        for (let i = 0; i < 20 && nextBtn.disabled; i++) await sleep(300);
        stepSet(5, 'done'); nextBtn.classList.add('solara-ring');
        ISL.actions = { retry: () => { if (!pbActive) { pbDone = false; sessionStorage.removeItem('solaraRun:' + c.customer_id); sessionStorage.removeItem('solaraPress:fetch'); startAppPlaybook(c); } }, fetch: pressFetchNow, next: () => realClick(nextBtn), change: () => pick() };
        ISL.phase = 'waiting';
        tip(`Filled. Check it, then press <b>Next</b> when you are ready. I will wait.`, 'ok');
        const { autoSubmit } = await store.get({ autoSubmit: false });
        if (autoSubmit && !nextBtn.disabled) { await sleep(900); realClick(nextBtn); }
      } else { ISL.phase = 'waiting'; stepSet(5, 'fail'); tip('Something did not go through. Press Retry, or fill the rest yourself. I will wait.', 'warn'); }
    } finally { pbActive = false; pbDone = true; }   // done or failed: stop. Only Retry runs it again
  }
  // opening the box by hand starts the rule by itself, with the customer you picked; the refresh icon is no longer needed
  const handled = new WeakSet();   // dialog nodes already run: a node is never run twice, however often the page re-renders around it
  async function startModalFlow(force) {
    if (!isOwner()) return;
    const d = startModal(); if (!d || pbActive) return;
    if (handled.has(d) && !force) return;
    if (pbDone && !force) return;
    if (!force && Date.now() - pbLastRun < 20000) return;   // never in a loop
    if (pbAsked && !force) return;   // already asked who this is for; wait for the answer, do not ask again
    if (pbStarting) return; pbStarting = true; if (force) handled.delete(d);   // one start at a time: the watcher, the timer and the page-change scan all land here
    try { await startModalFlow2(force); } finally { pbStarting = false; }
  }
  async function startModalFlow2(force) {
    const rec = await recalled();
    if (pbActive || (pbDone && !force)) return;
    if (!rec) { pbAsked = true; await pick(); return; }   // ask once for this opening of the box
    const key = 'solaraCache:' + rec.cid;
    const cached = (() => { try { const x = JSON.parse(sessionStorage.getItem(key) || 'null'); return x && Date.now() - x.t < 120000 ? x.data : null; } catch (e) { return null; } })();
    const r = cached ? { ok: true, data: cached } : await ask({ type: 'lookup', cid: rec.cid });
    if (!r.ok) { pbDone = true; ISL.actions = { retry: () => { pbDone = false; pbAsked = false; startModalFlow(true); } }; tip(`Could not reach Solara: ${esc(r.error)}. Press Retry when it is back.`, 'warn'); return; }
    if (!cached) try { sessionStorage.setItem(key, JSON.stringify({ t: Date.now(), data: r.data })); } catch (e) { /* skip */ }
    const d2 = startModal();
    if (pbActive || (pbDone && !force) || !d2 || (handled.has(d2) && !force)) return;   // a run finished or the box closed while we were asking
    const lockKey = 'solaraRun:' + rec.cid;   // the same customer is not filled again within 3 minutes, even if the portal rebuilt the box
    if (!force && Date.now() - (+sessionStorage.getItem(lockKey) || 0) < 180000) { pbDone = true; return; }
    sessionStorage.setItem(lockKey, String(Date.now())); handled.add(d2);
    if (MODE === 'manual') {   // show the values; the person presses Fill for each, or Fill all
      const c = r.data; pbDone = true;
      ISL.cust = { name: c.name, id: c.customer_id }; ISL.pend = null; ISL.steps = []; setTiles(c);
      ISL.actions = { fillOne: k => fillOne(c, k), fill: () => { pbDone = false; startAppPlaybook(c); }, change: () => pick() };
      ISL.open = true; ISL.fresh = true; ISL.phase = 'waiting';
      tip('Manual: press Fill next to a value, or Fill now for all of them.', 'idle');
      return;
    }
    await startAppPlaybook(r.data);
  }
  let modalTimer;
  const OURS = '#solaraToast,#solaraPanel,#solaraFallback';
  try {
    new MutationObserver(muts => {
      if (pbActive || pbDone || pbAsked) return;   // working, finished, or waiting for an answer: nothing to watch
      if (muts.every(m => m.target.nodeType === 1 ? m.target.closest(OURS) : m.target.parentElement && m.target.parentElement.closest(OURS))) return;
      clearTimeout(modalTimer); modalTimer = setTimeout(() => startModalFlow(false), 350);
    }).observe(document.body, { childList: true, subtree: true });
  } catch (e) { /* skip */ }
  setInterval(() => {
    if (pbActive) return;
    if (!document.querySelector('.p-dialog,[role=dialog],.p-dynamic-dialog,.modal.show')) { if (++pbAbsent >= 2 && (pbDone || pbAsked)) { pbDone = false; pbAsked = false; ISL.phase = 'idle'; } return; }   // no box at all: cheap, and a closed box means the next opening is new
    if (startModal()) { pbAbsent = 0; if (!pbDone && !pbAsked) startModalFlow(false); }   // the box was closed (not just re-drawn): the next opening is a new application
  }, 1500);
  const running = async () => { const { run, vendorFills } = await store.get({ run: null, vendorFills: true });
    return run && Date.now() - run.at < 60 * 60 * 1000 ? { run, vendorFills } : null; };

  async function scan() {
    if (startModal()) { startModalFlow(false); return; }   // not forced: a page change must not run the rule again
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
    const ck = cid ? 'solaraCache:' + cid : '';
    const cached = ck && (() => { try { const x = JSON.parse(sessionStorage.getItem(ck) || 'null'); return x && Date.now() - x.t < 120000 ? x.data : null; } catch (e) { return null; } })();
    if (!cached) say('Looking up this customer…');
    const r = cached ? { ok: true, data: cached } : await ask({ type: 'lookup', consumer_no: consumer, app_no: app, cid });
    if (r.ok && ck && !cached) try { sessionStorage.setItem(ck, JSON.stringify({ t: Date.now(), data: r.data })); } catch (e) { /* too big: skip */ }
    if (!r || !r.ok) { say(`<span style="color:#F2A6A0">${esc((r && r.error) || 'No answer from Solara.')}</span>` + (fields.length ? btn('solaraPick', 'Choose the customer') : '') + btn('solaraRetry', 'Try again'));
      const p = panel.querySelector('#solaraPick'); if (p) p.onclick = pick;
      panel.querySelector('#solaraRetry').onclick = scan; return; }
    const c = r.data;
    remember(c);
    ISL.cust = { name: c.name, id: c.customer_id }; ISL.pend = null; ISL.tiles = []; ISL.actions.change = () => pick();
    tip(`Solara &middot; ${esc((c.name || '').split(' ')[0])}`, 'idle');
    const head = `<div style="margin-top:6px;padding:7px 9px;border-radius:7px;background:#16303A"><div style="font-size:10px;letter-spacing:.08em;color:#8FA3B2">FILLING FOR</div>` +
      `<b style="font-size:14px">${esc(c.name)}</b> <span style="color:#8FA3B2">&middot; ${esc(c.customer_id)}</span> ` +
      `<a href="#" id="solaraChange" style="color:#8FA3B2;font-size:11px;margin-left:6px">change</a></div>`;
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
    ISL.actions.more = () => { panel.style.display = panel.style.display === 'none' ? '' : 'none'; };
  }

  function wireChange() { const a = panel.querySelector('#solaraChange'); if (a) a.onclick = e => { e.preventDefault(); pick(); }; }

  async function pick() {
    const r = await ask({ type: 'pending' });
    if (r && r.ok) { ISL.pend = r.data; ISL.cust = null; ISL.steps = []; ISL.tiles = []; ISL.actions = { more: () => { panel.style.display = panel.style.display === 'none' ? '' : 'none'; } }; ISL.open = true; tip('Choose the customer you are filling for', 'idle'); }
    if (!r || !r.ok) { say(`<span style="color:#F2A6A0">${esc((r && r.error) || 'No answer from Solara.')}</span>`); return; }
    if (!r.data.length) { say('No customer in Solara is waiting to be registered.'); return; }
    say('<div style="margin-top:4px">Fill this page for:</div>' + r.data.map(x =>
      `<button data-pick="${esc(x.id)}" style="display:block;width:100%;text-align:left;margin-top:6px;padding:7px 9px;border:0;border-radius:7px;background:#24343F;color:#E8EEF2;cursor:pointer">` +
      `<b>${esc(x.name)}</b><br><span style="color:#8FA3B2;font-size:11px">${esc(x.id)} &middot; consumer ${esc(x.consumer_no)}</span></button>`).join(''));
    panel.querySelectorAll('[data-pick]').forEach(b => b.onclick = async () => {
      await store.set({ current: { cid: b.dataset.pick, at: Date.now(), picked: true } });
      const x = r.data.find(y => y.id === b.dataset.pick);
      ask({ type: 'lookup', cid: x.id }).then(pre => { if (pre.ok) try { sessionStorage.setItem('solaraCache:' + x.id, JSON.stringify({ t: Date.now(), data: pre.data })); } catch (e) { /* skip */ } });
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

  let lastFill = null;   // what the last Fill left over, so the forward step can run again once the popup is done
  async function forwardStep() {
    if (!lastFill) return;
    const { root, left, failed } = lastFill, box = panel.querySelector('#solaraFilled');
    if (panel.querySelector('#solaraGo') || (box && /Pressing <b>/.test(box.innerHTML))) return;
    const why = readyToPress(root, left, failed);
    let fwd = forwardButton(root);
    if (!fwd) { const all = [...root.querySelectorAll(PRESS.forward.find)].filter(el => visible(el) && !panel.contains(el) && PRESS.forward.text.test(((el.innerText || el.value || '') + '').trim())); fwd = all[0] || null; }
    if (!fwd || !box) { if (!why) tip('All filled. Check the page, then continue.', 'ok', 9000); else tip(`Still needed: ${esc(why)}`, 'warn', 9000); return; }
    const label = ((fwd.innerText || fwd.value || '') + '').trim(), { autoSubmit } = await store.get({ autoSubmit: false }), key = 'solaraPress:forward:' + location.href;
    box.querySelector('#solaraWhy')?.remove();
    if (why) { tip(`Not ready to continue: ${esc(why)}.`, 'warn', 12000); box.insertAdjacentHTML('beforeend', `<div id="solaraWhy" style="margin-top:6px;color:#F2C879">Not pressing “${esc(label)}”: ${esc(why)}.</div>`); return; }
    for (let i = 0; i < 20 && fwd.disabled; i++) await sleep(300);   // Next stays locked until Fetch Details has answered
    if (fwd.disabled) {
      const fetchBtn = [...root.querySelectorAll('button,[role=button]')].find(b => visible(b) && !b.disabled && PRESS.fetch.text.test((b.innerText || '').trim()));
      if (fetchBtn) { tip('All filled. Press <b>Fetch Details</b>, then <b>' + esc(label) + '</b>.', 'ok'); fetchBtn.classList.add('solara-ring'); }
      else tip(`All filled. <b>${esc(label)}</b> unlocks when the portal has the details.`, 'warn', 12000);
      return;
    }
    tip(`All filled. Press <b>${esc(label)}</b> to continue.`, 'ok');
    fwd.classList.add('solara-ring');
    if (autoSubmit && await running() && !sessionStorage.getItem(key)) {
      sessionStorage.setItem(key, '1');
      box.insertAdjacentHTML('beforeend', `<div style="margin-top:6px;color:#5FD3A8">Everything is filled. Pressing <b>${esc(label)}</b>…</div>`);
      await sleep(900); fwd.click();
    } else {
      box.insertAdjacentHTML('beforeend', btn('solaraGo', `Looks right: press ${esc(label)}`, true));
      const go = panel.querySelector('#solaraGo'); if (go) go.onclick = () => { go.textContent = 'Pressed'; fwd.click(); };
    }
  }

  // fixed words of each screen of the portal: a screen is "known" only when most of its words are on the page
  const SCREENS = [
    ['Details of Applicant', [/details of applicant/i, /name as per electricity bill/i, /\bgender\b/i, /type of location/i, /pin ?code/i]],
    ['Electricity Distribution Company Details', [/electricity distribution company details/i, /consumer (account )?(no|number)|ca no/i]],
    ['Site Feasibility Report', [/site feasibility report/i, /roof has enough load|load bearing/i, /shadow ?free roof/i, /permissible rts installation capacity|permissible/i, /quotation (amount|document)/i]],
    ['Upload Agreement', [/upload agreement/i, /agreement copy/i, /total cost of rts installation/i, /application number/i]],
    ['Solar Rooftop Details', [/solar rooftop details/i, /proposed solar plant capacity/i, /latitude/i, /longitude/i, /category/i]],
  ];
  function screenOf(root) {
    const t = root.innerText || '';
    const best = SCREENS.map(([name, words]) => ({ name, hit: words.filter(w => w.test(t)).length, total: words.length })).sort((a, b) => b.hit / b.total - a.hit / a.total)[0];
    return best && best.hit / best.total >= 0.6 ? best : null;
  }
  // the portal's own red messages ("Urban Local Body Name must be filled", "capacity is more than the sanctioned load")
  function portalErrors() {
    const seen = new Set();
    return [...document.querySelectorAll('.p-error,.text-danger,.invalid-feedback,.error-message,small.error,[class*=error-msg],[class*=errormsg]')]
      .filter(e => visible(e) && !panel.contains(e) && !e.closest('#solaraToast,#solaraFallback') && (e.innerText || '').trim().length > 3 && (e.innerText || '').length < 220)
      .map(e => ({ lab: ((e.closest('.form-group,.field,.col,.p-field,div') || e).querySelector('label')?.innerText || '').replace(/[*\s]+$/, '').trim(), t: e.innerText.trim() }))
      .filter(x => !seen.has(x.t) && seen.add(x.t));
  }
  function showErrors() {
    const list = portalErrors(); if (!list.length) return false;
    ISL.errors = list;
    tip('<b>The portal says:</b><br>' + list.slice(0, 4).map(e => (e.lab ? '<b>' + esc(e.lab) + '</b>: ' : '') + esc(e.t)).join('<br>'), 'warn');
    return true;
  }
  function formMode(c, root, head, saved) {
    const mapBox = el => /^(lat|lng)$/.test(ruleFor(labelOf(el)) || '');
    const els = [...root.querySelectorAll('input,select,textarea')].filter(el => visible(el) && (mapBox(el) || (!el.readOnly && !el.disabled)) &&
      !['hidden', 'checkbox', 'radio', 'submit', 'button', 'password', 'file'].includes(el.type) && !humanOnly(el) && !isSearch(el));
    // custom dropdowns are picked by their visible option text; one that cannot be matched is named for the owner
    const customsAll = [...root.querySelectorAll(CUSTOM)].filter(el => visible(el) && !el.closest('select') &&
      !el.querySelector('input:not([type=hidden]),select')).map(el => {
        const key = ruleFor(labelOf(el)); return key === null ? null : { el, key, label: shown(el) || key }; })
      .filter(Boolean);
    const customs = customsAll.filter(x => x.key && has(c.values[x.key]));
    const lackCustoms = customsAll.filter(x => x.key && !has(c.values[x.key]) && isEmpty(x.el) && !x.el.closest('header,nav,.p-menubar,.p-menu,.navbar,.dropdown-menu'));   // only fields Solara has a rule for: never menus or boxes it does not know
    const radios = radioGroups(root).filter(g => g.key);
    const known = screenOf(root);
    if (known) { ISL.screen = known.name + ' (' + known.hit + ' of ' + known.total + ' marks seen)'; }
    else if (els.length > 6) { ISL.screen = ''; tip('I do not know this screen by its headings. I fill only the fields whose names I recognise. Check the page.', 'warn'); }
    const issues = c.issues || [];
    const issueHtml = (issues.length ? `<div style="margin-top:8px;padding:8px;border-radius:7px;background:#3A2E12;color:#F2C879">` +
      `<b>${issues.length} to sort out in Solara first</b>` + issues.map(i => `<div style="margin-top:3px"><b>${esc(i.kind)}</b>: ${esc(i.field)} &mdash; ${esc(i.message)}</div>`).join('') + '</div>' : '') +
      (c.build_error ? `<div style="margin-top:6px;color:#F2A6A0">${esc(c.build_error)}</div>` : '');
    c._customs = customs;
    const plan = els.map(el => ({ el, key: ruleFor(labelOf(el)) }));
    const fillable = plan.filter(p => p.key && has(c.values[p.key]));
    // fields the page asks for that Solara knows by name but has no data for: the owner types them here
    const lacking = plan.filter(p => p.key && !has(c.values[p.key]) && !p.el.value && p.el.tagName !== 'SELECT');   // a known field with no data; unknown boxes are left alone
    const lackHtml = '';
    fallbackItems = [...lacking.map(p => ({ type: 'text', el: p.el, key: p.key, label: shown(p.el) || p.key, why: p.key ? 'Solara has no data' : 'Solara does not know this field', suggest: p.key === 'rts_cost' && (c.cost_options || []).length ? c.cost_options : suggestFor(c, shown(p.el) || p.key || '') })),
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
      showFallback(c);   // (it only reads the lists; filling is the Fill step's job, never this)
    };
    // reading the dropdown lists opens them, so it waits until the automatic fill (if any) has finished
    store.get({ auto: false, run: null }).then(({ auto, run }) => { if (!(auto || (run && run.cid === c.customer_id && Date.now() - run.at < 3600000)) && MODE === 'auto') suggestLists(); });
    const files = [...root.querySelectorAll('input[type=file]')].filter(el => !el.disabled).map(el => {
      const own = norm(labelOf(el));   // the box's own label first: a wrapper that holds several boxes must not name this one
      let hit = FILES.find(([re]) => re.test(own));
      if (!hit) {   // a label that is not linked to the box: the nearest label or text just before it
        let near = '', q = el;
        for (let i = 0; i < 4 && q && !near; i++, q = q.parentElement) { let sib = q.previousElementSibling; while (sib && !near) { const t = (sib.innerText || '').trim(); if (t && t.length < 80 && !/^(choose file|browse|upload|select file|view file)$/i.test(t)) near = t; sib = sib.previousElementSibling; } }
        hit = FILES.find(([re]) => re.test(norm(near)));
      }
      if (!hit) { const t = norm((el.closest('tr,.upr,.fg,.form-group') || el.parentElement).innerText); if (t.length < 200) hit = FILES.find(([re]) => re.test(own + ' ' + t)); }
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
    say(head + saved + issueHtml + lackHtml + (fillable.length || files.length || pickable.length || radios.length ? btn('solaraFill', (issues.length ? 'Fill anyway: ' : 'Fill ') + `${fillable.length + pickable.length} field(s) for ${esc((c.name || '').split(' ')[0])}` +
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
    if (!fill) { delete ISL.actions.fill; return; }
    ISL.actions.fill = () => fill.onclick && fill.onclick();
    ISL.actions.fillOne = k => fillOne(c, k);
    if (MODE === 'manual') {   // show every value this screen can take; nothing is filled until the person presses
      ISL.cust = { name: c.name, id: c.customer_id }; ISL.steps = [];
      const keys = [...customs.map(x => [x.key, shown(x.el)]), ...plan.filter(p => p.key && has(c.values[p.key]) && !p.el.value).map(p => [p.key, shown(p.el)]), ...radios.filter(g => has(c.values[g.key]) && !g.rs.some(r => r.checked)).map(g => [g.key, g.q]), ...(certBox(root) && !certBox(root).checked ? [['certify', 'Equipment certification']] : [])];
      ISL.tiles = keys.filter(([k], i) => keys.findIndex(z => z[0] === k) === i).map(([k, l]) => ({ k, l, v: k === 'certify' ? 'tick' : String(c.values[k] || ''), s: '' }));
      ISL.open = true; ISL.fresh = true; ISL.phase = 'waiting';
      tip(`Manual: ${ISL.tiles.length} value(s) ready. Press Fill next to one, or Fill now for all.`, 'idle');
    }
    const fillAll = async () => {
      let filled = 0, kept = 0, attached = 0;
      const left = [], done = [], failed = [];
      // live status on the island: one tile per value, each goes blue (typing), then green (done) or amber (needs you)
      ISL.phase = 'filling'; ISL.cust = { name: c.name, id: c.customer_id }; ISL.steps = [];
      ISL.tiles = [...customs.map(x => ({ k: x.key, l: shown(x.el), v: String(c.values[x.key] || ''), s: '' })),
        ...plan.filter(p => p.key && has(c.values[p.key])).map(p => ({ k: p.key, l: shown(p.el), v: String(c.values[p.key]), s: '' })),
        ...radios.filter(g => has(c.values[g.key])).map(g => ({ k: g.key, l: g.q, v: String(c.values[g.key]), s: '' })),
        ...(certBox(root) ? [{ k: 'certify', l: 'Equipment certification', v: 'tick', s: '' }] : [])];
      ISL.open = true; ISL.fresh = true; islandRender();
      // dropdowns first, top to bottom: a later box (District) often waits for the one above it (State)
      const total = customs.length + plan.filter(p => p.key && has(c.values[p.key])).length; let stepNo = 0;
      for (const { el, key } of customs) {
        const label = shown(el);
        stepNo += 1; tip(`Filling ${esc(label)} (${stepNo} of ${total})`, 'busy', 0, (stepNo - 1) / total);
        el.scrollIntoView({ block: 'center', behavior: 'auto' }); await sleep(PACE.step / 2);
        if (!isEmpty(el)) { kept += 1; continue; }   // someone already chose; theirs stays
        tileSet(key, 'doing');
        if (await pickCustom(el, c.values[key])) { filled += 1; done.push(label); tileSet(key, 'ok'); await sleep(PACE.step); }
        else {
          tileSet(key, 'warn', 'choose below');
          const cands = lastCands.slice(), want = norm(c.values[key]);
          const several = cands.filter(o => norm(o).includes(want) || want.includes(norm(o))).length > 1;
          left.push(`${label} (${several ? 'several match; choose below' : 'choose below'})`);
          fallbackItems.push({ type: 'select', el, key, label, options: cands.length ? cands : null,
            why: several ? `several options match “${c.values[key]}”` : `“${c.values[key]}” is not in the list` });
        }
      }
      let caFilled = false;
      const fillTexts = async () => {
        for (const p of plan) {
          let { el } = p; const { key } = p;
          if (key === null) continue; // OTP, CAPTCHA: the person types these
          if (!el.isConnected) el = (key && freshInput(key)) || el;   // the portal re-drew it: use the one on the page now
          const label = shown(el);
          if (!key || !has(c.values[key])) { if (!el.value) left.push(label); continue; }
          // never overwrite what a person typed or chose
          if ((el.value && el.tagName !== 'SELECT') || el.dataset.solaraHuman) { kept += 1; continue; }
          if (key === 'consumer_no' && !el.value) { tip('The portal needs a moment. The consumer number is next…', 'busy', 0, stepNo / total); await sleep(PACE.settle); }   // let the portal settle after the dropdowns
          if (!total || stepNo < total) { stepNo += 1; tip(`Filling ${esc(label)} (${stepNo} of ${total})`, 'busy', 0, (stepNo - 1) / total); }
          tileSet(key, 'doing');
          const ok = el.tagName === 'SELECT' ? setVal(el, c.values[key]) : await typeInto(el, c.values[key]);
          if (ok && (el.tagName === 'SELECT' || el.value === String(c.values[key]) || (/^[\d.,\s]+$/.test(el.value) && el.value.replace(/[,\s]/g, '') === String(c.values[key]).replace(/[,\s]/g, '')))) { filled += 1; done.push(label); tileSet(key, 'ok'); p.el = el; if (key === 'consumer_no') caFilled = true; await sleep(PACE.step); }
          else { left.push(label); failed.push(label); tileSet(key, 'warn', 'not accepted'); }   // the page refused or changed the value
        }
      };
      for (const g of radios) {   // Yes / No answers: only what Solara knows from the site visit; the rest is left for the person
        if (g.rs.some(r => r.checked)) { kept += 1; continue; }
        if (!has(c.values[g.key])) { left.push(g.q + ' (answer on the page)'); continue; }
        tileSet(g.key, 'doing');
        if (pickRadio(g, c.values[g.key])) { filled += 1; done.push(g.q); tileSet(g.key, 'ok'); await sleep(PACE.step); } else { left.push(g.q); tileSet(g.key, 'warn', 'choose on the page'); }
      }
      const cb = certBox(root);   // the certification box: ticked only when the owner's switch is on
      if (cb && !cb.checked) {
        if ((await store.get({ certify: true })).certify) { tileSet('certify', 'doing'); if (tickCert(cb)) { filled += 1; done.push('Equipment certification'); tileSet('certify', 'ok'); await sleep(PACE.step); } else { left.push('Equipment certification (tick it)'); tileSet('certify', 'warn'); } }
        else left.push('Equipment certification (tick it yourself)');
      }
      await fillTexts();
      c._refill = fillTexts;
      const checkNames = plan.filter(p => (c.derived || []).includes(p.key) && done.includes(labelOf(p.el).split(' | ')[0]))
        .map(p => labelOf(p.el).split(' | ')[0]);
      for (const { el, kind } of files) {
        if (el.files && el.files.length) { kept += 1; continue; }   // a file you chose stays
        attach.err = '';
        const ok = kind === 'quotation' ? await attach(el, { type: 'draft', cid: c.customer_id, kind: 'quotation', fmt: /doc/i.test(el.accept || '') ? '' : 'pdf' })
          : kind === 'agreement' ? await attach(el, agreementReady ? { type: 'file', cid: c.customer_id, key: 'agreement' } : { type: 'draft', cid: c.customer_id, kind: 'agreement' })
          : c.docs.includes(kind) && await attach(el, { type: 'doc', cid: c.customer_id, kind });
        if (ok) attached += 1;
        else {
          left.push(kind + (attach.err ? ` (${attach.err})` : c.docs.includes(kind) || kind === 'agreement' ? ' (could not be fetched from Solara)' : ' (not on file)'));
          el.style.outline = '2px solid #F2A6A0';
          fallbackItems.push({ type: 'file', el, key: null, label: FILE_NAMES[kind] || kind, why: 'not in Solara: choose the file' });
        }
      }
      await retryPending(c, customs);
      await suggestLists();
      await retryPending(c, customs);
      await fillTexts();   // the portal clears the CA number when a dropdown above it changes: fill it last
      // a box can appear after an earlier choice (Urban: Urban Local Body Name; Rural: Block and Panchayat): look again, a few times
      const tried = new WeakSet(customs.map(x => x.el));
      for (let pass = 0; pass < 4; pass++) {
        await sleep(PACE.settle);
        const fresh = customsIn(scope()).filter(x => x.key && !tried.has(x.el) && isEmpty(x.el));
        if (!fresh.length) { if (pass) break; continue; }
        for (const x of fresh) {
          tried.add(x.el);
          if (has(c.values[x.key]) && await pickCustom(x.el, c.values[x.key])) { filled += 1; done.push(x.label); await sleep(PACE.step); continue; }
          const names = (await pickCustom(x.el, '', 'list')) || [], hay = addressText(c), inAddr = names.filter(n => norm(n).length > 3 && hay.includes(norm(n)));
          if (inAddr.length === 1 && await pickCustom(x.el, inAddr[0])) { filled += 1; done.push(x.label); left.push(x.label + ' (chosen from the address: check it)'); continue; }
          fallbackItems.push({ type: 'select', el: x.el, key: x.key, label: x.label, options: names.length ? names : null, suggest: inAddr.slice(0, 3), why: has(c.values[x.key]) ? `“${c.values[x.key]}” is not in the list` : 'Solara has no data' });
          showFallback(c);
        }
      }
      ISL.phase = 'waiting';
      if (!showErrors()) tip(left.length ? `Filled ${filled}. ${left.length} left for you.` : `Filled ${filled}${attached ? ' and attached ' + attached : ''}. Check it, then press <b>Next</b>.`, left.length ? 'warn' : 'ok');
      setTimeout(() => { if (!left.length && !fallbackItems.length && ISL.phase === 'waiting') { ISL.open = false; islandRender(); } }, 3500);
      panel.dataset.filled = String(filled);
      panel.dataset.attached = String(attached);
      fill.outerHTML = `<div id="solaraFilled" style="margin-top:8px"><b>Filled ${filled}${attached ? `, attached ${attached}` : ''}.</b>` +
        (kept ? ` Kept ${kept} you had typed.` : '') +
        (failed.length ? `<br><span style="color:#F2A6A0">The page did not accept: ${esc(failed.join(', '))}</span>` : '') +
        (done.length ? `<div style="margin-top:4px;color:#8FA3B2">Filled: ${esc([...new Set(done)].join(', '))}</div>` : '') +
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
      if ((caFilled || await running()) && (() => { const f = freshInput('consumer_no'); return f && f.value; })()) { tip('Consumer number is in. Pressing <b>Fetch Details</b>…', 'busy'); await sleep(600); }
      if ((caFilled || await running()) && (() => { const f = freshInput('consumer_no'); return f && f.value; })() && openApplyCard('fetch'))
      {
        panel.querySelector('#solaraFilled').insertAdjacentHTML('beforeend', '<div id="solaraFetch" style="margin-top:6px;color:#5FD3A8">Pressed <b>Fetch Details</b>…</div>');
        // the portal answers in a few seconds: details, or "Data not Available" (seen live with an unknown CA number)
        for (let i = 0; i < 30; i++) {
          await sleep(300);
          const dlg = (document.querySelector('.p-dialog, [role=dialog]') || document.body).innerText, note = panel.querySelector('#solaraFetch');
          if (/data\s+not\s+available/i.test(dlg)) {
            note.style.color = '#F2A6A0';
            note.innerHTML = 'The portal has <b>no data for this consumer number</b>. Check the CA number on the bill and type the right one below.';
            const caEl = freshInput('consumer_no');
            tip('The portal has no data for this consumer number. Check it and correct it below.', 'warn');
            if (caEl) { fallbackItems.push({ type: 'text', el: caEl, key: 'consumer_no', label: shown(caEl) || 'Consumer number', why: 'the portal found no data for ' + caEl.value }); showFallback(c); }
            break;
          }
          if (!/fetch\s+details/i.test(dlg) || /^\s*next\s*$/im.test(dlg) && !/please fill required/i.test(dlg)) { note.innerHTML = 'Fetch Details done. Check the details that appear, then press Next yourself.'; break; }
        }
      }
      lastFill = { root, left: [...left], failed: [...failed] };
      await forwardStep();
      ask({ type: 'report', body: { customer_id: c.customer_id, portal: location.host, attached: filled + attached,
        page: location.host + location.pathname, left: [...new Set(left)] } }).then(r => {
        if (!r.ok) panel.querySelector('#solaraFilled').insertAdjacentHTML('beforeend',
          `<br><span style="color:#F2A6A0">Solara could not be told what was filled: ${esc(r.error)}</span>`); });
    };
    fill.onclick = async () => { if (fillBusy) return; fillBusy = true; try { await fillAll(); } finally { fillBusy = false; } };
    // hands-free mode (options page): fill as soon as the page opens, then ask the owner for the
    // OTP / CAPTCHA, which only a person types. Never submits, never types the OTP or CAPTCHA.
    store.get({ auto: false, run: null }).then(({ auto, run }) => {
      const going = run && run.cid === c.customer_id && Date.now() - run.at < 60 * 60 * 1000;
      const onceKey = 'solaraAuto:' + location.pathname + location.hash + ':' + c.customer_id;
      if (MODE === 'auto' && (afterNextGo || ((auto || going) && !issues.length && !sessionStorage.getItem(onceKey) && Date.now() - pbLastRun > 600000))) { sessionStorage.setItem(onceKey, '1'); fill.onclick(); }
    });
  }

  store.get('handoff').then(x => { handoff = x.handoff || null; }).finally(scan);
  try { chrome.storage.onChanged.addListener((ch, area) => {
    if (area === 'local' && ['islandV', 'islandH', 'panelV', 'panelH', 'gap'].some(k => ch[k])) { Object.keys(LAYOUT).forEach(k => { if (ch[k]) LAYOUT[k] = ch[k].newValue; }); applyLayout(); return; }
    if (area !== 'local' || !ch.handoff) return;
    handoff = ch.handoff.newValue || null;
    panel.querySelector('#solaraHandoff')?.remove();
    panel.firstElementChild?.insertAdjacentHTML('afterend', banner());
  }); } catch (e) { /* dead page */ }
  // ---------- vendor portal: open "Site Feasibility Report" from the application's Action menu ----------
  // On the vendor's My Applications: the application's row has a chevron that opens an expansion row; its Action button opens a menu
  // (Upload Agreement, View Application, Site Feasibility Report). Seen on the real portal.
  async function openVendorAction(c, re) {
    const app = c.application_no; if (!app) return false;
    const row = await waitFor(() => [...document.querySelectorAll('tbody tr')].find(r => visible(r) && !panel.contains(r) && (r.innerText || '').includes(app) && r.querySelectorAll('td').length > 3), 6000);
    if (!row) return false;
    const actionBtn = () => { const n = row.nextElementSibling; return n && [...n.querySelectorAll('button')].find(b => visible(b) && /^\s*action\s*$/i.test(b.innerText || '')); };
    if (!actionBtn()) { const chev = row.querySelector('td:last-child button'); if (chev) chev.click(); await waitFor(actionBtn, 4000); }
    const act = actionBtn(); if (!act) return false;
    act.click();
    const item = await waitFor(() => [...document.querySelectorAll('.p-menuitem a,.p-menuitem-link,li[role=menuitem],li a')].find(e => visible(e) && !panel.contains(e) && re.test((e.innerText || '').trim())), 5000);
    if (!item) return false;
    item.click(); return true;
  }
  const openFeasibility = c => openVendorAction(c, /^\s*site feasibility report\s*$/i);
  let sfrBusy = false;
  setInterval(async () => {
    if (sfrBusy || fillBusy || pbActive || !isOwner() || !/^vendor\./.test(location.host)) return;
    if (scope() !== document.body || screenOf(document.body)) return;   // a dialog is already open
    const rec = await recalled(); if (!rec) return;
    let c = null;
    try { const x = JSON.parse(sessionStorage.getItem('solaraCache:' + rec.cid) || 'null'); c = x && x.data; } catch (e) { /* skip */ }
    if (!c) { const r = await ask({ type: 'lookup', cid: rec.cid }); if (r && r.ok) { c = r.data; try { sessionStorage.setItem('solaraCache:' + rec.cid, JSON.stringify({ t: Date.now(), data: c })); } catch (e) { /* skip */ } } }
    if (!c || !c.application_no || !(document.body.innerText || '').includes(c.application_no)) return;
    const key = 'solaraSFR:' + c.application_no;
    if (Date.now() - (+sessionStorage.getItem(key) || 0) < 600000) return;
    sfrBusy = true;
    try {
      sessionStorage.setItem(key, String(Date.now()));
      if (MODE === 'manual') {
        ISL.tiles = [{ k: 'sfr', l: 'Open Site Feasibility Report', v: c.application_no, s: '' }]; ISL.cust = { name: c.name, id: c.customer_id };
        ISL.actions = { fillOne: async () => { tileSet('sfr', 'doing'); tileSet('sfr', (await openFeasibility(c)) ? 'ok' : 'warn'); }, change: () => pick() };
        ISL.open = true; ISL.fresh = true; tip('Manual: open the Site Feasibility Report.', 'idle'); return;
      }
      tip('Opening the Site Feasibility Report…', 'busy', 0, 0.2);
      const ok = await openFeasibility(c);
      if (!ok) tip('I could not open the Site Feasibility Report. Use Action on the application.', 'warn');
    } catch (err) { if (!/newer copy/.test(err && err.message)) tip('Site Feasibility: ' + esc((err && err.message) || err), 'warn'); } finally { sfrBusy = false; }
  }, 1800);
  // ---------- Find A Vendor: search the vendor, pick it from the list, press Select Vendor ----------
  const OURS_SEL = '#solaraToast,#solaraPanel,#solaraFallback';
  const textBoxes = () => [...document.querySelectorAll('input,textarea,[contenteditable=true]')].filter(el => visible(el) && !el.readOnly && !el.disabled &&
    !['hidden', 'checkbox', 'radio', 'submit', 'button', 'file', 'password', 'number', 'date'].includes(el.type) && !el.closest('.p-dropdown,.p-select,.p-multiselect') && !el.closest(OURS_SEL));
  const vendorBox = () => {
    const boxes = textBoxes();
    // 1. under the "Search Vendor" heading, whatever tag it is in: the nearest text box below it
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let h = null;
    while (w.nextNode()) { const n = w.currentNode; if (/^\s*search vendor\s*$/i.test(n.nodeValue) && n.parentElement && visible(n.parentElement) && !n.parentElement.closest(OURS_SEL)) h = n.parentElement; }
    if (h) {
      const hr = h.getBoundingClientRect();
      const near = boxes.map(el => ({ el, r: el.getBoundingClientRect() })).filter(x => x.r.top >= hr.bottom - 8 && x.r.top - hr.bottom < 220 && x.r.left < hr.left + 400).sort((p, q) => p.r.top - q.r.top)[0];
      if (near) return near.el;
    }
    // 2. a box that says "Search" in the left sidebar, below the page header
    return boxes.filter(el => { const r = el.getBoundingClientRect(); return /search/i.test([el.placeholder, el.getAttribute('aria-label'), el.name, el.id].join(' ')) && r.left < window.innerWidth * 0.4 && r.top > 120; })
      .sort((p, q) => p.getBoundingClientRect().top - q.getBoundingClientRect().top)[0] || null;
  };
  const vendorTerm = async () => (((await store.get({ vendorSearch: 'SOLARSEA ELECTROTECH SOLUTIONS PVT LTD' })).vendorSearch) || 'SOLARSEA ELECTROTECH SOLUTIONS PVT LTD').trim();
  // the "Select Vendor" buttons whose own card (the smallest block holding just that one button) names the vendor
  const vendorCards = term => {
    const all = [...document.querySelectorAll('button,[role=button]')].filter(b => visible(b) && !panel.contains(b) && /^\s*select\s+vendor\s*$/i.test((b.innerText || '').trim()));
    return all.filter(b => {
      let card = b;
      while (card.parentElement && card.parentElement !== document.body && all.filter(x => card.parentElement.contains(x)).length === 1) card = card.parentElement;
      return norm(card.innerText).includes(norm(term));
    });
  };
  async function vendorSearchStep(term) {
    tileSet('vendor', 'doing');
    const el = vendorBox(); if (!el) { tileSet('vendor', 'warn', 'search box not found'); return false; }
    if (!norm(el.value).includes(norm(term))) { setVal(el, ''); await typeInto(el, term); }
    // either a list of suggestions appears (click the line), or the page filters its cards while typing (one card is left)
    const got = await waitFor(() => [...document.querySelectorAll('li,[role=option],.p-autocomplete-item,.dropdown-item,.autocomplete-item,.suggestion')]
      .find(o => visible(o) && !panel.contains(o) && norm(o.innerText).includes(norm(term)) && (o.innerText || '').length < 120) || (vendorCards(term).length === 1 ? 'cards' : null), 8000);
    const hit = got && got !== 'cards' ? got : null;
    if (hit) { realClick(hit); await sleep(PACE.step * 3); }
    const ok = !!hit || vendorCards(term).length === 1;
    tileSet('vendor', ok ? 'ok' : 'warn', ok ? null : 'not in the list');
    return ok;
  }
  async function vendorSelectStep(term) {
    tileSet('select', 'doing');
    const b = await waitFor(() => { const c = vendorCards(term); return c.length === 1 ? c[0] : null; }, 8000);
    if (!b) { tileSet('select', 'warn', 'not exactly one match: press it yourself'); return false; }
    await sleep(PACE.step); realClick(b); tileSet('select', 'ok', 'pressed'); return true;
  }
  // Screen awareness: the island says which screen it recognises while it is idle.
  const SCREEN_NAMES = [[/#\/signed-in\/find-vendor/i, 'Find A Vendor', 'url'], [/find a vendor/i, 'Find A Vendor'], [/consumer request list/i, 'Consumer Request List'], [/my application/i, 'My Application']];
  let lastAware = '';
  setInterval(() => {
    if (!isOwner() || fillBusy || pbActive || vendorBusy || ISL.kind === 'busy') return;
    const t = document.body.innerText || '';
    const name = startModal() ? 'Start a new Application' : (screenOf(document.body) || {}).name || (SCREEN_NAMES.find(([re, , url]) => re.test(url ? location.href : t)) || [])[1] || '';
    if (name && name !== lastAware && ISL.kind === 'idle') { lastAware = name; tip(`Screen: ${esc(name)}`, 'idle'); }
    else if (!name) lastAware = '';
  }, 2000);
  let vendorBusy = false;
  setInterval(async () => {
    if (vendorBusy || !isOwner()) return;
    const onFind = /#\/signed-in\/find-vendor/i.test(location.href) || /find a vendor/i.test(document.body.innerText);
    if (!onFind) return;
    if (fillBusy || pbActive) { if (/find-vendor/i.test(location.href)) { fillBusy = false; pbActive = false; } else return; }   // a stale run from the earlier box must not hold this screen
    if (!vendorBox()) {
      if (Date.now() - (+sessionStorage.getItem('solaraVendorWarn') || 0) > 30000) { sessionStorage.setItem('solaraVendorWarn', String(Date.now())); ISL.open = true; ISL.fresh = true; tip(`Find A Vendor: I cannot see the Search Vendor box yet (${textBoxes().length} text boxes on the page).`, 'warn'); }
      return;
    }
    const key = 'solaraVendor:' + location.href;
    if (Date.now() - (+sessionStorage.getItem(key) || 0) < 600000) return;   // done once; a failed try may repeat after 20 s; Retry repeats at once
    vendorBusy = true;
    try {
      sessionStorage.setItem(key, String(Date.now() - 580000));   // counts as done only when Select Vendor was pressed
      const term = await vendorTerm();
      ISL.pend = null; ISL.steps = [];
      ISL.tiles = [{ k: 'vendor', l: 'Search vendor', v: term, s: '' }, { k: 'select', l: 'Select Vendor button', v: 'press it', s: '' }];
      ISL.actions = { retry: () => { sessionStorage.removeItem(key); }, change: () => pick() };
      if (MODE === 'manual') {
        ISL.actions.fillOne = k => k === 'vendor' ? vendorSearchStep(term) : vendorSelectStep(term);
        ISL.open = true; ISL.fresh = true; tip('Manual: search the vendor, then press Select Vendor.', 'idle'); return;
      }
      ISL.open = true; ISL.fresh = true; ISL.phase = 'filling';
      tip(`Find A Vendor. Searching “${esc(term)}”…`, 'busy', 0, 0.1);
      const ok = (await vendorSearchStep(term)) && (await vendorSelectStep(term));
      ISL.phase = 'waiting'; if (ok) sessionStorage.setItem(key, String(Date.now()));
      tip(ok ? 'Vendor selected. Continue on the next screen.' : 'I could not select the vendor by myself. Do it on the page.', ok ? 'ok' : 'warn');
    } catch (err) { /* a newer copy took over */ } finally { vendorBusy = false; }
  }, 600);
  // The island's button: search the vendor and press Select Vendor now, whatever the earlier tries did.
  async function runVendorNow() {
    if (vendorBusy) return;
    vendorBusy = true;
    try {
      const term = await vendorTerm();
      ISL.pend = null; ISL.steps = [];
      ISL.tiles = [{ k: 'vendor', l: 'Search vendor', v: term, s: '' }, { k: 'select', l: 'Select Vendor button', v: 'press it', s: '' }];
      ISL.open = true; ISL.fresh = true; ISL.phase = 'filling';
      tip(`Searching “${esc(term)}”…`, 'busy', 0, 0.15);
      const ok = (await vendorSearchStep(term)) && (await vendorSelectStep(term));
      ISL.phase = 'waiting'; if (ok) sessionStorage.setItem('solaraVendor:' + location.href, String(Date.now()));
      tip(ok ? 'Vendor selected. Continue on the next screen.' : 'I could not find or select the vendor. Check the search box, or do it on the page.', ok ? 'ok' : 'warn');
    } catch (err) { /* a newer copy took over */ } finally { vendorBusy = false; }
  }
  // ---------- consumer login: the mobile number is filled for the chosen customer; the CAPTCHA and the OTP are the person's ----------
  const loginBoxes = () => {
    const ins = [...document.querySelectorAll('input')].filter(el => visible(el) && !el.closest(OURS_SEL) && !['hidden', 'checkbox', 'radio', 'submit', 'button', 'file'].includes(el.type));
    const mob = ins.find(el => !el.readOnly && !el.disabled && !humanOnly(el) && ruleFor(labelOf(el)) === 'mobile');
    const human = ins.filter(el => humanOnly(el) && !el.readOnly && !el.disabled);
    return mob && (human.length || /captcha|otp/i.test(document.body.innerText)) ? { mob, human } : null;
  };
  let loginBusy = false, loginAsked = false;
  setInterval(async () => {
    if (loginBusy || !isOwner() || !/^consumer\./.test(location.host) || /signed-in/i.test(location.href)) return;
    const b = loginBoxes(); if (!b) { loginAsked = false; return; }
    const key = 'solaraLogin:' + location.href;
    if (Date.now() - (+sessionStorage.getItem(key) || 0) < 120000) return;
    loginBusy = true;
    try {
      const rec = await recalled();
      if (!rec) { if (!loginAsked) { loginAsked = true; await pick(); } return; }   // who is logging in? asked once
      let c = null;
      try { const x = JSON.parse(sessionStorage.getItem('solaraCache:' + rec.cid) || 'null'); c = x && x.data; } catch (e) { /* skip */ }
      if (!c) { const r = await ask({ type: 'lookup', cid: rec.cid }); if (r && r.ok) { c = r.data; try { sessionStorage.setItem('solaraCache:' + rec.cid, JSON.stringify({ t: Date.now(), data: c })); } catch (e) { /* skip */ } } }
      if (!c) return;
      sessionStorage.setItem(key, String(Date.now()));
      const mobile = digits(c.values && c.values.mobile).slice(-10);
      ISL.pend = null; ISL.steps = []; ISL.cust = { name: c.name, id: c.customer_id };
      ISL.tiles = [{ k: 'mobile', l: 'Mobile number', v: mobile, s: '' }, { k: 'human', l: 'CAPTCHA and OTP', v: 'you type these', s: '' }];
      ISL.actions = { change: () => pick(), retry: () => sessionStorage.removeItem(key) };
      ISL.open = true; ISL.fresh = true;
      if (!/^[6-9]\d{9}$/.test(mobile)) { tileSet('mobile', 'warn', 'not in Solara'); tip('Consumer login: Solara has no mobile number for this customer. Type it yourself.', 'warn'); return; }
      if (MODE === 'manual') { ISL.actions.fillOne = k => { if (k !== 'mobile') return; const el = loginBoxes()?.mob; if (el) { tileSet('mobile', 'doing'); typeInto(el, mobile).then(ok => { tileSet('mobile', ok ? 'ok' : 'warn'); if (ok) { const h = loginBoxes()?.human[0]; if (h) h.focus(); } }); } };
        tip('Consumer login: press Fill for the mobile number.', 'idle'); return; }
      tip('Consumer login: filling the mobile number…', 'busy', 0, 0.3);
      tileSet('mobile', 'doing');
      if (digits(b.mob.value) !== mobile) { setVal(b.mob, ''); await typeInto(b.mob, mobile); }
      const ok = digits(b.mob.value) === mobile;
      tileSet('mobile', ok ? 'ok' : 'warn', ok ? null : 'not accepted');
      tileSet('human', 'doing');
      if (b.human[0]) b.human[0].focus();
      tip(ok ? 'Mobile number is in. Type the CAPTCHA, press Send OTP, then type the OTP. I wait for you.' : 'The portal did not take the mobile number. Type it yourself, then the CAPTCHA and the OTP.', ok ? 'ok' : 'warn');
    } catch (err) { /* a newer copy took over */ } finally { loginBusy = false; }
  }, 1200);
  // Next pressed: if the portal refuses, say why. A new screen is found by the watcher below.
  document.addEventListener('click', e => {
    const b = e.target && e.target.closest && e.target.closest('button,[role=button],input[type=submit]');
    if (!b || panel.contains(b) || !isOwner()) return;
    if (!/^\s*(next|save\s*(&|and)\s*(continue|next)|continue)\s*$/i.test(((b.innerText || b.value || '') + '').trim())) return;
    setTimeout(() => { if (!showErrors() && !fillBusy) tip('Looking for the next screen…', 'busy'); }, 700);
  }, true);
  // The screen watcher: each new screen of the application form is filled by itself 2 seconds after it appears,
  // with the status live on the island. One fill per screen and address; the island's Fill button can repeat it.
  let watchBusy = false;
  setInterval(async () => {
    if (watchBusy || fillBusy || pbActive || !isOwner() || startModal()) return;
    const sc = screenOf(document.body); if (!sc) return;
    const sig = sc.name + '|' + location.href; if (screensDone.has(sig)) return;
    watchBusy = true;
    try {
      if (!(await recalled()) && sc.name !== 'Upload Agreement') return;   // the Upload Agreement dialog names its own customer
      screensDone.add(sig);
      if (MODE === 'manual') { await scan(); return; }
      ISL.phase = 'filling'; tip(`Found <b>${esc(sc.name)}</b>. Filling in 2 seconds…`, 'busy', 0, 0.05);
      await sleep(2000);
      if (!screenOf(document.body)) { screensDone.delete(sig); return; }
      afterNextGo = true; await scan();
      setTimeout(() => { afterNextGo = false; }, 6000);
    } catch (err) { /* a newer copy took over */ } finally { watchBusy = false; }
  }, 1200);
  // single-page portals change screens without reloading; read the page again when they do
  let last = location.href;
  setInterval(() => { if (location.href !== last) { last = location.href; setTimeout(scan, 800); } }, 700);
})();
