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
    window:{innerWidth:desktop ? 1200 : 390, matchMedia:()=>({matches:desktop})},
    location:{hash:'#K7M2QX9P', origin:'https://example.com', pathname:'/',search:''},
    navigator:{}, screen:{}, history:{replaceState(){}},
    localStorage:{getItem(){},setItem(){}}, sessionStorage:{getItem(){},setItem(){}},
    setInterval(){},setTimeout(){},clearTimeout(){}, AbortController,
    fetch:async () => { fetches++; return {ok:false}; },
    WebSocket:function(){sockets++;}, console
  };
  vm.runInNewContext(script, context);
  await new Promise(resolve => setImmediate(resolve));
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
