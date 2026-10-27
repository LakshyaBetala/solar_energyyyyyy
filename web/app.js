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
  pipeline: ['Pipeline', 'Every live application and the stage it is sitting at.'],
  run: ['Agent Runs', 'A real browser session filing an application. It stops for OTP, CAPTCHA, corrections and approval.'],
  docs: ['Document Intake', 'Parses the actual PDFs on disk and flags anything that does not agree. Drop in your own bill to try it.'],
  numbers: ['Number Pool', 'One dedicated mobile number per registration, held for 90 days.'],
  calls: ['AI Calling', 'Reminder, status and scheduling calls in Marathi, Hindi and English.'],
  audit: ['Audit Trail', 'Who did what, and when. Append-only, written by the server.'],
  reports: ['Reports', 'What the agent actually did, and the exports you can hand to anyone.']
};

const S = {
  view: 'pipeline', me: null, customers: [], numbers: [], calls: [], audit: [], llm: {},
  runs: [], activeRun: null, callSel: 0, showEn: true, docCid: 'SS-2045', extract: null,
  reports: null, steps: [], events: [], shots: [], hold: null, runStatus: 'idle', speed: 1,
  headless: true, es: null, lastFrame: null, t0: null,
  runCid: 'SS-2045', runWf: null, runKw: null, workflows: [], followups: []
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
  if (!r.ok) throw new Error((data && data.detail) || r.statusText);
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
  const b = await api('/bootstrap');
  S.me = b.user; S.customers = b.customers; S.numbers = b.numbers; S.calls = b.calls;
  S.audit = b.audit; S.llm = b.llm; S.runs = b.runs; S.activeRun = b.active_run;
  S.workflows = b.workflows || [];
  S.followups = await api('/followups').catch(() => []);
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
}

function counters() {
  $('#tagPipe').textContent = S.customers.length;
  $('#tagNum').textContent = S.numbers.length;
  $('#tagCalls').textContent = S.calls.length;
  const flagged = S.customers.reduce((a, c) => a + (c.flagged || 0), 0);
  $('#tagDocs').textContent = flagged;
  $('#tagDocs').className = 'tag' + (flagged ? ' hot' : '');
  $('#tagAudit').textContent = S.audit.length;
  const live = ['running', 'held', 'paused', 'starting'].includes(S.runStatus);
  $('#tagRun').textContent = live ? (S.runStatus === 'held' ? 'held' : 'live') : S.runStatus;
  $('#tagRun').className = 'tag' + (live ? ' live' : S.runStatus === 'failed' || S.runStatus === 'stopped' ? ' hot' : '');
}

