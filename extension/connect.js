// On Solara's own page only. "Connect the Chrome helper" there hands this browser's helper the address and a
// fresh key, so nothing is copied by hand. Only this page's own message is taken; the address is always this page's.
window.addEventListener('message', e => {
  if (e.source !== window || e.origin !== location.origin || !e.data || e.data.solara !== 'connect' || typeof e.data.key !== 'string') return;
  chrome.storage.local.set({ url: location.origin, key: e.data.key }).then(() => window.postMessage({ solara: 'connected' }, location.origin), () => {});
});
