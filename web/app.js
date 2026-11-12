/* Solara dashboard. Every panel is fed by the API; the browser pane shows real JPEG
   frames streamed off the Chromium session the agent is driving. */
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const ROLES = { viewer: 0, operator: 1, supervisor: 2 };

const STAGES = [
  ['lead', 'Lead captured', 'idle'], ['docs', 'Documents pending', 'warn'],
  ['register', 'Portal registration', 'info'], ['feasible', 'DISCOM feasibility', 'info'],
  ['install', 'Installation', 'live'], ['netmeter', 'Net metering', 'info'],
  ['claim', 'Subsidy claim filed', 'live'], ['disbursed', 'Subsidy disbursed', 'ok']
];
const stage = k => STAGES.find(s => s[0] === k) || STAGES[0];

const TITLES = {
  inst: ['Installation', 'Agreement uploaded to six documents on MSEDCL: feasibility report, loan, field photos and serials, DCR, the 5 installation steps.'],
  pipeline: ['Pipeline', 'Every live application and the stage it is sitting at.'],
  run: ['Agent Runs', 'A real browser session filing an application. It stops for OTP, CAPTCHA, corrections and approval.'],
  docs: ['Document Intake', 'Parses the actual PDFs on disk and flags anything that does not agree. Drop in your own bill to try it.'],
  today: ['Today', 'What to do now, for every customer. Do the top line first.'],
  reg: ['Registration', 'From the customer’s documents to the customer approving the agreement on PM Surya Ghar.'],
  closeout: ['Close-out', 'Installation done to six MSEDCL documents: enter it once, the customer e-signs, the co-pilot attaches the files.'],
  numbers: ['Number Pool', 'One dedicated mobile number per registration, held for 90 days.'],
  calls: ['AI Calling', 'Reminder, status and scheduling calls in Marathi, Hindi and English.'],
  audit: ['Audit Trail', 'Who did what, and when. Append-only, written by the server.'],
  reports: ['Reports', 'How each milestone stands, the owner’s time, backups and people, and the exports.']
};

const S = {
  view: 'today', me: null, today: null, board: null, inst: [], instCid: null, instData: null, customers: [], numbers: [], calls: [], audit: [], llm: {},
  runs: [], activeRun: null, callSel: 0, showEn: true, docCid: 'SS-2045', extract: null,
  reports: null, steps: [], events: [], shots: [], hold: null, runStatus: 'idle', speed: 1,
  headless: true, es: null, lastFrame: null, t0: null,
  runCid: 'SS-2045', runWf: null, runKw: null, workflows: [], followups: [],
  co: [], coCid: 'SS-2042', coData: null, reg: [], regCid: null, regData: null
};

const can = lvl => S.me && ROLES[S.me.role] >= ROLES[lvl];

/* ------------------------------ transport ------------------------------ */
async function api(path, opts = {}) {
  const r = await fetch('/api' + path, {
    method: opts.method || 'GET',
    headers: opts.body ? { 'Content-Type': 'application/json' } : {},
    body: opts.body ? JSON.stringify(opts.body) : undefined
  });
  if (r.status === 401) { S.me = null; showGate('Your session expired. Sign in again.'); throw new Error('unauthorised'); }
  const txt = await r.text();
  let data; try { data = txt ? JSON.parse(txt) : null; } catch { data = txt; }
  if (!r.ok) { const err = new Error((data && data.detail) || r.statusText); err.status = r.status; err.data = data; throw err; }
  return data;
}

let toastT;
function toast(msg, bad) {
  $('#toastmsg').textContent = msg;
  $('#toast').hidden = false;
  $('#toast').classList.toggle('bad', !!bad);
  clearTimeout(toastT); toastT = setTimeout(() => { $('#toast').hidden = true; }, 4200);
}
function modal(title, sub, body, foot) {
  $('#mtitle').textContent = title; $('#msub').textContent = sub;
  $('#mbody').innerHTML = body; $('#mfoot').innerHTML = foot;
  $('#scrim').hidden = false;
}
const closeModal = () => { $('#scrim').hidden = true; };

/* ------------------------------ sign in ------------------------------ */
function showGate(err) {
  $('#gate').hidden = false; $('#shell').hidden = true;
  $('#gateErr').hidden = !err; $('#gateErr').textContent = err || '';
  if (S.es) { S.es.close(); S.es = null; }
}
async function login(username, password) {
  try {
    S.me = await api('/login', { method: 'POST', body: { username, password } });
    $('#gate').hidden = true; $('#shell').hidden = false;
    await boot();
  } catch (e) { showGate(e.message); }
}

/* ------------------------------ boot ------------------------------ */
async function boot() {
  S.view = 'today';  // every sign-in starts the day on what to do now; a click while the data loads still wins
  if (!$('#runview')) { // before any request: a click while the data loads must find its containers
    $('#work').innerHTML = `<div id="runview" hidden></div><div id="otherview"></div>`;
    $('#runview').innerHTML = runView();
  }
  const b = await api('/bootstrap');
  S.me = b.user; S.customers = b.customers; S.numbers = b.numbers; S.calls = b.calls;
  S.audit = b.audit; S.llm = b.llm; S.runs = b.runs; S.activeRun = b.active_run;
  S.workflows = b.workflows || [];
  S.followups = await api('/followups').catch(() => []);
  S.co = await api('/closeout').catch(() => []);
  S.reg = await api('/registration').catch(() => []);
  S.inst = await api('/filing').catch(() => []);
  [S.today, S.board] = await Promise.all([api('/today').catch(() => null), api('/board').catch(() => null)]);
  $('#whoName').textContent = S.me.name;
  $('#whoRole').textContent = S.me.role;
  $('#llmChip').innerHTML = S.llm.enabled
    ? `<span class="dot on"></span>Model <b>${esc(S.llm.provider)}</b>`
    : `<span class="dot"></span>Model <b>off</b>`;
  $('#llmChip').title = S.llm.enabled
    ? `Extraction also runs through ${S.llm.provider}/${S.llm.model}`
    : 'No API key configured; extraction uses the deterministic parser only';
  counters();
  if (!$('#runview')) {
    $('#work').innerHTML = `<div id="runview" hidden></div><div id="otherview"></div>`;
    $('#runview').innerHTML = runView();
  }
  if (S.activeRun) { attachRun(S.activeRun); S.view = 'run'; }
  render();
  loadToday();
}

function counters() {
  $('#tagPipe').textContent = S.customers.length;
  $('#tagNum').textContent = S.numbers.length;
  $('#tagCalls').textContent = S.calls.length;
  const flagged = S.customers.reduce((a, c) => a + (c.flagged || 0), 0);
  $('#tagDocs').textContent = flagged;
  $('#tagDocs').className = 'tag' + (flagged ? ' hot' : '');
  $('#tagAudit').textContent = S.audit.length;
  $('#tagCo').textContent = S.co.filter(x => !x.uploaded).length;
  $('#tagReg').textContent = S.reg.filter(x => x.done < x.total).length;
  $('#tagInst').textContent = (S.inst || []).filter(x => x.done < x.total).length;
  if (S.today && $('#tagToday')) $('#tagToday').textContent = S.today.calls.length + S.today.todo.length + S.today.portal.length;
  const live = ['running', 'held', 'paused', 'starting'].includes(S.runStatus);
  $('#tagRun').textContent = live ? (S.runStatus === 'held' ? 'held' : 'live') : S.runStatus;
  $('#tagRun').className = 'tag' + (live ? ' live' : S.runStatus === 'failed' || S.runStatus === 'stopped' ? ' hot' : '');
}

/* ------------------------------ render ------------------------------ */
const VIEWS = {};
// what the owner has typed but not saved survives any redraw of the same customer's screen
const drafts = new Map();
const curCid = () => ({ inst: S.instCid, reg: S.regCid, closeout: S.coCid })[S.view];
const draftKey = el => { for (const a of ['i', 'r', 'f']) if (el.dataset && el.dataset[a]) return `${S.view}:${curCid()}:${a}:${el.dataset[a]}`; return null; };
const keepDraft = e => { const k = draftKey(e.target); if (k) drafts.set(k, e.target.value); };
document.addEventListener('input', keepDraft);
document.addEventListener('change', keepDraft);
document.addEventListener('change', async e => {
  const who = e.target.dataset && e.target.dataset.urole;
  if (!who) return;
  try { S.users = await api('/users', { method: 'POST', body: { username: who, role: e.target.value } }); toast(`${who} is now ${e.target.value}`); }
  catch (err) { toast(err.message, true); render(); }
});
const clearDrafts = () => { const pre = `${S.view}:${curCid()}:`; [...drafts.keys()].filter(k => k.startsWith(pre)).forEach(k => drafts.set(k, undefined)); };
function render() {
  if (!S.me || !$('#otherview')) return;
  $('#crumb').textContent = TITLES[S.view][0];
  $('#crumbsub').textContent = TITLES[S.view][1];
  $$('.navitem').forEach(b => b.setAttribute('aria-current', String(b.dataset.view === S.view)));
  const rv = $('#runview'), ov = $('#otherview');
  rv.hidden = S.view !== 'run'; ov.hidden = S.view === 'run';
  if (S.view === 'run') { runHead(); paintSteps(); paintShots(); paintRunState(); }
  else {
    ov.innerHTML = VIEWS[S.view]();
    $$('#otherview [data-i],#otherview [data-r],#otherview [data-f]').forEach(el => { const v = drafts.get(draftKey(el)); if (v !== undefined) el.value = v; });
    if (S.view === 'calls') playTranscript(false);
  }
  counters();
}

/* ------------------------------ pipeline ------------------------------ */
VIEWS.pipeline = () => {
  const c = S.customers;
  const filed = c.filter(x => x.application_no).length;
  const value = c.reduce((a, x) => a + (x.subsidy || 0), 0);
  const counts = STAGES.map(s => [s[1], c.filter(x => x.stage === s[0]).length]);
  const mx = Math.max(1, ...counts.map(x => x[1]));
  const done = S.runs.filter(r => r.status === 'done').length;
  return `<div class="grid" style="gap:14px">${boardCard()}
  <div class="kpis">
    <div class="kpi"><div class="k">Applications live</div><div class="v num">${c.length}</div>
      <div class="d">${filed} filed &middot; ${c.filter(x => x.discom_ref).length} with the DISCOM</div></div>
    <div class="kpi"><div class="k">Agent runs completed</div><div class="v num">${done}</div>
      <div class="d">${S.runs.length} started in this environment</div></div>
    <div class="kpi"><div class="k">Needs attention</div><div class="v num">${S.followups.length}</div>
      <div class="d">${S.followups.filter(f => f.sev === 'bad').length} urgent</div></div>
    <div class="kpi"><div class="k">Subsidy in flight</div><div class="v">&#8377;${(value / 1000).toFixed(0)}<span>k</span></div>
      <div class="d">across ${c.filter(x => x.subsidy > 0).length} households</div></div>
  </div>

  <div class="two">
    <div class="card"><div class="ch"><h3>Stage distribution</h3></div>
      <div class="cb" style="display:grid;gap:2px">${counts.map(([n, v]) =>
    `<div class="stagebar"><div class="nm">${n}</div><div class="tk"><i style="width:${v / mx * 100}%"></i></div><div class="ct">${v}</div></div>`).join('')}</div></div>
    <div class="card"><div class="ch"><h3>Needs attention</h3><span class="spacer"></span>
      <span class="hint">derived from live data, worst first</span></div>
      <div class="cb fus">${S.followups.length ? S.followups.map(f => `
        <div class="fu ${f.sev}"><span class="pill ${f.sev === 'bad' ? 'bad' : f.sev === 'warn' ? 'warn' : 'info'} mono">${esc(f.cid)}</span>
          <div style="min-width:0"><div>${esc(f.title)}</div><div class="sub">${esc(f.action)}</div></div></div>`).join('')
    : '<div class="hint">Nothing needs a person right now.</div>'}</div></div>
  </div>

  <div class="card raise"><div class="ch"><h3>Application pipeline</h3><span class="spacer"></span>
    <button class="btn sm" id="xlsx">Download Excel</button></div>
    <div class="tscroll"><table>
      <thead><tr><th>Ref</th><th>Customer</th><th>Consumer no.</th><th>Capacity</th><th>Stage</th>
        <th>Docs</th><th>Assigned number</th><th>Updated</th><th></th></tr></thead>
      <tbody>${c.map(x => { const s = stage(x.stage); return `<tr${x.blocked_note ? ' data-sev="warn"' : ''}>
        <td class="mono" style="color:var(--fg-dim);white-space:nowrap">${x.id}</td>
        <td><div class="who2">${esc(x.name)}</div><div class="sub">${esc(x.place)} &middot; ${esc(x.category)}</div></td>
        <td class="mono">${x.consumer_no || '<span class="sub">no connection</span>'}</td><td class="mono">${x.kw}&nbsp;kW</td>
        <td><span class="pill ${s[2]}">${s[1]}</span>${x.blocked_note ? `<div class="sub" style="color:${x.discom_ref ? 'var(--info)' : 'var(--warn)'};margin-top:3px">${x.discom_ref ? '&#9432;' : '&#9888;'} ${esc(x.blocked_note)}</div>` : ''}</td>
        <td class="mono">${x.docs}${x.flagged ? ` <span class="pill warn">${x.flagged} flagged</span>` : ''}</td>
        <td class="mono" style="font-size:11px;white-space:nowrap">${esc(x.number || '—')}</td>
        <td class="sub">${esc(x.last_activity)}</td>
        <td>${x.application_no
      ? `<span class="mono sub">${esc(x.application_no)}</span>`
      : x.workflow
        ? `<button class="btn sm pri" data-run="${x.id}" ${can('operator') ? '' : 'disabled title="Operator role required"'}>Run agent</button>
           <div class="sub" style="margin-top:3px">${esc(wfLabel(x.workflow))}</div>`
        : `<span class="sub">handled by staff</span>`}</td>
      </tr>`; }).join('')}</tbody></table></div></div></div>`;
};

/* ------------------------------ run view ------------------------------ */
function runView() {
  return `<div class="runwrap">
  <div class="card pane-steps"><div class="ch"><h3 id="planTitle">Run plan</h3><span class="spacer"></span>
    <span class="pill idle mono" id="runclock">00:00</span></div>
    <div class="cb" style="padding:10px 11px;border-bottom:1px solid var(--line-soft)">
      <div class="lab">Application</div>
      <select id="runcid" style="width:100%;margin-top:5px"></select>
      <div class="lab" style="margin-top:10px">Workflow</div>
      <select id="runwf" style="width:100%;margin-top:5px"></select>
      <div class="row" style="margin-top:7px;gap:8px">
        <label class="lab" for="runkw" style="margin:0">Load</label>
        <input type="text" id="runkw" inputmode="decimal" style="width:70px;text-align:right">
        <span class="sub">kW &middot; plant size, or the load being requested</span></div>
      <div class="hint" id="runmeta" style="margin-top:7px"></div>
    </div>
    <div class="steps" id="steps"></div>
    <div class="cb" style="border-top:1px solid var(--line-soft)">
      <div class="row"><div class="lab">Evidence</div><span class="spacer"></span>
        <button class="btn sm" id="runpdf" disabled>PDF report</button></div>
      <div class="shots" id="shots" style="margin-top:8px"></div>
    </div></div>

  <div class="card flat">
    <div class="ch">
      <h3 id="runstate">Idle</h3><span class="spacer"></span>
      <div class="seg" role="group" aria-label="Speed">
        <button data-speed="1" aria-pressed="true">1&times;</button>
        <button data-speed="2" aria-pressed="false">2&times;</button>
        <button data-speed="4" aria-pressed="false">4&times;</button></div>
      <label class="chip" style="gap:6px"><input type="checkbox" id="headful" style="margin:0">
        Show real window</label>
      <button class="btn sm" id="bpause" disabled>Pause</button>
      <button class="btn sm danger" id="bstop" disabled>Abandon</button>
      <button class="btn sm pri" id="bstart">Start run</button>
    </div>
    <div class="browser" id="browser">
      <div class="bbar"><div class="lights"><i></i><i></i><i></i></div>
        <div class="url"><span class="dot"></span><span id="urlbar">no session open</span></div>
        <span class="livetag" id="livetag">sandbox</span></div>
      <div class="stage" id="stage">
        <img id="frame" alt="Live view of the browser the agent is driving" hidden>
        <div class="idle" id="stageIdle">
          <div class="idlebox">
            <div class="lab">Browser idle</div>
            <div class="t">Press &ldquo;Start run&rdquo; and a real Chromium session takes it from here</div>
            <div class="hint">It opens the sandbox portal for the chosen workflow, fills every
              field from this customer's parsed documents, attaches their files and submits. The
              frames below are screenshots of that actual browser, streamed live. It stops wherever
              a person is required:</div>
            <ol>
              <li><b>OTP</b> — the portal texts a code to the number dedicated to this registration;
                a person reads it out of the inbox.</li>
              <li><b>CAPTCHA</b> — the agent screenshots the challenge and asks. It never tries to
                break it.</li>
              <li><b>Correction</b> — it compares the name it is about to file against the
                connection record and stops if they differ.</li>
              <li><b>Approval</b> — only a supervisor can file, and the server enforces that.</li>
            </ol>
          </div></div>
      </div></div>
    <div class="cb"><div class="hint" id="runfoot">Automation runs against the local sandbox portal
      at <span class="mono">/portal</span>. Delivery points the same step list at the live portal;
      the holds, evidence capture and audit writes do not change.</div></div>
  </div>

  <div class="card"><div class="ch"><h3>Live log</h3><span class="spacer"></span>
    <button class="btn sm" id="logcopy">Copy</button></div>
    <div class="log" id="log"></div>
    <div class="cb" style="border-top:1px solid var(--line-soft)" id="holdSlot"></div>
  </div></div>`;
}

const wfLabel = id => (S.workflows.find(w => w.id === id) || {}).label || id;

function runHead() {
  const sel = $('#runcid');
  sel.innerHTML = S.customers.map(c =>
    `<option value="${c.id}" ${c.id === S.runCid ? 'selected' : ''}>${c.id} · ${esc(c.name)} · ${c.kw} kW${c.application_no ? ' (filed)' : ''}</option>`).join('');
  const c = S.customers.find(x => x.id === S.runCid) || S.customers[0];
  S.runCid = c.id;
  if (S.runWf === null) S.runWf = c.workflow || '';
  if (S.runKw === null) S.runKw = c.kw;
  $('#runwf').innerHTML = (S.runWf ? '' : '<option value="">No workflow applies</option>') +
    S.workflows.map(w => `<option value="${w.id}" ${w.id === S.runWf ? 'selected' : ''}>${esc(w.label)}</option>`).join('');
  $('#runkw').value = S.runKw;
  $('#runmeta').innerHTML = `<span class="mono">${c.consumer_no || 'no connection yet'}</span> · ${esc(c.place)} ·
    ${esc(c.category)} · number <span class="mono">${esc(c.number || 'unassigned')}</span>
    ${c.blocked_note ? `<div style="margin-top:5px;color:var(--warn)">${esc(c.blocked_note)}</div>` : ''}`;
  $('#bstart').disabled = !can('operator') || !S.runWf || ['running', 'held', 'paused', 'starting'].includes(S.runStatus);
  $('#headful').disabled = !can('operator');
}
function pickRunCustomer(cid) {
  const c = S.customers.find(x => x.id === cid);
  S.runCid = cid; S.runWf = (c && c.workflow) || ''; S.runKw = c ? c.kw : null;
  runHead();
}

