// Solara as a desktop app. It starts Solara's own program (the same one Solara.exe is), shows it in a
// window, and stops it when the window is closed. The data lives in one folder that an update or an
// uninstall never touches. Portal and WhatsApp links open in the computer's browser, where the Chrome
// helper is.
const { app, BrowserWindow, Menu, shell, dialog, clipboard } = require('electron');
const { spawn } = require('child_process');
const http = require('http');
const path = require('path');
const fs = require('fs');

const PORT = +(process.env.SOLARA_PORT || 8900);
const URL_ = `http://127.0.0.1:${PORT}/`;
// the data: SOLARA_DATA when the installer set one, else a folder of its own under the user's profile
const DATA = process.env.SOLARA_DATA || path.join(app.getPath('userData'), 'data');
let backend = null, win = null, startedHere = false;

const answers = () => new Promise(done => {
  const req = http.get(URL_ + 'api/me', { timeout: 1500 }, res => { res.resume(); done(true); });
  req.on('error', () => done(false)); req.on('timeout', () => { req.destroy(); done(false); });
});

function startBackend() {
  fs.mkdirSync(DATA, { recursive: true });
  const env = { ...process.env, SOLARA_DATA: DATA, SOLARA_PORT: String(PORT), SOLARA_NO_BROWSER: '1', SOLARA_DESKTOP: '1' };
  const exe = path.join(process.resourcesPath, 'backend', 'Solara.exe');
  // installed: the bundled program. From source (npm start): python -m app.launcher in the project folder.
  backend = app.isPackaged ? spawn(exe, [], { env, cwd: path.dirname(exe), windowsHide: true })
    : spawn('python', ['-m', 'app.launcher'], { env, cwd: path.join(__dirname, '..'), windowsHide: true });
  startedHere = true;
  backend.on('exit', code => { backend = null; if (win && code) dialog.showErrorBox('Solara stopped', `Solara's program ended (code ${code}). The log is in ${path.join(DATA, 'logs')}.`); });
  backend.on('error', err => dialog.showErrorBox('Solara could not start', String(err.message || err)));
}

async function waitUntilUp(ms) {
  for (const end = Date.now() + ms; Date.now() < end;) {
    if (await answers()) return true;
    await new Promise(r => setTimeout(r, 400));
  }
  return false;
}

const local = u => u.startsWith(URL_) || u.startsWith(`http://localhost:${PORT}/`);

async function open() {
  win = new BrowserWindow({ width: 1360, height: 860, minWidth: 900, minHeight: 600, title: 'Solara', autoHideMenuBar: false,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true } });
  win.loadFile(path.join(__dirname, 'splash.html'));
  // the portals, WhatsApp and downloads of other sites belong in the browser that has the Chrome helper
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (local(url)) return { action: 'allow' };
    shell.openExternal(url); return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (e, url) => { if (!local(url) && !url.startsWith('file:')) { e.preventDefault(); shell.openExternal(url); } });
  win.on('closed', () => { win = null; });
  if (!(await answers())) startBackend();   // already running (Solara.exe, or a second window): use it
  if (!(await waitUntilUp(90000))) {
    dialog.showErrorBox('Solara did not start', `Nothing answered on ${URL_} after 90 seconds. The log is in ${path.join(DATA, 'logs')}.`);
    return app.quit();
  }
  if (win) win.loadURL(URL_);
}

Menu.setApplicationMenu(Menu.buildFromTemplate([
  { label: 'Solara', submenu: [
    { label: 'Open the data folder', click: () => shell.openPath(DATA) },
    { label: 'Open the backups', click: () => shell.openPath(path.join(DATA, 'backups')) },
    { label: 'Open the logs', click: () => shell.openPath(path.join(DATA, 'logs')) },
    { label: 'Show the Chrome helper folder (its path is copied too)', click: () => {
      const dir = app.isPackaged ? path.join(process.resourcesPath, 'backend', '_internal', 'extension') : path.join(__dirname, '..', 'extension');
      clipboard.writeText(dir); shell.openPath(dir);
      dialog.showMessageBox({ message: 'The Chrome helper folder', detail: dir + '\n\nThis path is copied. In Chrome: chrome://extensions, Developer mode on, Load unpacked, paste the path in the folder box, Select Folder.' });
    } },
    { type: 'separator' },
    { label: 'Open Solara in the browser', click: () => shell.openExternal(URL_) },
    { type: 'separator' }, { role: 'quit' }] },
  { label: 'View', submenu: [{ role: 'reload' }, { role: 'zoomIn' }, { role: 'zoomOut' }, { role: 'resetZoom' }, { role: 'togglefullscreen' }] },
]));

if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => { if (win) { if (win.isMinimized()) win.restore(); win.focus(); } });
  app.whenReady().then(open);
  app.on('window-all-closed', () => app.quit());
  // only the program this window started is stopped: a Solara that was already running is left alone
  app.on('before-quit', () => { if (backend && startedHere) { try { backend.kill(); } catch (e) { /* gone already */ } } });
}
