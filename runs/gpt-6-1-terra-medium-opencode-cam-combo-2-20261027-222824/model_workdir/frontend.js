const pages = await (await fetch('http://127.0.0.1:9222/json')).json();
const page = pages.find(p => p.url === 'http://localhost:8770/index.html');
if (!page) throw Error('frontend not found');
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
let id = 1;
function call(method, params) {
  return new Promise((resolve, reject) => {
    const n = id++;
    const handler = e => { const v = JSON.parse(e.data); if (v.id === n) { ws.removeEventListener('message', handler); v.error ? reject(v.error) : resolve(v.result); } };
    ws.addEventListener('message', handler);
    ws.send(JSON.stringify({id:n, method, params}));
  });
}
const expression = `(() => {
  const tile = [...document.querySelectorAll('.tile')].find(t => t.querySelector('.name').textContent.includes('RealSense'));
  const select = tile.querySelector('select'); select.value = ''; select.dispatchEvent(new Event('change'));
  return JSON.stringify([...document.querySelectorAll('.tile')].map(t => ({name:t.querySelector('.name').textContent, selected:t.querySelector('select').selectedOptions[0]?.text, live:!!t.querySelector('video').srcObject, size:[t.querySelector('video').videoWidth,t.querySelector('video').videoHeight], message:t.querySelector('.msg').textContent})));
})()`;
console.log(JSON.stringify(await call('Runtime.evaluate', {expression, returnByValue:true}), null, 2));
ws.close();