const BULLET = { done: '&#10003;', fail: '!', hold: '&#9208;', active: '&#9679;', skipped: '–' };
function paintSteps() {
  const el = $('#steps'); if (!el) return;
  if (!S.steps.length) { el.innerHTML = '<div class="hint" style="padding:12px 9px">The step plan for the chosen workflow appears here when a run starts.</div>'; return; }
  el.innerHTML = S.steps.map((s, i) => `<div class="step" data-s="${s.status}">
    <div class="bul">${BULLET[s.status] || i + 1}</div><div class="st">${esc(s.label)}</div>
    <div class="tm">${s.ms ? (s.ms / 1000).toFixed(1) + 's' : ''}</div>
    ${s.note ? `<div class="note">${esc(s.note)}</div>` : ''}</div>`).join('');
}
function paintShots() {
  const el = $('#shots'); if (!el) return;
  el.innerHTML = S.shots.length ? S.shots.map((s, i) =>
    `<button class="shot ${s.kind === 'fail' ? 'fail' : ''}" data-shot="${i}">
      <img src="${s.url}" alt="${esc(s.label)}" loading="lazy">
      <div class="cap2"><b>${esc(s.label)}</b><span>${esc(s.ts)}</span></div></button>`).join('')
    : '<div class="hint">Screenshots land here, one per checkpoint and one per failure.</div>';
}
function logLine(ev) {
  const log = $('#log'); if (!log) return;
  const d = document.createElement('div');
  d.className = 'le ' + (ev.level || 'info');
  d.innerHTML = `<t>${esc(ev.ts)}</t><span>${esc(ev.message)}</span>`;
  log.appendChild(d); log.scrollTop = log.scrollHeight;
}
function paintRunState() {
  const live = ['running', 'held', 'paused', 'starting'].includes(S.runStatus);
  const label = { starting: 'Starting', running: 'Running', held: 'Held for a person',
    paused: 'Paused', done: 'Completed', failed: 'Failed', stopped: 'Stopped', idle: 'Idle' };
  $('#runstate').textContent = label[S.runStatus] || S.runStatus;
  $('#browser').classList.toggle('live', live);
  $('#stage').classList.toggle('held', S.runStatus === 'held');
  $('#bpause').disabled = !live || !can('operator');
  $('#bpause').textContent = S.runStatus === 'paused' ? 'Resume' : 'Pause';
  $('#bstop').disabled = !live || !can('operator');
  $('#bstart').disabled = !can('operator') || live || !S.runWf;
  $('#bstart').textContent = S.runStatus === 'done' ? 'Run again' : 'Start run';
  $('#runpdf').disabled = !S.activeRun;
  $('#livetag').textContent = live ? 'live' : 'sandbox';
  counters();
}

function attachRun(rid) {
  S.activeRun = rid;
  if (S.es) S.es.close();
  S.steps = []; S.events = []; S.shots = []; S.hold = null;
  $('#log').innerHTML = ''; $('#holdSlot').innerHTML = '';
  S.es = new EventSource(`/api/runs/${rid}/stream`);
  S.es.onmessage = e => handle(JSON.parse(e.data));
  S.es.onerror = () => { /* EventSource retries on its own */ };
  S.t0 = Date.now(); tick();
}