/* ------------------------------ render ------------------------------ */
const VIEWS = {};
function render() {
  $('#crumb').textContent = TITLES[S.view][0];
  $('#crumbsub').textContent = TITLES[S.view][1];
  $$('.navitem').forEach(b => b.setAttribute('aria-current', String(b.dataset.view === S.view)));
  const rv = $('#runview'), ov = $('#otherview');
  rv.hidden = S.view !== 'run'; ov.hidden = S.view === 'run';
  if (S.view === 'run') { runHead(); paintSteps(); paintShots(); paintRunState(); }
  else {
    ov.innerHTML = VIEWS[S.view]();
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
  return `<div class="grid" style="gap:14px">
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
        : banner('', `Held at step ${esc(c.step)}. Nothing is submitted while this is open.`)) +
      `<div class="inbox"><div class="ih"><span class="dot on"></span><b class="mono">${esc(c.msisdn)}</b>
        <span class="spacer"></span><span>dedicated number for this registration</span></div>
        ${(c.inbox || []).map(m => `<div class="sms"><div class="sf">${esc(m.sender)} &middot; ${esc((m.ts || '').slice(11))}</div>
          <div class="sx">${esc(m.body)}</div></div>`).join('') || '<div class="sms"><div class="sx">No messages yet.</div></div>'}
      </div>
      <div class="otpin">${[0, 1, 2, 3, 4, 5].map(i => `<input id="o${i}" inputmode="numeric" maxlength="1" aria-label="digit ${i + 1}">`).join('')}</div>
      <div class="hint" style="text-align:center">${esc(c.hint)}</div>`,
      `<button class="btn" data-act="escalate">Escalate</button><span class="spacer"></span>
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
    <div class="kpi"><div class="k">Monthly cost</div><div class="v">&#8377;${n.length * 149}</div>
      <div class="d">&#8377;149 per number · 90-day retention</div></div>
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
    <div class="audit" style="max-height:58vh;overflow-y:auto">${S.audit.map(a => `
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
VIEWS.reports = () => {
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
      <button class="btn danger" id="resetdemo"${can('supervisor') ? '' : ' disabled'}>Reset the demo environment</button>
      ${S.runs.filter(x => x.status === 'done' || x.status === 'failed').slice(0, 6).map(x =>
      `<button class="btn" data-pdf="${x.id}">Run ${x.id} report — ${esc(x.customer_id)} (.pdf)</button>`).join('')}
      <div class="hint">Both are produced server-side: openpyxl for the workbook, Chromium print-to-PDF
        for the report, which embeds the run's screenshots.</div>
    </div></div>
  </div>
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
document.addEventListener('click', async e => {
  const t = e.target.closest('button'); if (!t) return;

  if (t.dataset.as) { $('#u').value = t.dataset.as; $('#p').value = 'demo'; return login(t.dataset.as, 'demo'); }
  if (t.dataset.view) { S.view = t.dataset.view; render(); if (S.view === 'docs' && !S.extract) loadExtract(S.docCid); if (S.view === 'reports') api('/reports').then(r => { S.reports = r; render(); }); return; }
  if (t.dataset.themeSet) {
    document.documentElement.setAttribute('data-theme', t.dataset.themeSet);
    try { localStorage.setItem('solara-theme', t.dataset.themeSet); } catch { }
    syncTheme(); return;
  }
  if (t.id === 'signout') { await api('/logout', { method: 'POST' }); S.me = null; showGate(); return; }
  if (t.hasAttribute('data-close')) return closeModal();
  if (t.dataset.act === 'escalate' || t.dataset.act === 'reject') {
    if (S.hold) send(S.hold, t.dataset.act === 'reject' ? 'reject' : 'escalate', {});
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

  if (t.id === 'backup') {
    try {
      const r = await api('/backup', { method: 'POST' });
      toast(`Backup written: ${r.file} (${Math.round(r.bytes / 1024)} KB)`);
      window.open('/api/backups/' + encodeURIComponent(r.file), '_blank');
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

document.addEventListener('change', async e => {
  if (e.target.id === 'docCid') { S.docCid = e.target.value; S.extract = null; render(); loadExtract(S.docCid); }
  if (e.target.id === 'runcid') pickRunCustomer(e.target.value);
  if (e.target.id === 'runwf') { S.runWf = e.target.value; runHead(); }
  if (e.target.id === 'runkw') S.runKw = e.target.value;
  if (e.target.id === 'file' && e.target.files[0]) uploadBill(e.target.files[0]);
});
$('#loginForm').addEventListener('submit', e => { e.preventDefault(); login($('#u').value, $('#p').value); });
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
(function init() {
  const mark = $('#markSvg').content.firstElementChild;
  $('#gateMark').appendChild(mark.cloneNode(true));
  $('#railMark').appendChild(mark.cloneNode(true));
  try { const t = localStorage.getItem('solara-theme'); if (t) document.documentElement.setAttribute('data-theme', t); } catch { }
  syncTheme();
  api('/me').then(async r => {
    if (!r || !r.user) return showGate();
    S.me = r.user; $('#gate').hidden = true; $('#shell').hidden = false; await boot();
  }).catch(() => showGate());
})();
