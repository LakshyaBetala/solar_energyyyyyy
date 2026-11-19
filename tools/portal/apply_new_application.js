/* Replays the procedure recorded on the live PM Surya Ghar consumer login (13 Nov 2026):
 *   Home -> "Apply for Solar Rooftop" card -> "Start a new Application" dialog ->
 *   State -> District (unlocks after State) -> Electricity Distribution Company -> CA No. -> Fetch Details.
 * It stops there: it never presses Next, Submit, or touches OTP / CAPTCHA. The owner checks the details
 * the portal fetches and presses Next.
 *
 * Use (in the page's console, or from Playwright's page.evaluate):
 *   window.SOLARA_VALUES = { state: 'Maharashtra', district: 'Nashik',
 *                            discom: 'Maharashtra State Electricity Distribution Co. Ltd.', consumer_no: '170038865021' };
 *   then run this file. It resolves to { ok, log, needs } where `needs` lists what the owner must do
 *   (a value Solara lacks, an option that did not match, or "Data not Available" after Fetch Details).
 * The same steps are built into extension/panel.js; this file is the recording in runnable form.
 */
(async () => {
  const V = window.SOLARA_VALUES || {};
  const log = [], needs = [];
  const t0 = performance.now(), mark = (step, detail) => log.push({ ms: Math.round(performance.now() - t0), step, detail });
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const norm = s => String(s ?? '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  const OPTS = '.p-dropdown-panel li[role=option], .p-select-overlay li[role=option]';
  const optName = o => (o.getAttribute('aria-label') || o.innerText || '').trim();
  const press = re => [...document.querySelectorAll('button,[role=button]')].find(b => vis(b) && !b.disabled && re.test((b.innerText || '').trim()));

  // 1. home page: open the card (only if the dialog is not already open)
  if (!document.querySelector('.p-dialog, [role=dialog]')) {
    const card = [...document.querySelectorAll('a,button,[role=button],div,span,h1,h2,h3,h4,p')]
      .filter(e => vis(e) && /apply\s+for\s+(a\s+)?solar\s+roof\s*top/i.test(e.innerText || '') && (e.innerText || '').length < 120)
      .sort((a, b) => a.innerText.length - b.innerText.length)[0];
    if (!card) return { ok: false, log, needs: ['Open the portal home page ("Apply for Solar Rooftop" card not found)'] };
    (card.closest('a,button,[role=button],[routerlink],.card,[class*=card]') || card).click();
    mark('opened the Apply for Solar Rooftop card');
    for (let i = 0; i < 30 && !document.querySelector('.p-dialog, [role=dialog]'); i++) await sleep(150);
  }

  // 2. a PrimeNG dropdown by its position in the dialog: pick the one option that matches, else report
  async function pick(nth, label, value) {
    const box = [...document.querySelectorAll('.p-dialog p-dropdown, [role=dialog] p-dropdown')].filter(vis)[nth];
    if (!box) { needs.push(`${label}: the dropdown was not found`); return false; }
    if (!value) { needs.push(`${label}: Solara has no value; choose it`); return false; }
    for (let i = 0; i < 25 && (box.matches('.p-disabled,.disable-input') || box.querySelector('[aria-disabled=true]')); i++) await sleep(150);  // District waits for State
    for (let i = 0; i < 15 && [...document.querySelectorAll(OPTS)].some(vis); i++) await sleep(100);   // the previous list is still closing
    (box.querySelector('.p-dropdown-label') || box).dispatchEvent(new MouseEvent('click', { bubbles: true }));
    let opts = [];
    for (let i = 0; i < 25 && !opts.length; i++) { await sleep(150); opts = [...document.querySelectorAll(OPTS)].filter(vis); }
    const want = norm(value), names = opts.map(optName);
    let hit = opts.filter(o => norm(optName(o)) === want);
    if (hit.length !== 1) hit = opts.filter(o => { const n = norm(optName(o)); return n.length > 3 && (n.includes(want) || want.includes(n)); });
    mark(`${label}: list of ${names.length}`, { matches: hit.length });
    if (hit.length !== 1) {   // none or several: close the list and hand the choices to the owner
      if ([...document.querySelectorAll(OPTS)].some(vis)) (box.querySelector('.p-dropdown-label') || box).dispatchEvent(new MouseEvent('click', { bubbles: true }));
      needs.push(`${label}: ${hit.length ? 'several options match' : 'no option matches'} "${value}"; choose from ${names.slice(0, 8).join(', ')}${names.length > 8 ? ', ...' : ''}`);
      return false;
    }
    hit[0].dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await sleep(400);
    mark(`${label}: picked`, box.querySelector('.p-dropdown-label').innerText.trim());
    return true;
  }
  await pick(0, 'State', V.state);
  await pick(1, 'District', V.district);
  await pick(2, 'Electricity Distribution Company', V.discom);

  // 3. the consumer account number, typed the way the page's framework notices
  const ca = [...document.querySelectorAll('input')].find(i => /consumer account number/i.test(i.placeholder || ''));
  if (!ca || !V.consumer_no) needs.push('Consumer Account Number: Solara has no value; type it');
  else {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(ca, V.consumer_no);
    ['input', 'change', 'blur'].forEach(t => ca.dispatchEvent(new Event(t, { bubbles: true })));
    mark('typed the consumer number');
    await sleep(400);
    // 4. Fetch Details loads the bill's data into the form; nothing is submitted
    const fetchBtn = press(/^fetch\s+details$/i);
    if (fetchBtn) {
      fetchBtn.click(); mark('pressed Fetch Details');
      for (let i = 0; i < 30; i++) {
        await sleep(300);
        const d = (document.querySelector('.p-dialog, [role=dialog]') || document.body).innerText;
        if (/data\s+not\s+available/i.test(d)) { needs.push('The portal has no data for this consumer number. Check the CA number on the bill'); break; }
        if (!/fetch\s+details/i.test(d) || press(/^next$/i)) { mark('details loaded'); break; }
      }
    } else needs.push('Fetch Details was not available (a field above is still empty)');
  }
  return { ok: !needs.length, log, needs };
})();