function handle(ev) {
  switch (ev.type) {
    case 'state':
      S.runStatus = ev.status; paintRunState(); break;
    case 'plan': S.steps = ev.steps; $('#planTitle').textContent = ev.label || 'Run plan'; paintSteps(); break;
    case 'step': {
      const s = S.steps.find(x => x.key === ev.key);
      if (s) Object.assign(s, ev); else S.steps.push({ ...ev });
      paintSteps(); break;
    }
    case 'event': S.events.push(ev); logLine(ev); break;
    case 'shot': S.shots.push(ev); paintShots(); break;
    case 'frame':
      S.lastFrame = ev;
      $('#frame').src = 'data:image/jpeg;base64,' + ev.data;
      $('#frame').hidden = false; $('#stageIdle').hidden = true;
      $('#urlbar').textContent = ev.url || '';
      break;
    case 'hold': S.hold = ev; openHold(ev); break;
    case 'hold_resolved': S.hold = null; closeModal(); $('#holdSlot').innerHTML = ''; break;
    case 'done':
      S.runStatus = 'done'; paintRunState();
      toast(`${ev.workflow || 'Run'}: filed ${ev.application_no} in ${ev.seconds}s`);
      refreshAfterRun(); break;
    case 'failed':
      S.runStatus = ev.status || 'failed'; paintRunState();
      toast((S.runStatus === 'stopped' ? 'Run stopped, ' : 'Run failed: ') + ev.reason +
        '. Nothing was submitted.', S.runStatus !== 'stopped');
      refreshAfterRun(); break;
  }
}
async function refreshAfterRun() {
  const b = await api('/bootstrap');
  S.customers = b.customers; S.numbers = b.numbers; S.audit = b.audit; S.runs = b.runs;
  S.followups = await api('/followups').catch(() => S.followups);
  // the customer's next step may have changed (a filed load enhancement leads to rooftop)
  if (S.view === 'run') { pickRunCustomer(S.runCid); paintRunState(); } else render();
  counters();
}
function tick() {
  if (!['running', 'held', 'paused', 'starting'].includes(S.runStatus)) { setTimeout(tick, 600); return; }
  const s = Math.floor((Date.now() - S.t0) / 1000);
  const el = $('#runclock');
  if (el) el.textContent = `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  setTimeout(tick, 500);
}

/* ------------------------------ human checkpoints ------------------------------ */
function openHold(h) {
  const c = h.context || {};
  const banner = (cls, txt) => `<div class="warnbox ${cls}" style="margin-bottom:13px"><span>&#9208;</span><div>${txt}</div></div>`;
  const gate = min => can(min) ? '' : ` disabled title="${min} role required"`;

  if (h.kind === 'otp') {
    modal('OTP checkpoint', 'The portal is waiting for a one-time password. The run is held.',
      (c.error ? banner('bad', `<b>The portal rejected the last code.</b> ${esc(c.error)}`)
        : c.notice ? banner('', `<b>${esc(c.notice)}</b> It is at the top of the messages below.`)
        : banner('', `Held at step ${esc(c.step)}. Nothing is submitted while this is open.`)) +
      `<div class="inbox"><div class="ih"><span class="dot on"></span><b class="mono">${esc(c.msisdn)}</b>
        <span class="spacer"></span><span>dedicated number for this registration</span></div>
        ${(c.inbox || []).map(m => `<div class="sms"><div class="sf">${esc(m.sender)} &middot; ${esc((m.ts || '').slice(11))}</div>
          <div class="sx">${esc(m.body)}</div></div>`).join('') || '<div class="sms"><div class="sx">No messages yet.</div></div>'}
      </div>
      <div class="otpin">${[0, 1, 2, 3, 4, 5].map(i => `<input id="o${i}" inputmode="numeric" maxlength="1" aria-label="digit ${i + 1}">`).join('')}</div>
      <div class="hint" style="text-align:center">${esc(c.hint)}</div>`,
      `<button class="btn" data-act="escalate">Escalate</button>
       <button class="btn" data-act="resend"${c.resends_left === 0 ? ' disabled title="The portal allows 3 resends"' : gate('operator')}>Resend OTP</button>
       <span class="spacer"></span>
       <button class="btn go" id="otpgo"${gate('operator')}>Verify and resume</button>`);
    $$('.otpin input').forEach((inp, i) => inp.addEventListener('input', () => {
      inp.value = inp.value.replace(/\D/g, '');
      if (inp.value && i < 5) $('#o' + (i + 1)).focus();
    }));
    setTimeout(() => $('#o0') && $('#o0').focus(), 60);
    $('#otpgo').onclick = () => send(h, 'ok', { code: $$('.otpin input').map(x => x.value).join('') });
  }

  if (h.kind === 'captcha') {
    modal('CAPTCHA checkpoint', 'A security challenge appeared. The agent screenshots it and asks.',
      (c.error ? banner('bad', `<b>The portal refused the last code.</b> ${esc(c.error)}`)
        : banner('', `Held at step ${esc(c.step)}.`)) +
      `<div class="capbox"><img src="${c.image}" alt="CAPTCHA challenge from the portal">
        <input type="text" id="capin" placeholder="Type the code" style="width:180px;text-align:center;font-family:var(--font-mono);letter-spacing:.16em;text-transform:uppercase"></div>
      <div class="hint" style="text-align:center">${esc(c.hint)}</div>`,
      `<button class="btn" data-act="escalate">Escalate</button><span class="spacer"></span>
       <button class="btn go" id="capgo"${gate('operator')}>Submit and resume</button>`);
    setTimeout(() => $('#capin') && $('#capin').focus(), 60);
    $('#capin').onkeydown = e => { if (e.key === 'Enter') $('#capgo').click(); };
    $('#capgo').onclick = () => send(h, 'ok', { code: $('#capin').value.trim().toUpperCase() });
  }

  if (h.kind === 'fix') {
    modal(c.portal_error ? 'The portal rejected it' : 'Field correction needed',
      c.portal_error ? 'Captured with a screenshot. The run is held, not abandoned.'
        : 'The agent caught this before spending a submission.',
      banner(c.portal_error ? 'bad' : '',
        c.portal_error ? `<b>${esc(c.code)}</b> — ${esc(c.portal_error)}`
          : `Filing <b>${esc(c.filed)}</b> against a connection registered as <b>${esc(c.on_record)}</b>.`) +
      `<dl class="kv" style="margin-bottom:13px">
        <dt>Name on the bill / connection</dt><dd class="mono">${esc(c.on_record || c.bill_name)}</dd>
        <dt>Name on the identity document</dt><dd class="mono">${esc(c.aadhaar_name)}</dd>
        <dt>Currently filled in the form</dt><dd class="mono">${esc(c.filed)}</dd></dl>
      <div class="choice">${(c.options || []).map(o =>
        `<button data-choice="${o.id}" class="${o.recommended ? 'rec' : ''}"${can('operator') ? '' : ' disabled'}>
          <b>${esc(o.label)}${o.recommended ? ' — recommended' : ''}</b>
          ${o.detail ? `<span>${esc(o.detail)}</span>` : ''}</button>`).join('')}</div>
      <div class="hint">${esc(c.hint)}</div>`,
      `<button class="btn danger" data-act="escalate">Escalate to staff</button>`);
    $$('[data-choice]').forEach(b => b.onclick = () => send(h, b.dataset.choice, {}));
  }

  if (h.kind === 'approve') {
    const rows = c.summary || {};
    const sup = can('supervisor');
    modal('Approval required', `${c.workflow || 'Filing'} — no application is filed without a person approving it.`,
      `<dl class="kv" style="margin-bottom:13px">${Object.entries(rows).map(([k, v]) =>
        `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
      <div class="warnbox ${sup ? '' : 'bad'}"><span>&#9432;</span><div>
        ${sup
          ? 'Approving records your username, the exact field values and a screenshot in the audit trail.'
          : `You are signed in as <b>${esc(S.me.role)}</b>. Press the button anyway: the server will refuse it and write the refused attempt to the audit trail. Sign in as <b>r.deshmukh</b> to approve.`}
      </div></div>`,
      `<button class="btn danger" data-act="reject">Reject</button><span class="spacer"></span>
       <button class="btn pri" id="appgo">${sup ? 'Approve and submit' : 'Try to approve as ' + esc(S.me.role)}</button>`);
    $('#appgo').onclick = () => send(h, 'approve', {});
  }

  $('#holdSlot').innerHTML = `<div class="row"><span class="pill warn">held</span>
    <span class="hint" style="flex:1">${esc(h.label)}</span>
    <button class="btn sm" id="reopen">Reopen</button></div>`;
  $('#reopen').onclick = () => openHold(h);
}

async function send(h, resolution, payload) {
  try {
    await api(`/runs/${S.activeRun}/holds/${h.id}`, { method: 'POST', body: { resolution, payload } });
    closeModal();
  } catch (e) { toast(e.message, true); }
}

/* ------------------------------ documents ------------------------------ */
VIEWS.docs = () => {
  const c = S.customers.find(x => x.id === S.docCid) || S.customers[0];
  const ex = S.extract;
  const fields = (ex && ex.customer_id === c.id) ? ex.fields : null;
  return `<div class="docwrap">
  <div class="card raise"><div class="ch"><h3>Documents on file</h3><span class="spacer"></span>
    <select id="docCid">${S.customers.map(x => `<option value="${x.id}" ${x.id === c.id ? 'selected' : ''}>${x.id} · ${esc(x.name)}</option>`).join('')}</select></div>
    <div class="cb">
      <div id="docList">${((ex && ex.documents) || []).map(d => `<div class="docrow">
        <span class="pill idle">${esc(d.kind)}</span>
        <span class="nm"><a href="/files/docs/${c.id}/${encodeURIComponent(d.filename)}" target="_blank" style="color:var(--teal)">${esc(d.filename)}</a>
        <div class="sub">${Math.round(d.bytes / 1024)} KB · on disk</div></span></div>`).join('')
      || '<div class="hint">Loading…</div>'}</div>
      <div class="drop" id="drop" style="margin-top:11px">
        Drop a PDF bill here to parse your own document, or
        <label style="color:var(--teal);cursor:pointer">choose a file<input type="file" id="file" accept=".pdf" hidden></label>
      </div>
      <div class="row" style="margin-top:12px">
        <button class="btn pri" id="extract"${can('operator') ? '' : ' disabled'}>Run extraction</button>
        <span class="hint" style="flex:1;min-width:170px">Reads the PDF text layer, applies labelled
          regexes, then cross-checks bill against identity document and passbook.
          ${S.llm.enabled ? `Also sent to ${esc(S.llm.provider)} for a second opinion.` : 'No model key configured, so the deterministic parser runs alone.'}</span>
      </div>
    </div></div>

  <div class="grid">
    <div class="card"><div class="ch"><h3>Extracted fields</h3><span class="spacer"></span>
      <span class="pill ${!fields ? 'idle' : fields.some(f => f.status === 'review') ? 'warn' : 'ok'}">
        ${!fields ? 'not run' : fields.some(f => f.status === 'review')
      ? `${fields.filter(f => f.status === 'review').length} need review` : `${fields.length} verified`}</span></div>
      <div class="cb" style="display:grid;gap:1px;padding:7px">${fields ? fields.map(f => `
        <div class="fld ${f.status === 'review' ? 'review' : ''}">
          <div class="fk">${esc(f.field)} <span style="opacity:.7">&middot; ${esc(f.source)}</span></div>
          <div class="fv">${esc(f.value)}</div><div class="fc">${f.confidence}%</div>
          <div class="conf"><i style="width:${f.confidence}%"></i></div>
          ${f.note ? `<div class="fk" style="color:var(--warn);letter-spacing:0;text-transform:none;font-size:11px;line-height:1.5">${esc(f.note)}</div>` : ''}
        </div>`).join('') : '<div class="hint" style="padding:18px 12px;text-align:center">Press Run extraction. Values here are what the agent types into the portal.</div>'}</div></div>
    ${ex && ex.model ? `<div class="card"><div class="ch"><h3>Model pass</h3></div>
      <div class="cb hint">${esc(ex.model)}</div></div>` : ''}
  </div></div>`;
};

async function loadExtract(cid) {
  S.extract = await api('/extract/' + cid);
  if (S.view === 'docs') render();
}

/* ------------------------------ today: one list of what to do now ------------------------------ */
async function loadReports() {
  const sup = can('supervisor');
  const [k, h, r, u] = await Promise.all([api('/kpi').catch(() => null), api('/health').catch(() => null),
    S.live ? null : api('/reports').catch(() => null), sup ? api('/users').catch(() => null) : null]);
  S.kpi = k; S.health = h; S.reports = r; S.users = u;
  if (S.view === 'reports') render();
}
async function loadToday() {
  [S.today, S.board] = await Promise.all([api('/today').catch(() => null), api('/board').catch(() => null)]);
  counters();
  if (S.view === 'today' || S.view === 'pipeline') render();
}
// The vendor login on the left, the customer login on the right: upload in one, the customer approves in
// the other, and the Solara panel in each says what the other finished. Named windows are reused.
function sideBySide(p) {
  const w = Math.floor(screen.availWidth / 2), at = x => `popup,left=${x},top=0,width=${w},height=${screen.availHeight}`;
  const a = window.open(p.pmsg_vendor, 'solaraVendor', at(0)), b = window.open(p.pmsg, 'solaraCustomer', at(w));
  toast(a && b ? 'Vendor login on the left, customer login on the right. The Solara panel in each tells the other what is done.'
    : 'Chrome blocked one window: click the blocked pop-up icon in the address bar, choose Always allow, then press again.');
}
// what the co-pilot saved on the portal shows here as soon as the owner comes back to Solara
window.addEventListener('focus', async () => {
  if (S.view === 'today') return loadToday();
  if (S.view !== 'reg' || !S.regCid || !S.regData) return;
  const fresh = await api('/registration/' + S.regCid).catch(() => null);
  const sig = g => g && g.steps.map(s => +s.done).join('') + g.next.act;
  // only a step that moved re-draws the page, so nothing half-typed is lost on every focus
  if (fresh && sig(fresh) !== sig(S.regData)) {
    S.regData = fresh; S.reg = await api('/registration').catch(() => S.reg); render(); toast('Updated from the portal.');
  }
});
const fmtPhone = n => n && n.length === 10 ? `${n.slice(0, 5)} ${n.slice(5)}` : (n || '');
// the one button each line gets, by what the line asks for
const TODAY_BTN = { docs: 'Send the WhatsApp link', sign: 'Send to sign', check: 'Check it', details: 'Add details',
  register: 'Register now', approve: 'Approve now', accept: 'Open', upload: 'Open', vsig: 'Add signature', fix: 'Fill in', build: 'Make documents', wait: 'Open',
  otp: 'Open', loan: 'Open Jan Samarth', ask_accept: 'Send the steps', roof: 'Add the photo', field: 'Send the field link', serials: 'Check serials',
  closeout: 'Open', sfr: 'Open the portal', dcr: 'Open the DCR portal', installation: 'Open the portal', msedcl: 'Open MSEDCL', portal: 'Check it' };
// lines whose button does something in Solara itself (a viewer only looks)
const TODAY_DOES = ['docs', 'sign', 'vsig', 'build', 'field'];

VIEWS.today = () => {
  const t = S.today;
  if (!t) return '<div class="rgv"><section class="rgpane"><p class="rgnote">Loading today’s list…</p></section></div>';
  const op = can('operator') ? '' : ' disabled';
  let lead = true;  // only the top line gets the filled button: do it first
  const row = (x, muted) => { const go = !muted && lead; if (go) lead = false; return `<li class="tdrow${muted ? ' muted' : ''}${x.sev === 'bad' ? ' urgent' : ''}">
    <div class="tdmain"><b>${esc(x.text)}</b>
      <span class="sub">${esc(x.name)} · ${esc(x.cid)}${x.phone ? ` · <a href="tel:+91${esc(x.phone)}">${fmtPhone(x.phone)}</a>` : ''}${x.detail ? ` · ${esc(x.detail)}` : ''}</span></div>
    <div class="tdact">${x.otp ? `<a class="btn sm" href="${esc(x.otp.whatsapp)}" target="_blank" rel="noopener">WhatsApp: codes are coming</a>` : ''}
      <button class="btn ${go ? 'go' : muted ? 'sm' : ''}" data-today="${esc(x.cid)}" data-screen="${x.screen}" data-act="${esc(x.act)}"${!muted && TODAY_DOES.includes(x.act) ? op : ''}>${esc(muted ? 'Open' : TODAY_BTN[x.act] || 'Open')}</button></div></li>`; };
  const group = (title, hint, items, muted, key) => !items.length ? '' : `<section class="tdgroup" data-group="${key}" aria-label="${esc(title)}">
    <div class="rgsh"><h3>${title}</h3><span class="rgmeta">${hint}</span></div>
    <ul class="tdlist">${items.map(x => row(x, muted)).join('')}</ul></section>`;
  const n = t.calls.length + t.todo.length + t.portal.length;
  const date = new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' });
  return `<div class="rgv"><section class="rgpane tdpane" aria-labelledby="tdTitle">
    <header class="rghead"><h2 id="tdTitle">${n ? `${n} thing${n > 1 ? 's' : ''} to do` : 'Nothing to do right now'}</h2>
      <p class="rgfacts">${date}${t.waiting.length ? ` · ${t.waiting.length} waiting for customers` : ''}</p></header>
    ${n ? '' : `<div class="rgnext idle"><div class="rgnext-main"><div class="rgnext-txt"><span class="rgk">All caught up</span>
      <p>A new customer? Add them and send them the WhatsApp link for their documents.</p></div>
      <button class="btn go lg" id="todayNew"${op}>Add a new customer</button></div></div>`}
    ${group('Calls to make', 'the customer reads out the OTP', t.calls, false, 'calls')}
    ${group('To do in Solara', 'one click each', t.todo, false, 'todo')}
    ${group('On the government website', 'the co-pilot fills it; you press Submit', t.portal, false, 'portal')}
    ${group('Waiting', 'for the customer, the dealer or the field team', t.waiting, true, 'waiting')}
    ${group('Paused', 'off the lists above until resumed', (t.paused || []).map(p => ({ ...p, screen: 'inst', act: 'paused',
      text: `Paused: ${p.reason || 'no reason given'}`, detail: `${p.by}, ${(p.at || '').slice(5, 16).replace('T', ' ')}` })), true, 'paused')}
    <div class="rgactions" style="justify-content:flex-start;gap:8px;flex-wrap:wrap;padding:14px 0 6px">${n ? `<button class="btn" id="todayNew"${op}>+ Add a new customer</button>` : ''}
      <button class="btn sm" id="sideBySide">Open vendor + customer logins side by side</button>
      <button class="btn sm" id="coKey"${op}>Connect the Chrome helper</button></div>
  </section>
  <section class="rgpane tdboard" aria-label="Every customer">${boardCard()}
    <div class="row" style="padding:12px 2px;gap:9px;flex-wrap:wrap"><b>Monthly report</b><input type="month" id="month" value="${thisMonth()}" style="width:170px">
      <button class="btn pri" id="monthXlsx">Excel</button><button class="btn" id="monthPdf">PDF</button>
      <span class="hint">every customer with each step's date, the portal's status, and the audit trail</span></div>
  </section></div>`;
};

async function todayAct(t) {
  const cid = t.dataset.today, act = t.dataset.act;
  if (t.dataset.screen === 'closeout') { S.view = 'closeout'; render(); await loadCo(cid); return; }
  if (t.dataset.screen === 'inst') { S.view = 'inst'; render(); await loadInst(cid); if (!['portal', 'paused'].includes(act)) instAct(act); return; }
  S.view = 'reg'; render(); await loadReg(cid);
  if (act === 'docs') return regAskDocs();
  if (act === 'sign') return regSendAgreement();
  if (['check', 'details'].includes(act)) return regAct(act);
}

/* ------------------------------ registration (milestone 1) ------------------------------ */
// the latest request wins: a slower, older answer must not redraw over what the owner is typing
const seq = {};
const latest = k => { const n = (seq[k] || 0) + 1; seq[k] = n; return () => seq[k] === n; };

async function loadReg(cid) {
  const still = latest('reg');
  if (cid && cid !== S.regCid) S.regOpen = {};
  if (cid) S.regCid = cid;
  const list = await api('/registration');
  const id = S.regCid && list.some(x => x.id === S.regCid) ? S.regCid : list[0] && list[0].id;
  const data = id ? await api('/registration/' + id) : null;
  if (!still()) return;
  S.reg = list; S.regCid = id; S.regData = data;
  if (S.view === 'reg') render();
}

const REG_REQ = ['name', 'mobile', 'consumer_no', 'kw'];
const REG_LATER = ['account_holder', 'account_no', 'ifsc', 'passbook_unread'];
const regMin = s => s == null ? '' : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;


/* Input rules for the registration forms. The server enforces the same ones; these show the
   problem while typing, before Save. */
const VD = ['0123456789', '1234067895', '2340178956', '3401289567', '4012395678', '5987604321', '6598710432', '7659821043', '8765932104', '9876543210'];
const VP = ['0123456789', '1576283094', '5803796142', '8916043527', '9453126870', '4286573901', '2793806415', '7046913258'];
const verhoeff = n => { let c = 0; [...n].reverse().forEach((ch, i) => { c = +VD[c][+VP[i % 8][+ch]]; }); return c === 0; };
const REG_RULES = {
  aadhaar: { hint: 'Last 4 digits, from the QR. A full number is checked, then cut to the last 4', max: 16, mode: 'numeric', check: v => {
    v = v.trim(); if (!v) return ''; if (/^[Xx*]{4}[ -]?[Xx*]{4}[ -]?\d{4}$/.test(v) || /^\d{4}$/.test(v)) return '';
    if (/[^\d\s-]/.test(v)) return 'Digits only'; const n = v.replace(/\D/g, '');
    return n.length !== 12 ? `12 digits needed (${n.length} so far)` : /^[01]/.test(n) ? 'Never starts with 0 or 1' : verhoeff(n) ? '' : 'Check digit does not match; check each digit on the card'; } },
  name: { hint: 'As on the Aadhaar', max: 60, check: v => !v ? 'Required' : v.trim().length < 3 ? 'At least 3 characters' : /[^\p{L}\p{M} .'-]/u.test(v) ? 'Use letters and spaces (a full stop, apostrophe or hyphen is fine)' : '' },
  mobile: { hint: '10 digits. The portal sends the OTP here', max: 16, mode: 'numeric', check: v => { const n = v.replace(/\D/g, '').replace(/^(91|0)(?=\d{10}$)/, ''); return !v ? '' : !n ? 'Digits only' : /^[6-9]\d{9}$/.test(n) ? '' : '10 digits starting with 6, 7, 8 or 9'; } },
  email: { hint: 'The portal sends an OTP here', max: 120, check: v => !v || /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v.trim()) ? '' : 'Does not look like an email' },
  consumer_no: { hint: '12 digits, printed on the bill', max: 16, mode: 'numeric', check: v => { if (!v) return ''; if (/[^\d\s-]/.test(v)) return 'Digits only'; const n = v.replace(/\D/g, ''); return n.length !== 12 ? `12 digits needed (${n.length} so far)` : /^(\d)\1+$/.test(n) ? 'Repeats one digit; check the bill' : ''; } },
  kw: { hint: '0.5 to 10, e.g. 3 or 3.3', max: 6, mode: 'decimal', check: v => !v ? '' : !/^\d+(\.\d+)?$/.test(v.trim()) ? 'A number, e.g. 3.3' : +v < 0.5 || +v > 10 ? 'Between 0.5 and 10 kW' : '' },
  rts_cost: { hint: 'In rupees, e.g. 285000', max: 14, mode: 'decimal', check: v => { if (!v) return ''; const t = v.replace(/^\s*(rs\.?|inr|\u20b9)\s*/i, '').replace(/,/g, '').trim(); if (!/^\d+(\.\d{1,2})?$/.test(t)) return 'An amount in rupees; up to 2 decimals'; return +t < 10000 || +t > 2500000 ? 'Between Rs 10,000 and Rs 25,00,000' : ''; } },
  district: { hint: 'Optional', max: 40, check: v => !v || !/[^\p{L}\p{M} .'-]/u.test(v) ? '' : 'Letters only' },
  app_no: { hint: 'Copied by the co-pilot; type only if it missed', max: 40, check: v => { v = v.trim().toUpperCase(); return !v ? '' : !/^NP-[A-Z0-9]+-\d{6,}$/.test(v) ? 'Looks like NP-MHSED26-12345678' : /^NP-MHSED/.test(v) && v.split('-').pop().length !== 8 ? 'Ends in 8 digits; check for a missed digit' : ''; } }
};
const regFieldCheck = inp => {
  const r = REG_RULES[inp.dataset.r || inp.dataset.rule]; if (!r) return true;
  const msg = r.check(inp.value), box = inp.closest('.field') || inp.parentElement;
  inp.classList.toggle('bad', !!msg); inp.setAttribute('aria-invalid', msg ? 'true' : 'false');
  const e = box.querySelector('.ferr'); if (e) e.textContent = msg;
  if (inp.value.trim()) box.classList.remove('miss');
  // the amount in lakh notation, so a missed zero is seen before the agreement is printed
  if (inp.dataset.r === 'rts_cost' && box.querySelector('.fhint')) { const t = inp.value.replace(/^\s*(rs\.?|inr|₹)\s*/i, '').replace(/,/g, '').trim();
    box.querySelector('.fhint').textContent = inp.value && !msg ? 'Rs ' + Number(t).toLocaleString('en-IN', { maximumFractionDigits: 2 }) : r.hint; }
  return !msg;
};
const regFormOk = scope => $$(scope).map(regFieldCheck).every(Boolean);
const regSyncButtons = () => {
  const d = $('#regSave'); if (d && can('operator')) d.disabled = !regFormOk('#regDetails [data-r]');
  const c = $('#regCreate'); if (c) c.disabled = !($('#nName').value.trim().length >= 3 && regFormOk('#nName,#nMobile'));
};

/* The Registration screen: one next step at the top, then only the section that step needs.
   Sections the owner opens or closes stay that way until another customer is picked. */
const REG_SHORT = { documents: 'Documents', details: 'Details', registered: 'Registered', accepted: 'Accepted', signed: 'E-signed', uploaded: 'Uploaded', approved: 'Customer approved' };
const REG_KIND = { missing: 'Missing', invalid: 'Invalid', uncertain: 'Not sure', mismatch: 'Differs' };
const REG_FIELDS = [['name', 'Customer name'], ['mobile', 'Mobile'], ['email', 'Email'], ['consumer_no', 'Consumer number'],
  ['kw', 'Capacity (kW)'], ['rts_cost', 'Installation cost (Rs)'], ['district', 'District'], ['aadhaar', 'Aadhaar']];
const REG_KW = [1, 2, 3, 4, 5];
const regKwChips = (g, val, op) => {
  const sug = g.suggest && g.suggest.kw, sizes = [...new Set([...REG_KW, ...(sug ? [sug] : [])])].sort((a, b) => a - b);
  return `<div class="kwchips" role="group" aria-label="Pick the capacity">${sizes.map(n => `<button type="button" class="chip${+val === n ? ' on' : ''}${n === sug ? ' sug' : ''}" data-usekw="${n}" aria-pressed="${+val === n}"${op}>${n} kW</button>`).join('')}</div>`;
};
const LOCAL_WARN = s => s.local ? '<div class="hint" style="color:var(--warn);margin-top:8px">This link only opens on this computer or office network, not on the customer\u2019s phone. Solara needs its internet address (SOLARA_PUBLIC_URL) before customers can use links.</div>' : '';
const regFold = (id, title, meta, body, def) => {
  const open = (S.regOpen || {})[id] ?? def;
  return `<details class="rgsec" id="${id}" data-fold="${id}"${open ? ' open' : ''}>
    <summary><h3>${title}</h3><span class="rgmeta">${meta}</span></summary><div class="rgbody">${body}</div></details>`;
};
const regWhy = (g, act) => {
  const c = g.customer, first = esc((c.name || '').split(' ')[0]);
  const unsure = g.fields.filter(f => f.status === 'review' && !REG_LATER.includes(f.key)).map(f => esc(f.field));
  return {
    docs: 'Add the electricity bill (the PDF from the MSEDCL website, or a photo) and the Aadhaar. Solara reads them as soon as they are uploaded.',
    check: `Solara is not sure about: ${unsure.join(', ') || 'the PIN code'}. Compare with the document, then confirm.`,
    details: g.steps[2].done ? 'The agreement prints the installation cost from the vendor’s quote.' : `Still needed: ${g.missing.map(m => esc(m.replace(/\s*\(.*\)$/, ''))).join(', ')}.`,
    register: 'With the customer on the phone, open the portal. The co-pilot fills the form; you type the OTP and press Submit. It copies the application number back here.',
    accept: `In the vendor login, open Vendor Consent and approve ${first}. Then open My Application: the co-pilot reads the list and updates Solara.`,
    vsig: 'Once only: add the company signature that goes on every agreement.',
    sign: 'The customer gets a WhatsApp link, enters the last 4 digits of the consumer number, reads the agreement and signs on the phone.',
    wait: 'The link is with the customer and works for 7 days. Send it again if they cannot find it.',
    upload: 'In the vendor login: My Application, then Update Agreement. The co-pilot attaches the signed PDF and the cost; you press Submit.',
    approve: `The portal needs ${first} to approve the uploaded agreement in their own login: My Applications, Submit Agreement Details, Approve, tick the declaration, Verify & Approve. Call them for the login code.`,
    '': g.elapsed_to_accepted != null ? `Documents to accepted took ${regMin(g.elapsed_to_accepted)}, including the wait for the customer’s OTP.` : 'Registered, accepted, and the agreement is on the portal.'
  }[act] || '';
};

VIEWS.reg = () => {
  const list = S.reg || [], g = S.regData;
  const n = k => list.filter(k).length, inProg = n(x => x.done < x.total), waiting = n(x => x.next.act === 'wait'), done = n(x => x.done === x.total);
  const left = `<aside class="card rglist"><div class="ch"><h3>Customers</h3><span class="spacer"></span>
    <button class="btn sm" id="regNew"${can('operator') ? '' : ' disabled'}>+ New customer</button></div>
    ${list.length ? `<p class="rgcount">${inProg} in progress${waiting ? ` · ${waiting} waiting for e-sign` : ''}${done ? ` · ${done} done` : ''}</p>` : ''}
    <div class="colist">${list.length ? list.map(x => `<button data-reg="${x.id}" aria-current="${x.id === S.regCid}">
      <span class="row" style="justify-content:space-between;gap:8px"><b>${esc(x.name)}</b><span class="sub mono">${x.id}</span></span>
      <span class="row" style="justify-content:space-between;gap:8px"><span class="rgstate ${x.done === x.total ? 'ok' : x.next.act === 'wait' ? 'info' : x.next.act === 'register' ? 'live' : 'warn'}">${x.done === x.total ? 'Done' : esc(x.next.label)}</span>
      <span class="sub">${x.done} of ${x.total}</span></span></button>`).join('') : '<p class="rgnote" style="padding:14px">No customers yet. Press New customer and type their name.</p>'}</div></aside>`;
  if (!g) return `<div class="rgv"><div class="cowrap">${left}<div></div></div></div>`;

  const c = g.customer, d = g.data, v = g.values, op = can('operator') ? '' : ' disabled', act = g.next.act;
  const stepDone = k => g.steps.find(s => s.key === k).done, regd = stepDone('registered');
  const docs = Object.fromEntries(g.documents.map(x => [x.kind, x]));
  const flagged = g.fields.filter(f => f.status === 'review' && !REG_LATER.includes(f.key));
  const fp = g.fields.find(f => f.key === 'pin'), fa = g.fields.find(f => f.key === 'aadhaar_pin');
  const pinConflict = !!(fp && fa && fp.value !== fa.value && fp.value !== 'not read' && fa.value !== 'not read'
    && (fp.status === 'review' || fa.status === 'review'));
  const fieldRow = f => {
    const later = REG_LATER.includes(f.key), rev = f.status === 'review' && !later;
    return `<div class="fld ${rev ? 'review' : ''}" data-field="${esc(f.key)}">
      <div class="fk">${esc(f.field)} <span class="sub">· ${esc(f.source)}</span>${later ? ' <span class="pill idle">needed later</span>' : ''}</div>
      ${rev ? `<div class="row" style="gap:8px;grid-column:1/-1"><input type="text" data-fval="${esc(f.key)}" value="${esc(f.value === 'not read' ? '' : f.value)}" placeholder="${f.key === 'aadhaar_masked' ? 'last 4 digits only, e.g. 4471' : 'type it as on the document'}" maxlength="80" style="flex:1" aria-label="${esc(f.field)}"${op}>
        <button class="btn go" data-confirm="${esc(f.key)}"${op}>Confirm</button></div>` : `<div class="fv">${esc(f.value)}</div>`}
      ${f.note ? `<div class="fnote${rev ? ' warn' : ''}">${esc(f.note)}</div>` : ''}</div>`;
  };

  /* the next step: one action, one line on why, and whatever that step needs right beside it */
  const cur = g.steps.findIndex(s => !s.done);
  const steps = `<ol class="rgsteps" aria-label="Progress: ${g.steps.filter(s => s.done).length} of ${g.steps.length} steps done">${g.steps.map((s, i) =>
    `<li class="${s.done ? 'done' : ''}${i === cur ? ' cur' : ''}" title="${esc(s.label)}"${i === cur ? ' aria-current="step"' : ''}><span class="dot" aria-hidden="true">${s.done ? '&#10003;' : i + 1}</span>${REG_SHORT[s.key]}</li>`).join('')}</ol>`;
  const appField = `<div class="field rgapp"><label for="regApp">Application number</label>
    <div class="row" style="gap:8px"><input type="text" id="regApp" data-rule="app_no" placeholder="NP-MHSED26-…" value="${esc(c.application_no || '')}" maxlength="40" autocomplete="off" aria-describedby="h_regApp"${op}>
    <button class="btn" id="regAppSave" data-has="${esc(c.application_no || '')}"${op}>${c.application_no ? 'Replace number' : 'Save number'}</button></div>
    <div class="fhint" id="h_regApp">${c.application_no ? 'Replace it only after checking the number on the portal' : esc(REG_RULES.app_no.hint)}</div><div class="ferr" role="alert"></div></div>`;
  const primary = !act ? `<p class="rgstatus" id="regNext">&#10003; ${esc(g.next.label)}</p>`
    : act === 'wait' ? `<p class="rgstatus" id="regNext">${esc(g.next.label)}</p><button class="btn" id="regSign"${op}>Send the link again</button>`
    : `<button class="btn ${act === 'check' ? '' : 'go '}lg" id="regNext" data-act="${act}"${act === 'vsig' || can('operator') ? '' : ' disabled'}>${esc(act === 'details' && !regd ? 'Add the missing details' : g.next.label)}</button>`;
  // an issue already shown beside its value under "Check what was read" is not repeated here
  const open = g.validation.issues.filter(i => !flagged.some(f => f.note && f.note === i.message));
  const issues = !regd && open.length ? `<div class="rgissues" id="regIssues"><p>Also needed before registering:</p><ul>${open.map(i =>
    `<li><b>${REG_KIND[i.kind] || esc(i.kind)}</b><span>${esc(i.kind === 'missing' ? i.field[0].toUpperCase() + i.field.slice(1) : i.message)}</span></li>`).join('')}</ul></div>` : '';
  const next = `<div class="rgnext${act ? '' : ' idle'}">
    <div class="rgnext-main"><div class="rgnext-txt">${act ? '<span class="rgk">Next step</span>' : ''}<p>${regWhy(g, act)}</p></div>${primary}</div>
    ${act === 'docs' || (act === 'details' && !d.email && !regd) ? `<div class="rgline">Documents on the customer's phone? <button class="btn sm" id="regAskDocs"${op}>Ask the customer on WhatsApp</button> They send the bill, Aadhaar and email themselves.</div>` : ''}
    ${['register', 'approve'].includes(act) && g.otp ? `<div class="rgline">Call ${esc((c.name || '').split(' ')[0])} on <a href="${esc(g.otp.tel)}"><b>${fmtPhone(g.otp.phone)}</b></a> when you open the portal: they read out the code. <a class="btn sm" href="${esc(g.otp.whatsapp)}" target="_blank" rel="noopener">Tell them on WhatsApp first</a></div>` : ''}
    ${act === 'approve' ? `<div class="rgline">Approved on the portal without the co-pilot? <button class="btn sm" id="regApproved"${op}>Mark it approved</button></div>` : ''}
    ${act === 'register' ? appField : ''}
    ${act === 'upload' ? `<div class="rgline">Pressed Submit on the portal without the co-pilot? <button class="btn sm" id="regUploaded"${op}>Mark the agreement uploaded</button></div>` : ''}
    ${issues}</div>`;

  /* sections, the current one first */
  const onFile = ['bill', 'aadhaar', 'passbook', 'roof'].filter(k => docs[k]).length;
  const docsSec = regFold('regDocs', 'Documents', `${onFile} of ${Object.keys(g.doc_kinds).length} on file`,
    Object.entries(g.doc_kinds).map(([k, label]) => `<div class="docrow">
      <span class="pill ${docs[k] ? 'ok' : ['bill', 'aadhaar'].includes(k) ? 'warn' : 'idle'}">${docs[k] ? 'on file' : ['bill', 'aadhaar'].includes(k) ? 'needed' : 'later'}</span>
      <span class="nm">${esc(label)}${docs[k] ? `<span class="sub">${esc(docs[k].filename.replace(k + '_', ''))} · ${Math.round(docs[k].bytes / 1024)} KB</span>` : ''}</span>
      <label class="btn sm">${docs[k] ? 'Replace' : 'Upload'}<input type="file" data-doc="${k}" accept="image/*,.pdf" hidden${op}></label></div>`).join('')
    + `<p class="rgnote">The Aadhaar is read from its QR code on this computer; only the last 4 digits are kept.${g.llm.enabled ? '' : ' A photo of a bill or bank page is flagged for you to type.'}</p>`,
    act === 'docs' || (!stepDone('documents') && onFile < Object.keys(g.doc_kinds).length));
  const pinCard = !pinConflict ? '' : `<div class="fld review" id="regPin"><div class="fk">PIN code: the bill and the Aadhaar disagree</div>
    <div class="fnote" style="grid-column:1/-1">The portal and the agreement use the PIN you pick: the one where the customer lives and the meter is.</div>
    <div class="row" style="gap:8px;grid-column:1/-1">
      <button class="btn go" data-pinpick="${esc(fp.value)}"${op}>Use ${esc(fp.value)} <span class="sub">(bill)</span></button>
      <button class="btn" data-pinpick="${esc(fa.value)}"${op}>Use ${esc(fa.value)} <span class="sub">(Aadhaar)</span></button></div></div>`;
  const shownFlags = flagged.filter(f => !(pinConflict && ['pin', 'aadhaar_pin'].includes(f.key)));
  const readSec = !(pinConflict || shownFlags.length) ? '' : `<section class="rgsec" id="regRead"><div class="rgsh"><h3>Check what was read</h3>
    <span class="rgmeta">${shownFlags.length + (pinConflict ? 1 : 0)} to confirm</span></div><div class="rgbody rgflags">${pinCard}${shownFlags.map(fieldRow).join('')}</div></section>`;
  const rest = g.fields.filter(f => !flagged.includes(f));
  const allSec = !g.fields.length ? '' : regFold('regAll', 'Everything Solara read', `${rest.length} values from the documents`,
    `<div class="rgflags">${rest.map(fieldRow).join('')}</div>`, false);
  const det = REG_FIELDS.map(([k, label]) => [k, label, { name: c.name, mobile: d.mobile, email: d.email, consumer_no: c.consumer_no, kw: c.kw,
    rts_cost: d.rts_cost, district: d.district, aadhaar: d.aadhaar_last4 ? `XXXX XXXX ${d.aadhaar_last4}` : '' }[k]]);
  const missing = det.filter(([k, , val]) => REG_REQ.includes(k) && !val).length;
  const detSec = regFold('regDetails', 'Details for the portal', missing ? `${missing} missing` : 'complete',
    `<div class="cofields">${det.map(([k, label, val]) => `<div class="field${REG_REQ.includes(k) && !val ? ' miss' : ''}"><label for="r_${k}">${esc(label)}${REG_REQ.includes(k) ? ' <span class="req" title="needed to register">*</span>' : ''}</label>
      ${k === 'district' && g.districts.length ? `<select id="r_district" data-r="district" aria-describedby="h_district"${op}><option value="">Pick the district</option>
        ${(val && !g.districts.includes(val) ? [val, ...g.districts] : g.districts).map(x => `<option${x === val ? ' selected' : ''}>${esc(x)}</option>`).join('')}</select>`
      : `<input type="text" id="r_${k}" data-r="${k}" value="${esc(val ?? '')}" maxlength="${REG_RULES[k].max}" inputmode="${REG_RULES[k].mode || 'text'}" autocomplete="off" aria-describedby="h_${k}"${op}>`}
      ${k === 'kw' ? regKwChips(g, val, op) : ''}<div class="fhint" id="h_${k}">${k === 'district' && g.districts.length ? (val && !g.districts.includes(val) ? 'Not a district the portal lists: pick it from the list' : 'As the portal lists it; filled from the Aadhaar') : esc(REG_RULES[k].hint)}</div>${k === 'kw' && g.suggest && !val ? `<div class="fhint">${esc(g.suggest.kw)} kW suggested: ${esc(g.suggest.why)}</div>` : ''}${k === 'rts_cost' && !val ? '<div class="fhint warn">From the vendor’s quote. Solara never guesses a price.</div>' : ''}<div class="ferr" role="alert"></div></div>`).join('')}</div>
    <div class="rgactions"><button class="btn" id="regSave"${op}>Save details</button></div>`, !stepDone('details') || ['check', 'details'].includes(act));
  const portalSec = regFold('regPortal', 'On PM Surya Ghar', c.application_no ? esc(c.application_no) : 'not registered yet',
    `<dl class="rgfiled">${[['Name filed', v.name], ['Consumer number', v.consumer_no], ['Mobile', v.mobile], ['Capacity', v.capacity ? v.capacity + ' kW' : null],
      ['State', v.state], ['District', v.district], ['DISCOM', v.discom], ['Vendor', v.vendor]].map(([k, x]) => `<div><dt>${k}</dt><dd>${esc(x || 'not yet')}</dd></div>`).join('')}</dl>
    <div class="row" style="gap:8px"><a class="btn" href="${esc(g.portals.pmsg)}" target="_blank" rel="noopener">Open customer registration</a>
      <a class="btn" href="${esc(g.portals.pmsg_vendor)}" target="_blank" rel="noopener">Open vendor login</a></div>
    ${act === 'register' ? '' : appField}
    ${stepDone('signed') ? `<p class="rgline" id="regAgrCheck">Signed agreement: ${g.agreement.check.ok ? 'verified (approval, kept copy and signatures match)' : 'NOT verified: ' + esc(g.agreement.check.problems.join('; '))}</p>` : ''}
    ${g.requests.length ? `<p class="rgline">Agreement link: ${g.requests.map(r => `${esc(r.status === 'signed' ? 'signed by ' + r.signer_name : r.status)} (${esc(r.created_at.slice(5, 16).replace('T', ' '))})`).join(' · ')}</p>` : ''}
    ${g.agreement.draft ? '<p class="rgline warn">The agreement wording is a DRAFT format. The client must approve it before the first real customer signs.</p>' : ''}`,
    stepDone('details'));
  const first = { docs: docsSec, check: readSec, details: detSec }[act] ?? (stepDone('details') ? portalSec : '');
  const order = [first, ...[docsSec, readSec, detSec, allSec, portalSec].filter(x => x !== first)];

  return `<div class="rgv"><div class="cowrap">${left}
  <section class="rgpane" aria-labelledby="rgName">
    <header class="rghead"><h2 id="rgName">${esc(c.name)}</h2>
      <p class="rgfacts">${c.id} · consumer ${esc(c.consumer_no || 'not read yet')} · ${c.kw ? esc(c.kw) + ' kW' : 'capacity not set'}${c.application_no ? ' · ' + esc(c.application_no) : ''}</p></header>
    ${steps}${next}${order.join('')}
  </section></div></div>`;
};

async function regPost(path, body) {
  try { S.regData = await api(`/registration/${S.regCid}${path}`, { method: 'POST', body: body || {} }); S.reg = await api('/registration'); render(); return true; }
  catch (err) { toast(err.message, true); return false; }
}

async function regSendAgreement() {
  try {
    const s = await api(`/registration/${S.regCid}/agreement`, { method: 'POST', body: {} });
    modal('Agreement to the customer', 'They confirm the last 4 digits of their consumer number, read the agreement and sign with a finger. The link works for 7 days.',
      `<div class="field"><label>Link</label><input type="text" readonly value="${esc(s.url)}" id="signUrl"></div>${LOCAL_WARN(s)}
       <div class="hint">With the customer? Open it on your phone and hand it over.</div>`,
      `<button class="btn" data-close>Close</button><button class="btn" id="signCopy">Copy link</button>
       <a class="btn" href="${esc(s.url)}" target="_blank" rel="noopener">Customer is here: open</a>
       ${s.whatsapp ? `<a class="btn go" href="${esc(s.whatsapp)}" target="_blank" rel="noopener">Send on WhatsApp</a>` : ''}`);
    await loadReg();
  } catch (err) { toast(err.message, true); }
}

async function regAskDocs() {
  try {
    const s = await api(`/registration/${S.regCid}/ask-docs`, { method: 'POST', body: {} });
    modal('Documents from the customer', 'They photograph the bill and the Aadhaar and type their email on their own phone. Everything comes back here to check. The link works for 7 days.',
      `<div class="field"><label for="askUrl">Link</label><input type="text" readonly value="${esc(s.url)}" id="askUrl"></div>${LOCAL_WARN(s)}`,
      `<button class="btn" data-close>Close</button><button class="btn" id="askCopy">Copy link</button>
       ${s.whatsapp ? `<a class="btn go" href="${esc(s.whatsapp)}" target="_blank" rel="noopener">Send on WhatsApp</a>` : '<span class="hint">Add their mobile to send it on WhatsApp.</span>'}`);
  } catch (err) { toast(err.message, true); }
}

async function regAct(act) {
  const g = S.regData;
  const go = sel => { const el = $(sel); if (el) { const f = el.closest('details'); if (f) f.open = true; el.scrollIntoView({ behavior: 'smooth', block: 'center' }); } return el; };
  if (act === 'docs') return go('#regDocs');
  if (act === 'check') { const el = go('#regRead .fld.review input'); if (el) el.focus(); return; }
  if (act === 'details') { go('#regDetails'); const m = $$('#regDetails input').find(i => !i.value); if (m) m.focus(); return; }
  if (act === 'register') { window.open(g.portals.pmsg, '_blank'); toast('On the portal, the Solara panel (bottom right) fills the form. You type the OTP and press Submit.'); return; }
  if (act === 'accept') {
    modal('Accept in vendor login', 'On the portal: vendor login → Vendor Consent → Approve this customer. Then mark it here.',
      `<div class="hint">${esc(g.customer.name)} · application ${esc(g.customer.application_no)}</div>`,
      `<button class="btn" data-close>Cancel</button><a class="btn" href="${esc(g.portals.pmsg_vendor)}" target="_blank" rel="noopener">Open Vendor Consent</a>
       <button class="btn go" id="regAcceptedModal">I approved it</button>`);
    return;
  }
  if (act === 'vsig') return coAct('vsig');
  if (act === 'sign' || act === 'wait') return regSendAgreement();
  if (act === 'upload') { sideBySide(g.portals); setTimeout(() => toast('Left: My Application → Update Agreement → Attach in the Solara panel → Submit. Right: the customer approves it next.'), 2500); }
  if (act === 'approve') { window.open(g.portals.pmsg, '_blank'); toast('Log in as the customer (they read you the code) → My Applications → Submit Agreement Details → Approve → tick → Verify & Approve.'); }
}

/* ------------------------------ close-out ------------------------------ */
const CO_STATE = {
  ready: ['ok', 'Ready'], missing: ['warn', 'Missing data'], blocked: ['bad', 'Blocked'],
  needs_approval: ['info', 'Customer to sign'], changed: ['warn', 'Changed, re-approve'],
  needs_vendor_sig: ['warn', 'Company signature']
};
const CO_SELECT = { phase: ['Single phase', 'Three phase'], lightning_arrester: ['Yes', 'No'], protection_checks: ['Yes', 'No'] };
const MSEDCL_URL = '/msedcl/'; // sandbox; the live build opens https://rts.mahadiscom.in/RoofTopSolarVendor/

async function loadCo(cid) {
  const still = latest('co');
  if (cid) S.coCid = cid;
  const [list, data] = await Promise.all([api('/closeout'), api('/closeout/' + S.coCid)]);
  if (!still()) return;
  S.co = list; S.coData = data;
  if (S.view === 'closeout') render();
}

function coNext(g) { // the one thing to do next for this customer
  const ms = g.docs.filter(d => d.slot);
  if (!g.vendor_signature) return can('supervisor') ? ['vsig', 'Add the company signature (once)'] : ['', 'A supervisor adds the company signature once'];
  if (g.checks.some(c => c.sev === 'bad') || g.docs.some(d => d.state === 'missing')) return ['fix', 'Complete the details below'];
  if (g.docs.some(d => d.state === 'needs_approval' || d.state === 'changed')) return ['sign', 'Send to the customer for signature'];
  if (ms.some(d => !d.bytes)) return ['build', 'Generate the MSEDCL documents'];
  if (!g.data.msedcl_uploaded) return ['upload', 'Open MSEDCL and upload'];
  return ['', 'Done. All six are on MSEDCL'];
}

VIEWS.closeout = () => {
  const g = S.coData, list = S.co;
  if (!g) return '<div class="card"><div class="cb hint">Loading…</div></div>';
  const c = g.customer, d = g.data, ms = g.docs.filter(x => x.slot);
  const has = k => g.docs.find(x => x.key === k).state !== 'missing';
  const next = coNext(g);
  const steps = [
    ['Details', !g.checks.some(x => x.sev === 'bad') && g.docs.every(x => x.state !== 'missing' || ['site_photo', 'datasheet'].includes(x.key))],
    ['Photo + datasheet', has('site_photo') && has('datasheet')],
    ['Customer signed', g.consumer_signature && !g.docs.some(x => ['needs_approval', 'changed'].includes(x.state))],
    ['Documents made', ms.every(x => x.bytes)], ['On MSEDCL', !!d.msedcl_uploaded]];
  const groups = [...new Set(g.fields.map(f => f.group))];
  const input = f => {
    const v = esc(d[f.key] || ''), dis = can('operator') ? '' : ' disabled';
    if (f.key === 'module_serials') return `<textarea data-f="${f.key}" rows="5"${dis}>${v}</textarea>`;
    if (CO_SELECT[f.key]) return `<select data-f="${f.key}"${dis}><option value=""></option>${CO_SELECT[f.key].map(o => `<option${d[f.key] === o ? ' selected' : ''}>${o}</option>`).join('')}</select>`;
    return `<input type="${f.key.endsWith('_date') ? 'date' : 'text'}" data-f="${f.key}" value="${v}"${dis}>`;
  };
  const pill = st => { const p = CO_STATE[st]; return `<span class="pill ${p[0]}">${p[1]}</span>`; };
  return `<div class="grid" style="gap:14px">
  <div class="kpis">
    <div class="kpi"><div class="k">To close out</div><div class="v num">${list.filter(x => !x.uploaded).length}</div><div class="d">installed, not yet on MSEDCL</div></div>
    <div class="kpi"><div class="k">With the customer</div><div class="v num">${list.filter(x => x.link_open).length}</div><div class="d">link sent, waiting for their e-sign</div></div>
    <div class="kpi"><div class="k">Ready to upload</div><div class="v num">${list.filter(x => x.built === x.total && !x.uploaded).length}</div><div class="d">all six made, under 300 KB</div></div>
    <div class="kpi"><div class="k">On MSEDCL</div><div class="v num">${list.filter(x => x.uploaded).length}</div><div class="d">uploaded through the co-pilot</div></div>
  </div>
  <div class="cowrap">
    <div class="card"><div class="ch"><h3>Installed</h3><span class="spacer"></span>
      <button class="btn sm" id="coKey"${can('operator') ? '' : ' disabled'}>Connect co-pilot</button></div>
      <div class="colist">${list.map(x => `<button data-co="${x.id}" aria-current="${x.id === S.coCid}">
        <div class="row" style="justify-content:space-between"><b>${esc(x.name)}</b><span class="mono sub">${x.id}</span></div>
        <div>${x.uploaded ? '<span class="pill ok">On MSEDCL</span>' : x.built === x.total ? '<span class="pill live">Ready to upload</span>'
        : x.missing ? `<span class="pill warn">${x.missing} to complete</span>` : x.link_open ? '<span class="pill info">With customer</span>'
        : x.waiting_customer ? '<span class="pill info">Send for e-sign</span>' : `<span class="pill idle">${x.ready} of ${x.total} ready</span>`}
        <span class="sub">${x.kw} kW</span></div></button>`).join('')}</div></div>

    <div class="grid" style="gap:12px">
      <div class="card raise"><div class="ch"><div><h3>${esc(c.aadhaar_name || c.name)}</h3>
        <div class="sub mono">${c.id} · consumer ${esc(c.consumer_no || '—')} · ${g.capacity || '—'} kWp · MSEDCL ${esc(d.msedcl_app_id || '—')}</div></div>
        <span class="spacer"></span>
        <button class="btn ${next[0] ? 'go' : ''}" id="coNext" data-act="${next[0]}"${next[0] && (next[0] === 'vsig' || can('operator')) ? '' : ' disabled'}>${esc(next[1])}</button></div>
        <div class="cb"><div class="costeps">${steps.map(([n, ok], i) => `<div class="${ok ? 'done' : ''}">${ok ? '&#10003;' : i + 1}. ${n}</div>`).join('')}</div>
        ${g.checks.length ? `<div style="display:grid;gap:5px;margin-top:10px">${g.checks.map(x =>
          `<div class="fu ${x.sev === 'bad' ? 'bad' : 'warn'}"><span class="pill ${x.sev === 'bad' ? 'bad' : 'warn'}">${x.sev === 'bad' ? 'fix' : 'check'}</span><div>${esc(x.text)}</div></div>`).join('')}</div>` : ''}
        </div></div>

      <div class="card"><div class="ch"><h3>Documents</h3><span class="spacer"></span>
        <span class="hint">MSEDCL takes PDF only, 300 KB each</span></div><div class="tscroll"><table>
        <thead><tr><th>#</th><th>Document</th><th>Signed by</th><th>State</th><th>Size</th><th></th></tr></thead>
        <tbody>${g.docs.map(x => `<tr><td class="mono">${x.slot || 'PMSG'}</td><td>${esc(x.title)}${x.note ? `<div class="sub">${esc(x.note)}</div>` : ''}</td>
          <td class="sub">${x.signers.join(' + ') || '—'}</td><td>${pill(x.state)}</td>
          <td class="mono">${x.bytes ? `${Math.round(x.bytes / 1024)} KB` : '—'}</td>
          <td>${x.bytes ? `<a class="btn sm" href="/files/closeout/${c.id}/${x.key}.pdf" target="_blank">View</a>` : ''}</td></tr>`).join('')}</tbody></table></div></div>

      <div class="two">
        <div class="card"><div class="ch"><h3>Customer signature</h3><span class="spacer"></span>
          <button class="btn sm go" id="coSign"${can('operator') ? '' : ' disabled'}>Send for signature</button></div>
          <div class="cb" style="display:grid;gap:7px">
          <div class="hint">${g.consumer_signature ? 'Signed once. New or changed documents only need the customer to tap Approve.'
            : 'The customer draws their signature once, on their own phone or yours at the site.'}</div>
          ${g.requests.map(r => `<div class="row" style="justify-content:space-between"><span class="sub">${esc(r.created_at.replace('T', ' ').slice(5, 16))} · ${r.docs.length} doc(s)</span>
            <span class="pill ${r.status === 'signed' ? 'ok' : r.status === 'locked' ? 'bad' : 'info'}">${r.status === 'signed' ? 'signed by ' + esc(r.signer_name) : esc(r.status)}</span></div>`).join('')}
          </div></div>
        <div class="card"><div class="ch"><h3>Site photo and datasheet</h3></div><div class="cb" style="display:grid;gap:9px">
          ${d.lat ? `<img src="/api/closeout/${c.id}/photo.jpg?v=${encodeURIComponent(d.lat)}" alt="Installed system" style="width:100%;max-height:150px;object-fit:cover;border-radius:var(--r)">
            <div class="sub mono">GPS ${esc(d.lat)}, ${esc(d.lng)}</div>` : '<div class="hint">No photo yet. It must carry the phone camera\'s GPS location.</div>'}
          <label class="btn sm">${d.lat ? 'Replace photo' : 'Add photo'}<input type="file" id="coPhoto" accept="image/jpeg" hidden></label>
          <div class="sub">Datasheet: ${has('datasheet') ? 'in the library, reused for every customer with this module and inverter'
            : esc(g.docs.find(x => x.key === 'datasheet').note || 'needs the module and inverter make')}</div>
          <label class="btn sm">Upload datasheet PDF<input type="file" id="coSheet" accept=".pdf" hidden></label>
        </div></div>
      </div>

      <div class="card" id="coForm"><div class="ch"><h3>What was installed</h3><span class="spacer"></span>
        <span class="hint">${g.serial_count} serial number${g.serial_count === 1 ? '' : 's'} entered</span>
        <button class="btn sm pri" id="coSave"${can('operator') ? '' : ' disabled'}>Save</button></div>
        <div class="cb">${groups.map(gr => `<div class="lab" style="margin:6px 0 8px">${esc(gr)}</div><div class="cofields">
          ${g.fields.filter(f => f.group === gr).map(f => `<div class="field${f.key === 'module_serials' ? ' wide' : ''}"><label>${esc(f.label)}</label>${input(f)}</div>`).join('')}</div>`).join('')}</div></div>
    </div>
  </div></div>`;
};

function signPad(canvas) {
  const ctx = canvas.getContext('2d'), k = devicePixelRatio || 1, r = canvas.getBoundingClientRect();
  canvas.width = r.width * k; canvas.height = r.height * k; ctx.scale(k, k);
  ctx.lineWidth = 2.4; ctx.lineCap = 'round'; ctx.strokeStyle = '#0A1A3A';
  let last = null; const at = e => { const b = canvas.getBoundingClientRect(); return [e.clientX - b.left, e.clientY - b.top]; };
  canvas.onpointerdown = e => { canvas.setPointerCapture(e.pointerId); last = at(e); };
  canvas.onpointermove = e => { if (!last) return; const p = at(e); ctx.beginPath(); ctx.moveTo(...last); ctx.lineTo(...p); ctx.stroke(); last = p; };
  canvas.onpointerup = canvas.onpointercancel = () => { last = null; };
  return { clear: () => ctx.clearRect(0, 0, canvas.width, canvas.height), url: () => canvas.toDataURL('image/png') };
}

async function coUpload(kind, file) {
  const fd = new FormData(); fd.append('file', file);
  try {
    const r = await fetch(`/api/closeout/${S.coCid}/${kind}`, { method: 'POST', body: fd });
    const j = await r.json(); if (!r.ok) throw new Error(j.detail || r.statusText);
    toast(kind === 'photo' ? `Photo saved. GPS ${j.lat}, ${j.lng}` : `Datasheet saved at ${Math.round(j.bytes / 1024)} KB`);
    await loadCo();
  } catch (err) { toast(err.message, true); }
}

async function coAct(act) {
  if (act === 'fix') { $('#coForm').scrollIntoView({ behavior: 'smooth' }); return; }
  if (act === 'upload') { window.open((S.coData && S.coData.portals && S.coData.portals.msedcl) || MSEDCL_URL, '_blank'); toast('On the upload page, press "Attach" in the Solara panel, check, then Upload.'); return; }
  if (act === 'vsig') {
    modal('Company signature', 'Drawn once by the authorised signatory. It goes on the vendor line of every document.',
      `<div class="field"><label for="vsName">Name of signatory</label><input type="text" id="vsName" value="${esc(S.me.name)}"></div>
       <canvas class="pad" id="vsPad"></canvas>`,
      '<button class="btn" data-close>Cancel</button><button class="btn" id="vsClear">Clear</button><button class="btn go" id="vsSave">Save signature</button>');
    S.pad = signPad($('#vsPad')); return;
  }
  if (act === 'build') {
    toast('Generating the documents…');
    try {
      const out = await api(`/closeout/${S.coCid}/build`, { method: 'POST' });
      const made = out.filter(x => x.bytes);
      toast(`${made.length} documents made, largest ${Math.round(Math.max(...made.map(x => x.bytes)) / 1024)} KB`);
      await loadCo();
    } catch (err) { toast(err.message, true); }
    return;
  }
  if (act === 'sign') {
    try {
      const s = await api(`/closeout/${S.coCid}/sign`, { method: 'POST', body: {} });
      modal('Send to the customer', `${s.docs.length} document(s). The link works for 7 days and only after the customer enters the last 4 digits of their consumer number.`,
        `<div class="field"><label>Link</label><input type="text" readonly value="${esc(s.url)}" id="signUrl"></div>${LOCAL_WARN(s)}
         <div class="hint">At the site? Open it on your phone and hand it to the customer.</div>`,
        `<button class="btn" data-close>Close</button><button class="btn" id="signCopy">Copy link</button>
         <a class="btn" href="${esc(s.url)}" target="_blank" rel="noopener">Customer is here: open</a>
         ${s.whatsapp ? `<a class="btn go" href="${esc(s.whatsapp)}" target="_blank" rel="noopener">Send on WhatsApp</a>` : ''}`);
      await loadCo();
    } catch (err) { toast(err.message, true); }
  }
}

/* ------------------------------ the board (milestone 3), shown under Today ------------------------------ */
const thisMonth = () => new Date().toISOString().slice(0, 7);

function stageDots(row, stages) {
  return `<span class="dots" title="${esc(row.stage_name)}">${stages.map((s, i) =>
    `<i class="${i < row.index ? 'done' : i === row.index ? 'current' : ''}" title="${esc(s.name)}"></i>`).join('')}</span>`;
}

function boardCard() {
  const b = S.board;
  if (!b) return '';
  return `<div class="card raise" id="board"><div class="ch"><h3>Every customer, by portal stage</h3><span class="spacer"></span>
    <span class="hint">the portal's own ten stages; the co-pilot reads the status when you open My Application</span></div>
    <div class="tscroll"><table><thead><tr><th>Ref</th><th>Customer</th><th>Stage</th><th></th><th>Portal says</th><th>Loan · DCR · MSEDCL</th><th>Next in Solara</th><th></th></tr></thead>
    <tbody>${b.rows.map(r => `<tr${r.problems.length ? ' data-sev="warn"' : ''}><td class="mono sub">${esc(r.id)}</td>
      <td><div class="who2">${esc(r.name)}</div><div class="sub mono">${esc(r.application_no || 'not registered')}</div></td>
      <td>${stageDots(r, b.stages)}</td><td><span class="pill ${r.paused ? 'idle' : 'live'}">${r.paused ? 'Paused' : esc(r.stage_name)}</span></td>
      <td class="sub">${r.portal_status ? `${esc(r.portal_status)}<div style="font-size:10.5px">seen ${esc(r.portal_seen.slice(5, 16).replace('T', ' '))}</div>` : '—'}
        ${r.problems.map(p => `<div style="color:var(--bad);font-size:11px">${esc(p)}</div>`).join('')}</td>
      <td class="sub" data-others>${[['Loan', r.others.loan], ['DCR', r.others.dcr], ['MSEDCL', r.others.msedcl]].filter(x => x[1])
        .map(([k, v]) => `<div><b>${k}</b> ${esc(v)}</div>`).join('') || '—'}</td>
      <td class="sub">${esc(r.next.label)}</td>
      <td><button class="btn sm" data-goto="${r.application_no ? 'inst' : 'reg'}" data-cid="${esc(r.id)}">Open</button></td></tr>`).join('')}</tbody></table></div></div>`;
}

/* ------------------------------ installation (milestone 2) ------------------------------ */
async function loadInst(cid) {
  const still = latest('inst');
  if (cid) S.instCid = cid;
  const list = await api('/filing');
  const id = S.instCid && list.some(x => x.id === S.instCid) ? S.instCid : list[0] && list[0].id;
  const data = id ? await api('/filing/' + id) : null;
  if (!still()) return;
  S.inst = list; S.instCid = id; S.instData = data;
  if (S.view === 'inst') render();
}

const SR_STATE = { read: ['warn', 'to confirm'], confirmed: ['ok', 'confirmed'], clash: ['bad', 'repeat'], unread: ['bad', 'not readable'], repeat: ['idle', 'repeat photo'] };
const STEP_OPEN = { sfr: 'pmsg_apps', installation: 'pmsg_apps', dcr: 'dcr', loan: 'jansamarth', msedcl: 'msedcl' };

VIEWS.inst = () => {
  const list = S.inst || [], g = S.instData;
  const top = `<div class="kpis">
    <div class="kpi"><div class="k">After the agreement</div><div class="v num">${list.filter(x => x.done < x.total).length}</div><div class="d">customers with filing left</div></div>
    <div class="kpi"><div class="k">On site now</div><div class="v num">${list.filter(x => ['field', 'wait_field', 'serials'].includes(x.next.act)).length}</div><div class="d">photos and serials coming in</div></div>
    <div class="kpi"><div class="k">Waiting for the dealer</div><div class="v num">${list.filter(x => x.next.act === 'dealer').length}</div><div class="d">DCR panels not transferred</div></div>
    <div class="kpi"><div class="k">Milestone 2 done</div><div class="v num">${list.filter(x => x.done === x.total).length}</div><div class="d">six documents on MSEDCL</div></div></div>`;
  const left = `<div class="card"><div class="ch"><h3>Customers</h3></div>
    <div class="colist">${list.length ? list.map(x => `<button data-inst="${x.id}" aria-current="${x.id === S.instCid}">
      <div class="row" style="justify-content:space-between"><b>${esc(x.name)}</b><span class="mono sub">${x.id}</span></div>
      <div><span class="pill ${x.paused ? 'idle' : x.done === x.total ? 'ok' : ['dealer', 'wait_field', 'ask_accept'].includes(x.next.act) ? 'info' : 'warn'}">${x.paused ? 'Paused' : x.done === x.total ? 'Done' : esc(x.next.label)}</span>
      <span class="sub">${x.done}/${x.total}</span></div></button>`).join('') : '<div class="cb hint">Customers appear here once registered.</div>'}</div></div>`;
  if (!g) return `<div class="grid" style="gap:14px">${top}<div class="cowrap">${left}<div></div></div></div>`;
  const c = g.customer, d = g.data, op = can('operator') ? '' : ' disabled', fs = g.field;
  const input = f => {
    const v = d[f.key] || '';
    if (g.choices[f.key]) return `<select data-i="${f.key}"${op}><option value=""></option>${g.choices[f.key].map(o => `<option${v === o ? ' selected' : ''}>${o}</option>`).join('')}</select>`;
    return `<input type="${f.key.endsWith('_date') ? 'date' : 'text'}" data-i="${f.key}" value="${esc(v)}"${op}>`;
  };
  const group = (title, keys, extra) => `<div class="card" data-form="${esc(title)}"><div class="ch"><h3>${title}</h3><span class="spacer"></span>
    <button class="btn sm pri" data-isave${op}>Save</button></div><div class="cb">${extra || ''}<div class="cofields">${g.fields.filter(f => keys.includes(f.key))
      .map(f => `<div class="field"><label>${esc(f.label)}</label>${input(f)}</div>`).join('')}</div></div></div>`;
  const receipt = step => g.receipts.find(r => r.step === step);
  const t = g.times;
  const when = k => t[k] ? esc(t[k].slice(5, 16).replace('T', ' ')) : '';
  const mins = s => s == null ? '' : `${Math.floor(s / 60)} min ${s % 60} s`;
  const steps = g.steps.map((s, i) => `<div class="${s.done ? 'done' : ''}">${s.done ? '&#10003;' : i + 1}. ${esc(s.label)}</div>`).join('');
  const portal = STEP_OPEN[g.next.act];
  return `<div class="grid" style="gap:14px">${top}<div class="cowrap">${left}
  <div class="grid" style="gap:12px">
    <div class="card raise"><div class="ch"><div><h3>${esc(c.name)}</h3>
      <div class="sub mono">${c.id} · ${esc(c.application_no || '—')} · consumer ${esc(c.consumer_no || '—')} · ${c.kw || '—'} kW${g.loan ? ' · loan' : ''}</div></div>
      <span class="spacer"></span>
      <button class="btn ${g.next.act && !g.paused ? 'go' : ''}" id="instNext" data-act="${g.next.act}"${g.next.act && !g.paused && (g.next.act === 'vsig' || can('operator')) ? '' : ' disabled'}>${esc(g.paused ? 'Paused' : g.next.label)}</button></div>
      <div class="cb" style="display:grid;gap:10px">
        <div class="costeps" style="grid-template-columns:repeat(${g.steps.length},minmax(0,1fr))">${steps}</div>
        ${g.backlog ? '<div class="hint">Filed on the portals before Solara: only the MSEDCL close-out is left.</div>' : ''}
        ${g.paused ? `<div class="fu warn"><span class="pill warn">paused</span><div>${esc(g.paused.reason)} <span class="sub">· ${esc(g.paused.by)}, ${esc((g.paused.at || '').slice(5, 16).replace('T', ' '))}</span></div></div>` : ''}
        <div class="controls">
          ${portal ? `<a class="btn sm" href="${esc(g.portals[portal])}" target="_blank" rel="noopener">Open ${portal === 'pmsg_apps' ? 'My Application' : portal === 'dcr' ? 'DCR portal' : portal === 'jansamarth' ? 'Jan Samarth' : 'MSEDCL'}</a>` : ''}
          ${g.paused ? `<button class="btn sm" id="instResume"${op}>Resume</button>` : `<button class="btn sm" id="instPause"${op}>Pause</button>`}
          <button class="btn sm" id="instReview">Review what will be filed</button>
          <button class="btn sm" id="instRetry"${op}>Retry a step</button>
          <a class="btn sm" href="#" data-goto="closeout" data-cid="${esc(c.id)}">Close-out documents</a></div>
        ${g.post_install_seconds != null ? `<div class="hint">Post-installation (first field photo to all six on MSEDCL): <b class="mono">${mins(g.post_install_seconds)}</b></div>` : t.field_at ? `<div class="hint">Post-installation clock started ${when('field_at')}</div>` : ''}
        ${g.checks.length ? g.checks.map(x => `<div class="fu ${x.sev === 'bad' ? 'bad' : 'warn'}"><span class="pill ${x.sev === 'bad' ? 'bad' : 'warn'}">${x.sev === 'bad' ? 'fix' : 'check'}</span><div>${esc(x.text)}</div></div>`).join('') : ''}
      </div></div>

    <div class="card"><div class="ch"><h3>On the national portal</h3><span class="spacer"></span>
      <span class="hint">${g.timeline.portal ? `portal said “${esc(g.timeline.portal.status)}” on ${esc(g.timeline.portal.seen_at.slice(5, 16).replace('T', ' '))}` : 'open My Application once and the co-pilot reads the status'}</span></div>
      <div class="cb"><div class="tline">${g.timeline.stages.map(s => `<div class="${s.state}">${esc(s.name)}<small>${esc(s.who)}${/^\d{4}-/.test(s.at || '') ? ' · ' + esc(s.at.slice(8, 10) + '/' + s.at.slice(5, 7)) : s.at ? ' · ' + esc(s.at) : ''}</small></div>`).join('')}</div>
      ${g.timeline.problems.map(p => `<div class="fu bad" style="margin-top:8px"><span class="pill bad">check</span><div>${esc(p)}</div></div>`).join('')}</div></div>

    ${group('Site visit and feasibility report', ['location_type', 'roof_load_ok', 'shadow_free', 'roof_area', 'site_visited', 'visitor_name', 'visitor_phone', 'loan', 'loan_bank'],
      `<div class="hint" style="margin-bottom:8px">Filed on PM Surya Ghar with the quotation (made from the cost in the agreement) and the pre-installation roof photo${g.documents.some(x => x.kind === 'roof') ? ' (on file)' : ' (<b>not uploaded yet</b>: Registration → Roof photo)'}.</div>`)}

    <div class="card" id="instField"><div class="ch"><h3>From the site</h3><span class="spacer"></span>
      <span class="hint">${fs.modules_confirmed}${fs.module_count ? ' of ' + fs.module_count : ''} panels confirmed${fs.inverter ? ' · inverter ' + esc(fs.inverter) : ''}</span>
      <button class="btn sm" id="instLink"${op}>${fs.link_open ? 'Send the link again' : 'Send field team the link'}</button>
      ${fs.to_confirm ? `<button class="btn sm go" id="instConfirmAll"${op}>Confirm all barcode reads</button>` : ''}</div>
      <div class="cb" style="display:grid;gap:10px">
        <div class="row" style="gap:12px">${fs.site_photo ? `<img src="/api/closeout/${c.id}/photo.jpg?v=${encodeURIComponent(d.lat)}" alt="Installed system" style="width:150px;height:96px;object-fit:cover;border-radius:var(--r)">
          <div class="sub">GPS ${esc(d.lat)}, ${esc(d.lng)}<br>${esc(fs.photo_source || '')}</div>` : '<div class="hint">No site photo yet. The field team takes it on the link, with location on.</div>'}</div>
        <div class="serials">${fs.reads.length ? fs.reads.map(r => `<div class="sr" data-sr="${r.id}">
          <img src="/api/field/${c.id}/photo/${r.id}.jpg" alt="" loading="lazy" onerror="this.style.visibility='hidden'">
          <div style="min-width:0"><div class="mono">${esc(r.serial || '—')} <span class="sub">${esc(r.kind)}</span></div>
            <div class="sub"><span class="pill ${(SR_STATE[r.status] || SR_STATE.read)[0]}">${(SR_STATE[r.status] || SR_STATE.read)[1]}</span> ${esc(r.source || '')}${r.note ? ' · ' + esc(r.note) : ''}</div></div>
          <div class="row" style="gap:5px">${r.status !== 'confirmed' ? `<input type="text" data-srfix="${r.id}" value="${esc(r.serial || '')}" placeholder="type as on the label" style="width:150px"${op}>
            <button class="btn sm go" data-srdo="confirm" data-srid="${r.id}"${op}>Confirm</button>` : ''}
            <button class="btn sm" data-srdo="reject" data-srid="${r.id}"${op}>Remove</button></div></div>`).join('')
          : '<div class="hint">Serial numbers appear here as the field team photographs each panel label. Every one is confirmed against its photo before it reaches a document.</div>'}</div>
        ${d.module_serials ? `<div class="row"><a class="btn sm" href="/api/filing/${c.id}/dcr.xlsx">DCR Excel of panel numbers</a><span class="sub">${esc(String(d.module_serials).split('\n').length)} in the record</span></div>` : ''}
      </div></div>

    ${group('Installation details', ['dcr_cert_no', 'invoice_no', 'install_date', 'module_make', 'almm_model', 'module_wp', 'module_count', 'phase', 'inverter_make', 'inverter_kw', 'inverter_qty', 'protection_checks', 'lightning_arrester', 'earth_ohm', 'earthing_count'])}

    <div class="card"><div class="ch"><h3>Receipts</h3><span class="spacer"></span><span class="hint">the portal page, saved when each filing is marked done</span></div>
      <div class="cb" style="display:grid;gap:6px">${['sfr', 'loan', 'dcr', 'installation', 'agreement_uploaded'].filter(s => s !== 'loan' || g.loan).map(s => {
        const r = receipt(s);
        return `<div class="row" style="justify-content:space-between"><span>${esc({ sfr: 'Site feasibility report', loan: 'Loan application', dcr: 'DCR certificate', installation: 'Installation', agreement_uploaded: 'Agreement upload' }[s])}
          <span class="sub">${r ? esc(r.at.slice(5, 16).replace('T', ' ')) + ' · ' + Math.round(r.bytes / 1024) + ' KB' : ''}</span></span>
          <span class="row" style="gap:6px">${r ? `<a class="btn sm" href="/files/receipt/${c.id}/${s}" target="_blank">View</a>` : '<span class="pill idle">none yet</span>'}
          <label class="btn sm">Add by hand<input type="file" data-receipt="${s}" accept=".pdf,image/*" hidden${op}></label></span></div>`; }).join('')}
        ${g.documents.some(x => x.kind === 'loan_approval') ? `<div class="row" style="justify-content:space-between"><span>Loan in-principle approval letter</span><a class="btn sm" href="/files/receipt/${c.id}/loan_approval" target="_blank">View</a></div>` : ''}
      </div></div>
  </div></div></div>`;
};

async function instPost(path, body) {
  try { S.instData = await api(`/filing/${S.instCid}${path}`, { method: 'POST', body: body || {} }); S.inst = await api('/filing'); render(); return true; }
  catch (err) { toast(err.message, true); return false; }
}

async function instReview(force) {
  const g = S.instData, step = force || { sfr: 'sfr', loan: 'loan', dcr: 'dcr', installation: 'installation', details: g.steps.find(x => !x.done)?.key }[g.next.act];
  const pick = ['registration', 'sfr', 'loan', 'dcr', 'installation'].includes(step) ? step : 'installation';
  const r = await api(`/filing/${S.instCid}/review?step=${pick}`);
  modal(`Review: ${r.title}`, 'Exactly what the co-pilot puts on this portal form. Blank lines are left for you, or add them here first.',
    `<div class="field"><label>Form</label><select id="revStep">${['sfr', 'loan', 'dcr', 'installation', 'registration'].map(s => `<option value="${s}"${s === pick ? ' selected' : ''}>${esc({ sfr: 'Site feasibility report', loan: 'Jan Samarth basic details', dcr: 'DCR certificate', installation: 'Installation (5 steps)', registration: 'Registration' }[s])}</option>`).join('')}</select></div>
     <div class="sumgrid">${r.rows.map(x => `<div><div class="k">${esc(x.label)}</div><div class="v" style="font-size:12.5px;font-family:var(--font-ui);font-weight:500;line-height:1.35;white-space:pre-line;${x.value ? '' : 'color:var(--warn)'}">${esc(x.value || 'blank')}</div></div>`).join('')}</div>
     ${r.files.length ? `<div class="hint" style="margin-top:10px">Files: ${r.files.map(f => `${esc(f.title)} ${f.ready ? '&#10003;' : '<b style="color:var(--warn)">missing</b>'}`).join(' · ')}</div>` : ''}
     <div class="hint" style="margin-top:8px">${r.approval ? (r.approval.current ? `Approved by ${esc(r.approval.by)} on ${esc(r.approval.at.slice(5, 16).replace('T', ' '))}.` : `Approved by ${esc(r.approval.by)}, but the values changed since.`) : 'Not approved yet.'}</div>`,
    `<button class="btn" data-close>Close</button><button class="btn go" id="revApprove" data-step="${pick}"${r.missing.length || !can('supervisor') ? ' disabled' : ''}>${r.missing.length ? 'Fill the blanks to approve' : 'Approve these values'}</button>`);
}

async function instAct(act) {
  const g = S.instData;
  const go = sel => { const el = $(sel); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' }); return el; };
  if (act === 'details' || act === 'roof') {
    const el = (/number of panels/.test(g.next.label) && $('[data-i="module_count"]')) || $$('[data-i]').find(i => !i.value);
    if (act === 'roof') { S.view = 'reg'; await loadReg(g.customer.id); toast('Upload the pre-installation roof photo under Documents.'); return; }
    if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); el.focus(); } return;
  }
  if (act === 'vsig') return coAct('vsig');
  if (act === 'field' || act === 'wait_field') return $('#instLink').click();
  if (act === 'serials') { go('#instField'); return; }
  if (act === 'sfr' || act === 'installation') { window.open(g.portals.pmsg_apps, '_blank'); toast(act === 'sfr' ? 'My Application → Action → Site Feasibility Report. In the Solara panel press Fill, check, Submit, then "mark filed".' : 'My Application → Submit Installation. Press Fill on each of the 5 steps; you press Save & Next and Final Submit.'); return; }
  if (act === 'dcr') { window.open(g.portals.dcr, '_blank'); toast('DCR → Sell (B2C). Press Fill in the Solara panel. The certificate number is saved when it is issued.'); return; }
  if (act === 'dealer') {
    modal('Waiting for the dealer', 'The DCR portal refused panels that the dealer has not transferred to your stock yet.',
      '<div class="hint">Call the dealer to transfer them. When they confirm, apply again; Solara clears this as soon as the certificate is issued.</div>',
      `<button class="btn" data-close>Close</button><a class="btn" href="${esc(g.portals.dcr)}" target="_blank" rel="noopener">Open DCR portal</a><button class="btn go" id="instDealerClear">Dealer has transferred them</button>`);
    return;
  }
  if (act === 'loan') { window.open(g.portals.jansamarth, '_blank'); toast('With the customer: the panel fills the basic details and address. The customer types their own Aadhaar number and OTP and picks the bank.'); return; }
  if (act === 'ask_accept') {
    const mob = (g.data.mobile || '').replace(/\D/g, '').slice(-10);
    modal('Customer accepts the installation', 'This is the customer\'s own step on their phone. Send them the three lines below.',
      `<div class="field"><label>Message</label><textarea id="acceptText" rows="5" readonly>${esc(g.accept_text)}</textarea></div>`,
      `<button class="btn" data-close>Close</button>${mob.length === 10 ? `<a class="btn" href="https://wa.me/91${mob}?text=${encodeURIComponent(g.accept_text)}" target="_blank" rel="noopener">Send on WhatsApp</a>` : ''}
       <button class="btn go" id="instAccepted">Customer has accepted</button>`);
    return;
  }
  if (act === 'closeout' || act === 'msedcl') { S.view = 'closeout'; await loadCo(g.customer.id); if (act === 'msedcl') coAct('upload'); }
}

/* ------------------------------ numbers ------------------------------ */
VIEWS.numbers = () => {
  const n = S.numbers;
  return `<div class="grid" style="gap:14px">
  <div class="kpis">
    <div class="kpi"><div class="k">Pool size</div><div class="v num">${n.length}</div>
      <div class="d">${n.filter(x => x.customer_id).length} assigned · ${n.filter(x => !x.customer_id).length} free</div></div>
    <div class="kpi"><div class="k">OTPs received</div><div class="v num">${n.reduce((a, x) => a + x.otp_count, 0)}</div>
      <div class="d">counted by the server</div></div>
    <div class="kpi"><div class="k">Expiring in 14 days</div><div class="v num">${n.filter(x => x.days_left <= 14).length}</div>
      <div class="d">reminder fires at day 7</div></div>
    <div class="kpi"><div class="k">Monthly cost</div><div class="v">&#8377;${n.length * 165}</div>
      <div class="d">&#8776;&#8377;165 per number (voice+SMS pack) · 90-day retention</div></div>
  </div>
  <div class="card raise"><div class="ch"><h3>Dedicated number pool</h3><span class="spacer"></span>
    <span class="hint">One number per registration, held exclusively for 90 days.</span></div>
    <div class="tscroll"><table>
      <thead><tr><th>Number</th><th>Retention</th><th>Assigned to</th><th>OTPs</th><th>Inbox</th>
        <th>State</th><th></th></tr></thead>
      <tbody>${n.map(x => {
    const cust = S.customers.find(c => c.id === x.customer_id);
    const pct = Math.min(1, x.days_left / 90), circ = 2 * Math.PI * 14;
    const col = x.days_left <= 14 ? 'var(--bad)' : x.days_left <= 30 ? 'var(--warn)' : 'var(--teal)';
    return `<tr${x.days_left <= 14 ? ' data-sev="warn"' : ''}>
      <td class="mono">${esc(x.msisdn)}</td>
      <td><div class="row" style="gap:8px"><div class="ring">
        <svg width="34" height="34" aria-hidden="true"><circle cx="17" cy="17" r="14" fill="none" stroke="var(--line)" stroke-width="3"/>
        <circle cx="17" cy="17" r="14" fill="none" stroke="${col}" stroke-width="3" stroke-linecap="round"
          stroke-dasharray="${circ.toFixed(1)}" stroke-dashoffset="${(circ * (1 - pct)).toFixed(1)}"/></svg>
        <span>${x.days_left}</span></div><span class="sub">days</span></div></td>
      <td>${cust ? `<div class="who2">${esc(cust.name)}</div><div class="sub mono">${cust.id}</div>` : '<span class="sub">unassigned</span>'}</td>
      <td class="mono">${x.otp_count}</td>
      <td><button class="btn sm" data-inbox="${x.id}">Open${x.unread ? ` (${x.unread})` : ''}</button></td>
      <td><span class="pill ${x.status === 'free' ? 'idle' : x.status === 'expiring' ? 'bad' : 'ok'}">${esc(x.status)}</span></td>
      <td><div class="row" style="gap:6px">
        <button class="btn sm" data-otptest="${x.id}"${can('operator') ? '' : ' disabled'}>Test OTP</button>
        ${x.customer_id ? `<button class="btn sm danger" data-release="${x.id}"${can('operator') ? '' : ' disabled'}>Release</button>`
        : `<button class="btn sm" data-assign="${x.id}"${can('operator') ? '' : ' disabled'}>Assign</button>`}
      </div></td></tr>`; }).join('')}</tbody></table></div></div></div>`;
};

/* ------------------------------ calls ------------------------------ */
VIEWS.calls = () => {
  const c = S.calls[S.callSel] || S.calls[0];
  if (!c) return '<div class="card"><div class="cb hint">No calls recorded.</div></div>';
  return `<div class="callwrap">
  <div class="card"><div class="ch"><h3>Call log</h3></div>
    <div>${S.calls.map((x, i) => `<button class="cl" data-call="${i}" aria-current="${i === S.callSel}">
      <div class="row" style="justify-content:space-between"><span class="who2">${esc(x.customer_id)}</span>
        <span class="mono sub">${esc(x.duration)}</span></div>
      <div class="sub">${esc(x.goal)}</div>
      <div class="row" style="gap:6px;margin-top:3px">
        <span class="pill ${x.outcome.includes('Escalated') ? 'bad' : 'ok'}">${esc(x.outcome)}</span>
        <span class="pill idle">${esc(x.lang)}</span><span class="sub mono">${esc(x.when_label)}</span></div>
    </button>`).join('')}</div>
    <div class="cb" style="border-top:1px solid var(--line-soft)">
      <div class="lab">Voice coverage</div>
      <div class="row" style="margin-top:6px">${['Marathi', 'Hindi', 'English'].map(l => `<span class="pill info">${l}</span>`).join('')}</div>
      <div class="hint" style="margin-top:9px">These are recorded sample calls stored in the database.
        Live telephony needs a provider account and is quoted separately.</div>
    </div></div>
  <div class="card raise"><div class="ch"><h3>${esc(c.id)}</h3><span class="spacer"></span>
    <button class="btn sm" id="replay">Replay</button>
    <button class="btn sm" id="togglemr" aria-pressed="${S.showEn}">${S.showEn ? 'Hide English' : 'Show English'}</button></div>
    <div class="cb">
      <div class="sumgrid" style="margin-bottom:12px">
        <div><div class="k">Objective</div><div class="v" style="font-size:12.5px;font-family:var(--font-ui);font-weight:500;line-height:1.35">${esc(c.goal)}</div></div>
        <div><div class="k">Language</div><div class="v">${esc(c.lang)}</div></div>
        <div><div class="k">Duration</div><div class="v mono">${esc(c.duration)}</div></div>
        <div><div class="k">Outcome</div><div class="v" style="font-size:12.5px;font-family:var(--font-ui);font-weight:500;line-height:1.35">${esc(c.outcome)}</div></div>
      </div>
      <div class="tr" id="tr"></div></div></div></div>`;
};
function playTranscript(animate) {
  const tr = $('#tr'); if (!tr) return;
  const c = S.calls[S.callSel]; if (!c) return;
  tr.innerHTML = '';
  c.transcript.forEach((l, i) => {
    const add = () => {
      const d = document.createElement('div');
      d.className = 'tl ' + l[0];
      d.innerHTML = `<div class="wh">${l[0] === 'agent' ? 'Agent' : esc(c.customer_id)}</div>
        <div>${esc(l[1])}</div>${S.showEn ? `<div class="en">${esc(l[2])}</div>` : ''}`;
      tr.appendChild(d); tr.scrollTop = tr.scrollHeight;
    };
    animate ? setTimeout(add, i * 620) : add();
  });
}

/* ------------------------------ audit ------------------------------ */
VIEWS.audit = () => `<div class="grid" style="gap:14px">
  <div class="card"><div class="ch"><h3>Append-only audit trail</h3><span class="spacer"></span>
    <span class="pill idle mono">${S.audit.length} entries</span>
    <button class="btn sm" id="xlsx">Download Excel</button></div>
    <div class="audit">${S.audit.map(a => `
      <div class="ar"><span style="color:var(--fg-faint)">${esc(a.ts.replace('T', ' ').slice(5))}</span>
        <b>${esc(a.actor)}</b><span>${esc(a.action)}${a.target ? ' · ' + esc(a.target) : ''}
        ${a.detail ? `<span style="color:var(--fg-faint)"> — ${esc(a.detail)}</span>` : ''}</span></div>`).join('')}</div></div>
  <div class="two">
    <div class="card"><div class="ch"><h3>Who can do what</h3></div><div class="cb" style="display:grid;gap:8px">
      ${[['viewer', 'Viewer', 'Read dashboards and the audit trail. Cannot start a run.'],
    ['operator', 'Operator', 'Start, pause and retry runs. Enter OTP and CAPTCHA. Correct fields.'],
    ['supervisor', 'Supervisor', 'Everything an operator can do, and the only role allowed to approve a filing.']]
    .map(([k, r, d]) => `<div style="padding:9px 11px;border:1px solid var(--line-soft);border-radius:var(--r);background:${S.me.role === k ? 'var(--panel-2)' : 'transparent'}">
      <div class="row" style="justify-content:space-between"><b>${r}</b>${S.me.role === k ? '<span class="pill live">you</span>' : ''}</div>
      <div class="sub">${d}</div></div>`).join('')}
      <div class="hint">Every one of these is checked by the API before anything happens, not by the
        screen. Try approving a filing as the operator and watch the server refuse it.</div>
    </div></div>
    <div class="card"><div class="ch"><h3>Data handling in this build</h3></div><div class="cb" style="display:grid;gap:8px">
      ${[['Documents', 'on disk under data/documents, per customer'],
    ['OTP values', 'written to the SMS table only, never to the run log'],
    ['Screenshots', 'PNG files under data/screenshots, linked to the run'],
    ['Database', 'SQLite with WAL, single file, easy to back up'],
    ['Duplicate guard', 'enforced by the portal on consumer number'],
    ['Audit', 'append-only table, written server-side on every action']]
    .map(([k, v]) => `<div class="row" style="justify-content:space-between;gap:12px">
      <span class="sub">${k}</span><span class="mono" style="font-size:11.5px;text-align:right">${v}</span></div>`).join('')}
    </div></div>
  </div></div>`;

/* ------------------------------ reports ------------------------------ */
const mins = s => s == null ? '—' : s < 60 ? `${s} s` : `${(s / 60).toFixed(1)} min`;
VIEWS.reports = () => {
  const k = S.kpi, h = S.health, sup = can('supervisor') ? '' : ' disabled';
  if (!k) return '<div class="card"><div class="cb hint">Loading…</div></div>';
  const ms = `<div class="card raise" id="milestones"><div class="ch"><h3>The six milestones, measured</h3><span class="spacer"></span>
    <span class="hint">worked out from what Solara records; no stopwatch sheet</span></div>
    <div class="tscroll"><table><thead><tr><th></th><th>Milestone</th><th>Target</th><th>Now</th><th></th></tr></thead>
    <tbody>${k.milestones.map(m => `<tr data-ms="${m.key}"><td class="mono">${m.key}</td><td>${esc(m.name)}</td><td class="sub">${esc(m.target)}</td>
      <td>${esc(m.value)}${m.cases ? `<div class="sub">${m.cases.map(c => `${c.times ? '&#10003;' : '&middot;'} ${esc(c.case)}`).join('&ensp; ')}</div>` : ''}</td>
      <td><span class="pill ${m.met ? 'ok' : 'idle'}">${m.met ? 'met' : 'not yet'}</span></td></tr>`).join('')}</tbody></table></div></div>`;
  const time = `<div class="card" id="ownerTime"><div class="ch"><h3>Owner's time per customer</h3><span class="spacer"></span>
    <span class="hint">actions closer than 4 minutes are one sitting; waits for OTPs, the customer or the field are left out</span></div>
    <div class="tscroll"><table><thead><tr><th>Ref</th><th>Customer</th><th>Registration</th><th>After installation</th><th>All of it</th><th>Typed by hand</th><th>Re-filed</th></tr></thead>
    <tbody>${k.customers.map(c => `<tr><td class="mono sub">${esc(c.id)}</td><td>${esc(c.name)}</td><td>${mins(c.k1_seconds)}</td>
      <td>${mins(c.k2_seconds)}</td><td>${mins(c.total_seconds)}</td><td>${c.left_fields || '—'}</td><td>${c.refiled || '—'}</td></tr>`).join('')}</tbody></table></div></div>`;
  const care = `<div class="card" id="health"><div class="ch"><h3>Health and upkeep</h3><span class="spacer"></span>
    ${h ? `<span class="pill ${h.ok ? 'ok' : 'bad'}">${h.ok ? 'healthy' : 'needs attention'}</span>` : ''}</div>
    <div class="cb" style="display:grid;gap:6px">${h ? h.checks.map(c => `<div class="row" style="gap:10px">
      <span class="pill ${c.state === 'ok' ? 'ok' : c.state === 'warn' ? 'warn' : 'bad'}" style="min-width:70px;justify-content:center">${esc(c.key)}</span>
      <span class="sub">${esc(c.text)}</span></div>`).join('') : ''}
      <div class="row" style="gap:8px;flex-wrap:wrap;margin-top:6px">
        <button class="btn" id="backup"${sup}>Back up now</button>
        <button class="btn" id="drill"${sup}>Restore drill</button>
        <button class="btn" id="everything"${sup}>Export everything (.zip)</button></div>
      <div class="hint">Solara backs itself up once a day. The restore drill opens the newest backup on the side and proves it would restore.
        Export everything gives all customers, documents and the audit trail as plain files.</div></div></div>`;
  const people = !S.users ? '' : `<div class="card" id="people"><div class="ch"><h3>People who can sign in</h3></div>
    <div class="cb" style="display:grid;gap:6px">${S.users.map(u => `<div class="row" style="gap:10px">
      <b style="min-width:120px">${esc(u.username)}</b><span class="sub" style="flex:1">${esc(u.name)}</span>
      <select data-urole="${esc(u.username)}">${['viewer', 'operator', 'supervisor'].map(r => `<option${r === u.role ? ' selected' : ''}>${r}</option>`).join('')}</select>
      <button class="btn sm" data-upass="${esc(u.username)}">New password</button>
      ${u.username === S.me.username ? '' : `<button class="btn sm danger" data-uremove="${esc(u.username)}">Remove</button>`}</div>`).join('')}
      <button class="btn" id="userAdd" style="justify-self:start">+ Add a person</button>
      <div class="hint">Viewer: looks only. Operator: does the daily work. Supervisor: also people, backups and exports.</div></div></div>`;
  const exportsCard = `<div class="card"><div class="ch"><h3>Exports</h3></div><div class="cb" style="display:grid;gap:9px">
      <div class="row" style="gap:9px;flex-wrap:wrap"><b>Monthly report</b><input type="month" id="month" value="${thisMonth()}" style="width:170px">
        <button class="btn pri" id="monthXlsx">Excel</button><button class="btn" id="monthPdf">PDF</button></div>
      <button class="btn" id="xlsx" data-demo>Pipeline, numbers, runs and audit (.xlsx)</button>
      <button class="btn danger" id="resetdemo" data-demo${sup}>Reset the demo environment</button></div></div>`;
  return `<div class="grid" style="gap:14px">${ms}<div class="two">${care}${exportsCard}</div>${people}${time}
    ${S.live || !S.reports ? '' : demoReports()}</div>`;
};

const demoReports = () => {
  const r = S.reports;
  if (!r) return '<div class="card"><div class="cb hint">Loading…</div></div>';
  const holds = Object.entries(r.holds || {});
  const mx = Math.max(1, ...holds.map(h => h[1]));
  return `<div class="grid" style="gap:14px">
  <div class="kpis">
    <div class="kpi"><div class="k">Runs completed</div><div class="v num">${r.runs_done}</div>
      <div class="d">of ${r.runs_total} started${r.runs_failed ? ` · ${r.runs_failed} stopped` : ''}</div></div>
    <div class="kpi"><div class="k">Average run</div><div class="v num">${r.avg_seconds ? r.avg_seconds : '—'}<span>s</span></div>
      <div class="d">including every human pause</div></div>
    <div class="kpi"><div class="k">Filed on portals</div><div class="v num">${r.applications + (r.service_requests || 0)}</div>
      <div class="d">${r.applications} rooftop &middot; ${r.service_requests || 0} DISCOM</div></div>
    <div class="kpi"><div class="k">Fields extracted</div><div class="v num">${r.extractions}</div>
      <div class="d">${r.flagged} flagged for review</div></div>
    <div class="kpi"><div class="k">Retries</div><div class="v num">${r.retries}</div>
      <div class="d">corrections applied mid-run</div></div>
  </div>
  <div class="two">
    <div class="card"><div class="ch"><h3>Where humans were needed</h3></div>
      <div class="cb" style="display:grid;gap:2px">${holds.length ? holds.map(([k, v]) =>
    `<div class="stagebar"><div class="nm">${k}</div><div class="tk"><i style="width:${v / mx * 100}%"></i></div><div class="ct">${v}</div></div>`).join('')
    : '<div class="hint">No checkpoints yet. Run the agent once.</div>'}
      <div class="hint" style="margin-top:10px">Approval is one per filing by design. The agent never
        files without it.</div></div></div>
    <div class="card"><div class="ch"><h3>Exports</h3></div><div class="cb" style="display:grid;gap:9px">
      <button class="btn" id="xlsx">Pipeline, numbers, runs and audit (.xlsx)</button>
      <button class="btn" id="backup"${can('supervisor') ? '' : ' disabled'}>Create a backup (.zip, documents stay encrypted)</button>
      <button class="btn danger" id="resetdemo" data-demo${can('supervisor') ? '' : ' disabled'}>Reset the demo environment</button>
      ${S.runs.filter(x => x.status === 'done' || x.status === 'failed').slice(0, 6).map(x =>
      `<button class="btn" data-pdf="${x.id}">Run ${x.id} report — ${esc(x.customer_id)} (.pdf)</button>`).join('')}
      <div class="hint">Both are produced server-side: openpyxl for the workbook, Chromium print-to-PDF
        for the report, which embeds the run's screenshots.</div>
    </div></div>
  </div>
  ${S.health ? `<div class="card" id="health"><div class="ch"><h3>System health</h3><span class="spacer"></span>
    <span class="pill ${S.health.ok ? 'ok' : 'bad'}">${S.health.ok ? 'healthy' : 'needs attention'}</span></div>
    <div class="cb" style="display:grid;gap:6px">${S.health.checks.map(c => `<div class="row" style="gap:10px">
      <span class="pill ${c.state === 'ok' ? 'ok' : c.state === 'warn' ? 'warn' : 'bad'}" style="min-width:70px;justify-content:center">${esc(c.key)}</span>
      <span class="sub">${esc(c.text)}</span></div>`).join('')}</div></div>` : ''}
  <div class="card"><div class="ch"><h3>Runs</h3></div><div class="tscroll"><table>
    <thead><tr><th>Run</th><th>Customer</th><th>Workflow</th><th>Status</th><th>Started</th><th>Reference</th>
      <th>Retries</th><th></th></tr></thead>
    <tbody>${S.runs.map(x => `<tr><td class="mono">${x.id}</td><td class="mono">${esc(x.customer_id)}</td>
      <td class="sub">${esc(wfLabel(x.workflow))}</td>
      <td><span class="pill ${x.status === 'done' ? 'ok' : x.status === 'running' ? 'live' : 'bad'}">${esc(x.status)}</span></td>
      <td class="sub mono">${esc((x.started_at || '').replace('T', ' ').slice(5))}</td>
      <td class="mono">${esc(x.application_no || '—')}</td><td class="mono">${x.retries}</td>
      <td><button class="btn sm" data-pdf="${x.id}">PDF</button></td></tr>`).join('')}
    </tbody></table></div></div></div>`;
};

/* ------------------------------ events ------------------------------ */
document.addEventListener('click', e => {
  const sm = e.target.closest('summary'), f = sm && sm.parentElement;
  if (f && f.dataset.fold) (S.regOpen ||= {})[f.dataset.fold] = !f.open;
});
document.addEventListener('click', async e => {
  const t = e.target.closest('button,a[data-goto]'); if (!t) return;

  if (t.dataset.as) { $('#u').value = t.dataset.as; $('#p').value = 'demo'; return login(t.dataset.as, 'demo'); }
  if (t.dataset.view) { S.view = t.dataset.view; render(); if (S.view === 'docs' && !S.extract) loadExtract(S.docCid); if (S.view === 'reports') loadReports(); if (S.view === 'closeout') loadCo(); if (S.view === 'reg') loadReg(); if (S.view === 'inst') loadInst(); if (S.view === 'today' || S.view === 'pipeline') loadToday(); return; }

  /* today and the board */
  if (t.dataset.goto) {
    e.preventDefault();
    const v = t.dataset.goto, cid = t.dataset.cid, act = t.dataset.gact;
    S.view = v; render();
    if (v === 'reg') { await loadReg(cid); if (act) regAct(act); }
    else if (v === 'inst') { await loadInst(cid); if (act && act !== 'portal') instAct(act); }
    else if (v === 'closeout') { await loadCo(cid); }
    return;
  }
  if (t.id === 'monthXlsx' || t.id === 'monthPdf') { window.open(`/api/exports/month.${t.id === 'monthXlsx' ? 'xlsx' : 'pdf'}?month=${$('#month').value}`, '_blank'); return; }

  /* installation */
  if (t.dataset.inst) { loadInst(t.dataset.inst); return; }
  if (t.id === 'instNext') { instAct(t.dataset.act); return; }
  if (t.hasAttribute('data-isave')) {
    // only what was changed here: the co-pilot or the field page may have saved other values meanwhile
    const body = Object.fromEntries($$('[data-i]').filter(i => i.value !== String(S.instData.data[i.dataset.i] ?? '')).map(i => [i.dataset.i, i.value]));
    try { S.instData = await api('/filing/' + S.instCid, { method: 'PUT', body }); clearDrafts(); S.inst = await api('/filing'); render(); toast('Saved'); }
    catch (err) { toast(err.message, true); }
    return;
  }
  if (t.id === 'instPause') {
    modal('Pause this customer', 'They leave Today until resumed. Nothing is filed or sent while paused.',
      '<div class="field"><label for="pauseWhy">Why</label><input type="text" id="pauseWhy" placeholder="e.g. customer away until 12 Nov"></div>',
      '<button class="btn" data-close>Cancel</button><button class="btn go" id="instPauseGo">Pause</button>');
    $('#pauseWhy').focus(); return;
  }
  if (t.id === 'instPauseGo') { if (await instPost('/pause', { reason: $('#pauseWhy').value })) { closeModal(); toast('Paused'); loadToday(); } return; }
  if (t.id === 'instResume') { if (await instPost('/resume')) { toast('Resumed'); loadToday(); } return; }
  if (t.id === 'instReview') { instReview().catch(err => toast(err.message, true)); return; }
  if (t.id === 'revApprove') {
    try { await api(`/filing/${S.instCid}/approve`, { method: 'POST', body: { step: t.dataset.step } }); closeModal(); toast('Approved. The co-pilot shows it on that form.'); }
    catch (err) { toast(err.message, true); }
    return;
  }
  if (t.id === 'instRetry') {
    const done = S.instData.steps.filter(x => x.done && ['sfr', 'loan', 'dcr', 'installation', 'accepted', 'msedcl'].includes(x.key));
    modal('Retry a step', 'For a filing the portal rejected or returned: the step shows as to do again and the co-pilot fills it again.',
      `<div class="field"><label for="retryStep">Step</label><select id="retryStep">${done.map(x => `<option value="${x.key}">${esc(x.label)}</option>`).join('')}</select></div>
       <div class="field"><label for="retryWhy">What the portal said</label><input type="text" id="retryWhy" placeholder="e.g. plant photo rejected, no coordinates"></div>`,
      `<button class="btn" data-close>Cancel</button><button class="btn go" id="instRetryGo"${done.length ? '' : ' disabled'}>Reopen it</button>`);
    return;
  }
  if (t.id === 'instRetryGo') { if (await instPost('/retry', { step: $('#retryStep').value, reason: $('#retryWhy').value })) { closeModal(); toast('Reopened. File it again on the portal.'); } return; }
  if (t.id === 'instLink') {
    try {
      const s2 = await api(`/filing/${S.instCid}/field-link`, { method: 'POST' });
      modal('Link for the field team', 'Valid 3 days. They open it on site: site photo with location on, every panel label, the inverter label.',
        `<div class="field"><label>Link</label><input type="text" readonly value="${esc(s2.url)}" id="signUrl"></div>`,
        `<button class="btn" data-close>Close</button><button class="btn" id="signCopy">Copy link</button>
         <a class="btn" href="${esc(s2.url)}" target="_blank" rel="noopener">Open here</a><a class="btn go" href="${esc(s2.whatsapp)}" target="_blank" rel="noopener">Send on WhatsApp</a>`);
      await loadInst();
    } catch (err) { toast(err.message, true); }
    return;
  }
  if (t.id === 'instConfirmAll') { if (await instPost('/serials/confirm-all')) toast('Confirmed every clean barcode read'); return; }
  if (t.dataset.srdo) {
    const id = t.dataset.srid, fix = $(`[data-srfix="${id}"]`);
    const r = (S.instData.field.reads || []).find(x => String(x.id) === id) || {};
    const action = t.dataset.srdo === 'confirm' && fix && fix.value.trim() && fix.value.trim().toUpperCase() !== (r.serial || '') ? 'correct' : t.dataset.srdo;
    if (await instPost(`/serial/${id}`, { action, serial: fix ? fix.value : '' })) toast(action === 'reject' ? 'Removed' : 'Confirmed');
    return;
  }
  if (t.id === 'instDealerClear') { closeModal(); if (await instPost('/mark', { step: 'dealer' })) toast('Cleared. Apply for the DCR certificate again.'); return; }
  if (t.id === 'instAccepted') { closeModal(); if (await instPost('/mark', { step: 'accepted' })) toast('Marked accepted'); return; }

  /* registration */
  if (t.dataset.reg) { loadReg(t.dataset.reg); return; }
  if (t.id === 'regNext') { regAct(t.dataset.act); return; }
  if (t.id === 'regNew') {
    modal('New customer', 'Just the name to start. Everything else comes from the documents.',
      `<div class="field"><label for="nName">Customer name</label><input type="text" id="nName" data-rule="name" maxlength="60" autocomplete="off" aria-describedby="nNameHint">
         <div class="fhint" id="nNameHint">As on the Aadhaar. Letters only, at least 3.</div><div class="ferr" role="alert"></div></div>
       <div class="field"><label for="nMobile">Mobile (optional)</label><input type="text" id="nMobile" data-rule="mobile" inputmode="numeric" maxlength="16" autocomplete="off">
         <div class="fhint">10 digits. Used to spot a customer who is already on file.</div><div class="ferr" role="alert"></div></div>`,
      '<button class="btn" data-close>Cancel</button><button class="btn go" id="regCreate" disabled>Add customer</button>');
    $('#nName').focus(); return;
  }
  if (t.id === 'regCreate') {
    try {
      const g = await api('/customers', { method: 'POST', body: { name: $('#nName').value, mobile: $('#nMobile').value,
        allow_duplicate: t.dataset.force === $('#nName').value + '|' + $('#nMobile').value } });
      closeModal(); await loadReg(g.customer.id); toast('Added. Now upload the bill and the Aadhaar.');
    } catch (err) {
      if (err.status === 409) {   // looks like someone already on file: open them, or add on purpose
        t.dataset.force = $('#nName').value + '|' + $('#nMobile').value; t.textContent = 'Add as a new customer anyway';
        $('#regDupe') || $('#nMobile').closest('.field').insertAdjacentHTML('afterend', `<div id="regDupe" class="hint" style="color:var(--warn)"></div>`);
        $('#regDupe').innerHTML = esc(err.message) + '<br>' + err.data.duplicates.map(m => `<button class="btn sm" data-reg="${esc(m.id)}" data-close>Open ${esc(m.id)}</button>`).join(' ');
      } else toast(err.message, true);
    }
    return;
  }
  if (t.dataset.pinpick) {
    const v = t.dataset.pinpick;
    if (await regPost('/confirm', { key: 'pin', value: v }) && await regPost('/confirm', { key: 'aadhaar_pin', value: v })) toast(`PIN ${v} will be used on the portal and the agreement`);
    return;
  }
  if (t.dataset.usekw) { const i = $('#r_kw'); if (i) { i.value = t.dataset.usekw; i.dispatchEvent(new Event('input', { bubbles: true })); }
    $$('.kwchips .chip').forEach(b => { b.classList.toggle('on', b === t); b.setAttribute('aria-pressed', String(b === t)); }); return; }
  if (t.id === 'regAskDocs') { regAskDocs(); return; }
  if (t.dataset.today) { todayAct(t); return; }
  if (t.id === 'sideBySide') return sideBySide(S.today.portals);
  if (t.id === 'todayNew') { S.view = 'reg'; render(); await loadReg(); $('#regNew')?.click(); return; }
  if (t.dataset.confirm) {
    const k = t.dataset.confirm;
    if (await regPost('/confirm', { key: k, value: $(`[data-fval="${k}"]`).value })) toast('Confirmed');
    return;
  }
  if (t.id === 'regSave') {
    const body = Object.fromEntries($$('[data-r]').map(i => [i.dataset.r, i.value]));
    try { S.regData = await api('/registration/' + S.regCid, { method: 'PUT', body }); clearDrafts(); S.reg = await api('/registration'); render(); toast('Saved'); }
    catch (err) { toast(err.message, true); }
    return;
  }
  if (t.id === 'regAppSave') {
    const v = $('#regApp').value.trim().toUpperCase(), had = t.dataset.has;
    if (!regFieldCheck($('#regApp')) || !v) { toast('Type the application number as NP-MHSED26-12345678', true); return; }
    if (had && v !== had && !confirm(`This customer is already registered as ${had}.\nReplace it with ${v}? Only do this after checking the portal.`)) return;
    if (await regPost('/mark', { step: 'registered', app_no: v, replace: !!had && v !== had })) toast('Application number saved');
    return;
  }
  if (t.id === 'regAccepted' || t.id === 'regAcceptedModal') { closeModal(); if (await regPost('/mark', { step: 'accepted' })) toast('Marked accepted'); return; }
  if (t.id === 'regSign') { regSendAgreement(); return; }
  if (t.id === 'regUploaded') { if (await regPost('/mark', { step: 'agreement_uploaded' })) toast('Agreement marked uploaded. Next: the customer approves it in their login.'); return; }
  if (t.id === 'regApproved') { if (await regPost('/mark', { step: 'customer_approved' })) toast('Approved by the customer. Milestone 1 done for this customer.'); return; }

  /* close-out */
  if (t.dataset.co) { loadCo(t.dataset.co); return; }
  if (t.id === 'coNext') { coAct(t.dataset.act); return; }
  if (t.id === 'coSign') { coAct('sign'); return; }
  if (t.id === 'coSave') {
    const body = Object.fromEntries($$('[data-f]').filter(i => i.value !== String(S.coData.data[i.dataset.f] ?? '')).map(i => [i.dataset.f, i.value]));
    try { S.coData = await api('/closeout/' + S.coCid, { method: 'PUT', body }); clearDrafts(); S.co = await api('/closeout'); render(); toast('Saved'); }
    catch (err) { toast(err.message, true); }
    return;
  }
  if (t.id === 'vsClear') { S.pad.clear(); return; }
  if (t.id === 'vsSave') {
    try {
      await api('/signature/vendor', { method: 'POST', body: { name: $('#vsName').value, image: S.pad.url() } });
      closeModal(); toast('Company signature saved'); S.view === 'reg' ? await loadReg() : await loadCo();
    } catch (err) { toast(err.message, true); }
    return;
  }
  if (t.id === 'signCopy' || t.id === 'askCopy') {
    try { await navigator.clipboard.writeText($(t.id === 'askCopy' ? '#askUrl' : '#signUrl').value); toast('Link copied'); } catch { toast('Copy blocked by the browser', true); }
    return;
  }
  if (t.id === 'coKey') {
    try {
      const k = await api('/copilot/key', { method: 'POST' });
      modal('Connect the co-pilot', 'Do this once on the computer you use for the portals. The key is shown only now.',
        `<div class="field"><label>Your key</label><input type="text" readonly value="${esc(k.key)}"></div>
         <div class="field"><label>Solara address</label><input type="text" readonly value="${esc(location.origin)}"></div>
         <ol class="hint" style="margin:0;padding-left:18px;display:grid;gap:4px">
           <li>Open <span class="mono">chrome://extensions</span>, switch on Developer mode, press Load unpacked and pick the <span class="mono">extension</span> folder.</li>
           <li>Open the co-pilot's Options, paste the address and the key, press Save.</li>
           <li>Log in to a portal yourself. On a customer's page the Solara panel appears at the bottom right.</li></ol>`,
        '<button class="btn" data-close>Done</button>');
    } catch (err) { toast(err.message, true); }
    return;
  }
  if (t.dataset.themeSet) {
    document.documentElement.setAttribute('data-theme', t.dataset.themeSet);
    try { localStorage.setItem('solara-theme', t.dataset.themeSet); } catch { }
    syncTheme(); return;
  }
  if (t.id === 'signout') { await api('/logout', { method: 'POST' }); S.me = null; showGate(); return; }
  if (t.hasAttribute('data-close')) return closeModal();
  if (t.dataset.act === 'escalate' || t.dataset.act === 'reject' || t.dataset.act === 'resend') {
    if (S.hold) send(S.hold, t.dataset.act, {});
    return;
  }

  /* run */
  if (t.id === 'bstart') {
    try {
      S.runStatus = 'starting'; paintRunState();
      const r = await api('/runs', { method: 'POST', body: {
        customer_id: S.runCid, workflow: $('#runwf').value, target_kw: $('#runkw').value,
        speed: S.speed, headless: !$('#headful').checked } });
      attachRun(r.run_id); toast('Run ' + r.run_id + ' started');
    } catch (err) { S.runStatus = 'idle'; paintRunState(); toast(err.message, true); }
    return;
  }
  if (t.id === 'bpause') {
    const to = S.runStatus === 'paused' ? 'resume' : 'pause';
    try { await api(`/runs/${S.activeRun}/${to}`, { method: 'POST' }); } catch (err) { toast(err.message, true); }
    return;
  }
  if (t.id === 'bstop') {
    try {
      await api(`/runs/${S.activeRun}/stop`, { method: 'POST' });
      closeModal(); S.hold = null; $('#holdSlot').innerHTML = '';
      toast('Run abandoned. Nothing was submitted.');
    } catch (err) { toast(err.message, true); }
    return;
  }
  if (t.dataset.speed) {
    S.speed = +t.dataset.speed;
    $$('[data-speed]').forEach(b => b.setAttribute('aria-pressed', String(b === t)));
    if (S.activeRun) api(`/runs/${S.activeRun}/speed`, { method: 'POST', body: { speed: S.speed } }).catch(() => { });
    return;
  }
  if (t.id === 'logcopy') {
    const txt = S.events.map(e2 => `${e2.ts}  [${e2.level}]  ${e2.message}`).join('\n');
    try { await navigator.clipboard.writeText(txt); toast('Run log copied'); } catch { toast('Copy blocked by the browser', true); }
    return;
  }
  if (t.dataset.shot !== undefined) {
    const s = S.shots[+t.dataset.shot];
    modal(s.label, 'Captured at ' + s.ts + ', stored with the run record',
      `<img src="${s.url}" alt="${esc(s.label)}" style="width:100%;border:1px solid var(--line);border-radius:var(--r)">`,
      '<button class="btn" data-close>Close</button>');
    return;
  }
  if (t.id === 'runpdf' || t.dataset.pdf) {
    window.open(`/api/exports/run/${t.dataset.pdf || S.activeRun}.pdf`, '_blank'); return;
  }
  if (t.id === 'xlsx') { window.open('/api/exports/pipeline.xlsx', '_blank'); return; }
  if (t.dataset.run) {
    S.view = 'run'; render(); pickRunCustomer(t.dataset.run);
    $('#bstart').click(); return;
  }

  if (t.id === 'drill') {
    t.disabled = true; t.textContent = 'Opening the newest backup…';
    try { const r = await api('/backup/verify', { method: 'POST' });
      toast(r.ok ? `Restore drill passed: ${r.file}, ${r.customers} customers, documents open with this key.` : `Restore drill FAILED: ${r.document}`, !r.ok); loadReports(); }
    catch (err) { toast(err.message, true); }
    return;
  }
  if (t.id === 'everything') { window.open('/api/exports/everything.zip', '_blank'); toast('Making the export. It holds Aadhaar copies: keep it like the paper files.'); return; }
  if (t.id === 'userAdd' || t.dataset.upass) {
    const who = t.dataset.upass;
    modal(who ? `New password for ${who}` : 'Add a person', who ? 'Their old password stops working at once.' : 'They sign in with their own username and password.',
      `${who ? '' : `<div class="field"><label for="uName">Name</label><input type="text" id="uName" autocomplete="off"></div>
       <div class="field"><label for="uUser">Username</label><input type="text" id="uUser" autocomplete="off" placeholder="e.g. s.kale"></div>
       <div class="field"><label for="uRole">Role</label><select id="uRole"><option>operator</option><option>viewer</option><option>supervisor</option></select></div>`}
       <div class="field"><label for="uPass">Password (10 or more characters)</label><input type="password" id="uPass" autocomplete="new-password"></div>`,
      `<button class="btn" data-close>Cancel</button><button class="btn go" id="userSave" data-who="${esc(who || '')}">Save</button>`);
    return;
  }
  if (t.id === 'userSave') {
    const who = t.dataset.who;
    const body = who ? { username: who, password: $('#uPass').value }
      : { username: $('#uUser').value, name: $('#uName').value, role: $('#uRole').value, password: $('#uPass').value };
    try { S.users = await api('/users', { method: 'POST', body }); closeModal(); render(); toast(who ? 'Password changed' : 'Added'); }
    catch (err) { toast(err.message, true); }
    return;
  }
  if (t.dataset.uremove) {
    if (!confirm(`Remove ${t.dataset.uremove}? They can no longer sign in. What they did stays in the audit trail.`)) return;
    try { S.users = await api('/users/' + encodeURIComponent(t.dataset.uremove), { method: 'DELETE' }); render(); toast('Removed'); }
    catch (err) { toast(err.message, true); }
    return;
  }
  if (t.id === 'backup') {
    try {
      const r = await api('/backup', { method: 'POST' });
      toast(`Backup written: ${r.file} (${Math.round(r.bytes / 1024)} KB)`); loadReports();
    } catch (err) { toast(err.message, true); }
    return;
  }
  if (t.id === 'resetdemo') {
    try {
      await api('/demo/reset', { method: 'POST' });
      S.steps = []; S.events = []; S.shots = []; S.activeRun = null; S.runStatus = 'idle';
      S.runWf = null; S.runKw = null;
      if (S.es) { S.es.close(); S.es = null; }
      $('#log').innerHTML = ''; $('#frame').hidden = true; $('#stageIdle').hidden = false;
      await refreshAfterRun(); S.reports = await api('/reports'); render();
      toast('Demo reset. Every run, screenshot and filing cleared.');
    } catch (err) { toast(err.message, true); }
    return;
  }

  /* documents */
  if (t.id === 'extract') {
    t.disabled = true; t.textContent = 'Parsing…';
    try { S.extract = await api(`/extract/${S.docCid}`, { method: 'POST' }); await refreshAfterRun(); render();
      const f = S.extract.fields.filter(x => x.status === 'review').length;
      toast(`${S.extract.fields.length} fields from ${S.extract.chars_parsed} characters of PDF text` + (f ? `, ${f} flagged` : ''));
    } catch (err) { toast(err.message, true); render(); }
    return;
  }

  /* numbers */
  if (t.dataset.inbox) {
    const rows = await api(`/numbers/${t.dataset.inbox}/inbox`);
    modal('Message inbox', 'Real rows from the sms table for this number.',
      `<div class="inbox">${rows.length ? rows.map(m => `<div class="sms">
        <div class="sf">${esc(m.sender)} &middot; ${esc(m.ts.replace('T', ' '))}${m.read_at ? ' &middot; read' : ''}</div>
        <div class="sx">${esc(m.body)}</div></div>`).join('') : '<div class="sms"><div class="sx">No messages.</div></div>'}</div>`,
      '<button class="btn" data-close>Close</button>');
    return;
  }
  for (const [key, path, msg] of [['otptest', 'test-otp', 'Test message delivered'],
    ['release', 'release', 'Number released to the pool'], ['assign', 'assign', 'Number assigned']]) {
    if (t.dataset[key]) {
      try { await api(`/numbers/${t.dataset[key]}/${path}`, { method: 'POST', body: {} }); toast(msg); await refreshAfterRun(); render(); }
      catch (err) { toast(err.message, true); }
      return;
    }
  }

  /* calls */
  if (t.dataset.call !== undefined) { S.callSel = +t.dataset.call; render(); playTranscript(true); return; }
  if (t.id === 'replay') { playTranscript(true); return; }
  if (t.id === 'togglemr') { S.showEn = !S.showEn; render(); return; }
});

