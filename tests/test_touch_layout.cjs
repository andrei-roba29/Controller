// npm install --no-save --package-lock=false playwright @sparticuz/chromium
// node tests/test_touch_layout.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const chromiumPackage = require('@sparticuz/chromium');
const bundledChromium = chromiumPackage.default;
(async () => {
  // The bundled Linux build includes NSS/NSPR for minimal CI workspaces.
  const libDir = await chromiumPackage.inflate(path.join(path.dirname(require.resolve('@sparticuz/chromium')), '../bin/al2023.tar.br'));
  const browser = await chromium.launch({executablePath: await bundledChromium.executablePath(),
    args:bundledChromium.args, headless:true,
    env:{...process.env, LD_LIBRARY_PATH:path.join(libDir, 'lib') + ':' + (process.env.LD_LIBRARY_PATH || '')}});
  try {
    const context = await browser.newContext({isMobile:true, hasTouch:true});
    const page = await context.newPage();
    await page.route('**/*', route => {
      const name = new URL(route.request().url()).pathname.slice(1) || 'index.html';
      if (!['index.html','relay.js','config.json'].includes(name)) return route.fulfill({status:404, body:''});
      return route.fulfill({body:fs.readFileSync(path.join(__dirname, '../web', name)),
        contentType:name.endsWith('.js') ? 'application/javascript' : name.endsWith('.json') ? 'application/json' : 'text/html'});
    });
    await page.goto('http://padlink.test/');
    await page.evaluate(() => {
      goFull = () => {};
      mode = 'lan'; window.sentInputs = []; link = {send(s){ window.sentInputs.push(s); }, settings(){}};
      document.querySelector('#wrongdev').classList.remove('show');
      enterPad();
    });
    for (const [width,height] of [[568,320],[640,360],[667,375],[740,360],[812,375],[844,390],[915,412],[932,430],[1024,600]]) {
      await page.setViewportSize({width,height});
      await page.evaluate(() => { fitController(); window.sentInputs = []; });
      const errors = await page.evaluate(() => {
        const controls = [...document.querySelectorAll('[data-b], [data-s], #openSettings')];
        const failures = [];
        const rects = controls.map(el => ({el, r:el.getBoundingClientRect()}));
        for (const {el,r} of rects) {
          const name = el.dataset.b || el.dataset.s || el.id;
          if(r.left < 0 || r.right > innerWidth || r.top < 0 || r.bottom > innerHeight) failures.push(name + ' off screen');
          for (const [fx,fy] of [[.5,.5],[.3,.5],[.7,.5],[.5,.3],[.5,.7]]) {
            const hit = document.elementFromPoint(r.x+r.width*fx, r.y+r.height*fy);
            if(hit !== el && !el.contains(hit)) failures.push(name + ' hit ' + hit?.outerHTML);
          }
          for (const other of rects) {
            if(other.el === el) continue;
            const overlapX = Math.min(r.right,other.r.right) - Math.max(r.left,other.r.left);
            const overlapY = Math.min(r.bottom,other.r.bottom) - Math.max(r.top,other.r.top);
            if(overlapX > .1 && overlapY > .1) failures.push(name + ' overlaps ' + (other.el.dataset.b || other.el.dataset.s || other.el.id));
          }
        }
        return failures;
      });
      assert.deepEqual(errors, [], `${width}x${height}: control hit regions must be separate`);
      const triangle = await page.locator('[data-b="triangle"]').boundingBox();
      await page.touchscreen.tap(triangle.x + triangle.width/2, triangle.y + triangle.height/2);
      assert.equal(await page.evaluate(() => window.sentInputs.some(s => s.b.includes('triangle'))), true, 'triangle press must be delivered');
      assert.equal(await page.evaluate(() => window.sentInputs.some(s => s.rx !== 128 || s.ry !== 128)), false, 'triangle must never move right stick');
      await page.evaluate(() => { window.sentInputs = []; });
      const settings = await page.locator('#openSettings').boundingBox();
      await page.touchscreen.tap(settings.x+settings.width/2,settings.y+settings.height/2);
      assert.equal(await page.locator('#settingsPanel').isVisible(), true, 'Settings must open');
      assert.equal(await page.evaluate(() => window.sentInputs.some(s => s.b.includes('touchpad'))), false, 'Settings must never press touchpad');
      await page.locator('#closeSettings').click();
      console.log(`${width}x${height}: no overlaps; taps hit correct controls`);
    }
    const cdp = await context.newCDPSession(page);
    const stick = await page.locator('[data-s="r"]').boundingBox();
    const first = {id:1, x:stick.x+stick.width*.25, y:stick.y+stick.height*.5};
    const second = {id:2, x:stick.x+stick.width*.75, y:stick.y+stick.height*.5};
    await cdp.send('Input.dispatchTouchEvent', {type:'touchStart', touchPoints:[first]});
    const heldX = await page.evaluate(() => st.rx);
    assert.ok(heldX < 128);
    await cdp.send('Input.dispatchTouchEvent', {type:'touchStart', touchPoints:[first,second]});
    assert.equal(await page.evaluate(() => st.rx), heldX, 'second finger must not take over stick');
    await cdp.send('Input.dispatchTouchEvent', {type:'touchEnd', touchPoints:[second]});
    assert.equal(await page.evaluate(() => st.rx), heldX, 'second finger ending must not release stick');
    await cdp.send('Input.dispatchTouchEvent', {type:'touchEnd', touchPoints:[]});
    assert.equal(await page.evaluate(() => st.rx), 128);
    const cross = await page.locator('[data-b="cross"]').boundingBox();
    const a = {id:3, x:cross.x+cross.width*.4, y:cross.y+cross.height*.5};
    const b = {id:4, x:cross.x+cross.width*.6, y:cross.y+cross.height*.5};
    await cdp.send('Input.dispatchTouchEvent', {type:'touchStart', touchPoints:[a]});
    await cdp.send('Input.dispatchTouchEvent', {type:'touchStart', touchPoints:[a,b]});
    await cdp.send('Input.dispatchTouchEvent', {type:'touchEnd', touchPoints:[b]});
    assert.equal(await page.evaluate(() => st.b.has('cross')), true, 'button stays held until all fingers release');
    await cdp.send('Input.dispatchTouchEvent', {type:'touchEnd', touchPoints:[]});
    assert.equal(await page.evaluate(() => st.b.has('cross')), false);
    console.log('Multi-touch pointer ownership passed');
    await context.close();
  } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exitCode = 1;});
