const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('web/index.html', 'utf8');
const script = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1];
async function run(desktop) {
  const nodes = new Map();
  const node = key => {
    if (!nodes.has(key)) nodes.set(key, {style:{}, classList:{add(){},remove(){}}, addEventListener(){}, textContent:''});
    return nodes.get(key);
  };
  let fetches = 0;
  let sockets = 0;
  const context = {
    document: {querySelector:node, querySelectorAll:()=>[], body:node('body'),
      documentElement:{}, addEventListener(){}},
    window:{addEventListener(){}, innerWidth:desktop ? 1200 : 390, matchMedia:()=>({matches:desktop})},
    location:{hash:'#K7M2QX9P', origin:'https://example.com', pathname:'/',search:''},
    navigator:{}, screen:{}, performance, history:{replaceState(){}},
    localStorage:{getItem(){},setItem(){}}, sessionStorage:{getItem(){},setItem(){}},
    setInterval(){},setTimeout(){},clearTimeout(){}, AbortController,
    fetch:async () => { fetches++; return {ok:false}; },
    WebSocket:function(){sockets++;}, console
  };
  const timers = [];
  context.setTimeout = fn => { timers.push(fn); return timers.length; };
  vm.runInNewContext(script, context);
  await new Promise(resolve => setImmediate(resolve));
  // Settings must send over the connected channel, not fetch a phone-local URL.
  vm.runInNewContext("link = {send() {}, settings(r) { globalThis.lastRequest = r; }}", context);
  node('#openSettings').onclick();
  assert.equal(node('#settingsPanel').hidden, false);
  assert.equal(context.lastRequest.action, 'get');
  context.reply = {id:context.lastRequest.id, mode:'keyboard', controls:[], keys:[], mappings:{}};
  vm.runInNewContext('receiveSettings(reply)', context);
  assert.equal(node('#savePhoneSettings').disabled, false);
  assert.match(node('#settingsMessage').textContent, /PC replied/);
  node('#savePhoneSettings').onclick();
  assert.equal(context.lastRequest.action, 'save');
  // Transport not ready should report an immediate failure, not a timeout.
  vm.runInNewContext("link.settings = () => false", context);
  node('#reloadPhoneSettings').onclick();
  assert.match(node('#settingsMessage').textContent, /Request not sent/);
  vm.runInNewContext("mode = 'relay'; pcSeenAt = 0; pcInfo = null", context);
  assert.match(vm.runInNewContext("settingsFailure('get')", context), /No PC heartbeat/);
  vm.runInNewContext("pcSeenAt = Date.now(); pcInfo = {}", context);
  assert.match(vm.runInNewContext("settingsFailure('get')", context), /older running copy/);
  vm.runInNewContext("pcInfo = {capabilities:['settings-v1']}", context);
  assert.match(vm.runInNewContext("settingsFailure('save')", context), /may have reached/);
  vm.runInNewContext("globalThis.readCount = 0; link.settings = () => { readCount++; return true; }", context);
  node('#reloadPhoneSettings').onclick();
  timers.at(-1)(); timers.at(-1)(); timers.at(-1)();
  assert.equal(context.readCount, 3);
  assert.match(node('#settingsMessage').textContent, /after retries/);
  vm.runInNewContext("readCount = 0", context);
  node('#savePhoneSettings').onclick();
  timers.at(-1)();
  assert.equal(context.readCount, 1, 'save must not retry automatically');
  node('#closeSettings').onclick();
  assert.equal(node('#settingsPanel').hidden, true);
  assert.match(html, /data-b="options">Options/);
  assert.equal(sockets, 0, 'no automatic controller connection on either device');
  if(desktop) {
    assert.equal(fetches,0, 'desktop stays on PC pairing screen');
    assert.match(node('#desktopcode').textContent,/K7M2QX9P/);
  } else {
    assert.equal(node('#code').value,'K7M2QX9P');
    assert.match(node('#pstatus').textContent,/tap Connect/);
    assert.equal(typeof node('#go').onclick,'function');
  }
}
(async()=>{await run(true);await run(false);console.log('Desktop pairing / phone tap-to-connect tests passed');})().catch(e=>{console.error(e);process.exitCode=1;});