document.addEventListener('input', e => {
  const t = e.target;
  if (t.dataset && (t.dataset.r || t.dataset.rule)) { regFieldCheck(t); regSyncButtons(); }
});
document.addEventListener('change', async e => {
  if (e.target.id === 'docCid') { S.docCid = e.target.value; S.extract = null; render(); loadExtract(S.docCid); }
  if (e.target.id === 'runcid') pickRunCustomer(e.target.value);
  if (e.target.id === 'runwf') { S.runWf = e.target.value; runHead(); }
  if (e.target.id === 'runkw') S.runKw = e.target.value;
  if (e.target.id === 'file' && e.target.files[0]) uploadBill(e.target.files[0]);
  if (e.target.dataset.doc && e.target.files[0]) {
    (S.regOpen ||= {}).regDocs = true;  // the owner is adding documents: keep the list open after the last one
    const fd = new FormData(); fd.append('file', e.target.files[0]);
    toast('Reading the document…');
    try {
      const r = await fetch(`/api/registration/${S.regCid}/document?kind=${e.target.dataset.doc}`, { method: 'POST', body: fd });
      const j = await r.json(); if (!r.ok) throw new Error(j.detail || r.statusText);
      S.regData = j; S.reg = await api('/registration'); render();
      const n = j.fields.filter(f => f.status === 'review' && !REG_LATER.includes(f.key)).length;
      toast(n ? `Read. ${n} detail${n > 1 ? 's' : ''} to check.` : 'Read. Nothing to check.');
    } catch (err) { toast(err.message, true); }
  }
  if (e.target.id === 'coPhoto' && e.target.files[0]) coUpload('photo', e.target.files[0]);
  if (e.target.dataset.receipt && e.target.files[0]) {
    const fd = new FormData(); fd.append('file', e.target.files[0]);
    try {
      const r = await fetch(`/api/filing/${S.instCid}/receipt?step=${e.target.dataset.receipt}`, { method: 'POST', body: fd });
      const j = await r.json(); if (!r.ok) throw new Error(j.detail || r.statusText);
      S.instData = j; render(); toast('Receipt saved');
    } catch (err) { toast(err.message, true); }
  }
  if (e.target.id === 'revStep') {
    closeModal(); instReview(e.target.value).catch(err => toast(err.message, true));
  }
  if (e.target.id === 'coSheet' && e.target.files[0]) coUpload('datasheet', e.target.files[0]);
});
$('#loginForm').addEventListener('submit', e => { e.preventDefault(); login($('#u').value, $('#p').value); });
$('#setupForm').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    S.me = await api('/setup', { method: 'POST', body: { name: $('#sName').value, username: $('#sUser').value, password: $('#sPass').value } });
    $('#gate').hidden = true; $('#shell').hidden = false; await boot();
  } catch (err) { showGate(err.message); }
});
$('#scrim').addEventListener('click', e => { if (e.target === $('#scrim')) closeModal(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

async function uploadBill(file) {
  const fd = new FormData(); fd.append('file', file);
  try {
    const r = await fetch(`/api/documents/${S.docCid}/upload?kind=bill`, { method: 'POST', body: fd });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    toast(`${file.name} stored, parsing it now`);
    S.extract = await api(`/extract/${S.docCid}`, { method: 'POST' });
    render();
  } catch (err) { toast(err.message, true); }
}
document.addEventListener('dragover', e => {
  const d = e.target.closest('#drop'); if (!d) return;
  e.preventDefault(); d.classList.add('over');
});
document.addEventListener('dragleave', e => {
  const d = e.target.closest('#drop'); if (d) d.classList.remove('over');
});
document.addEventListener('drop', e => {
  const d = e.target.closest('#drop'); if (!d) return;
  e.preventDefault(); d.classList.remove('over');
  if (e.dataTransfer.files[0]) uploadBill(e.dataTransfer.files[0]);
});

function syncTheme() {
  const t = document.documentElement.getAttribute('data-theme');
  $$('[data-theme-set]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.themeSet === t)));
}

/* ------------------------------ start ------------------------------ */
/* a live install shows only the real work: no demo accounts, no sandbox-only screens */
function liveMode() {
  S.live = true;
  $$('.whoami, [data-demo], .railfoot .hint').forEach(el => { el.hidden = true; }); // hidden, not removed: counters still update them
  $('#u').value = ''; $('#p').value = '';
  S.view = 'today'; // the owner's day starts with what to do now
}

(function init() {
  const mark = $('#markSvg').content.firstElementChild;
  $('#gateMark').appendChild(mark.cloneNode(true));
  $('#railMark').appendChild(mark.cloneNode(true));
  try { const t = localStorage.getItem('solara-theme'); if (t) document.documentElement.setAttribute('data-theme', t); } catch { }
  syncTheme();
  api('/me').then(async r => {
    if (r && r.live) liveMode();
    if (r && r.setup) { $('#setupForm').hidden = false; $('#loginForm').hidden = true; }
    if (!r || !r.user) return showGate();
    S.me = r.user; $('#gate').hidden = true; $('#shell').hidden = false; await boot();
  }).catch(() => showGate());
})();
