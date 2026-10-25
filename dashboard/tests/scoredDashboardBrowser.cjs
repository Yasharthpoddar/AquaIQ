/* Verify actual completed score data, alert filters, and national map bounds. */
const {chromium}=require(process.env.AQUAIQ_PLAYWRIGHT || 'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'../..'),base=process.env.AQUAIQ_UI_URL || 'http://127.0.0.1:5173';
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.AQUAIQ_CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const passed=[],errors=[];
  try {
    const page=await browser.newPage({viewport:{width:1440,height:1100}});
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/*',route=>new URL(route.request().url()).origin===new URL(base).origin?route.continue():route.abort());
    const response=await page.request.get(base+'/api/scores');assert.equal(response.status(),200);
    const data=await response.json();assert.equal(data.status,'success');assert.equal(data.total,725);
    assert.equal(Object.values(data.tier_counts).reduce((a,b)=>a+b,0),725);
    await page.goto(base+'/');
    await page.getByRole('heading',{name:'Project risk index',exact:true}).waitFor();
    await page.getByText('721 scored · 4 unavailable · 725 districts',{exact:false}).waitFor();
    const polygons=page.locator('.map-container path[role="button"]');
    await polygons.first().waitFor();
    // Multipart district geometries can have several paths for one identity.
    const labels=await polygons.evaluateAll(nodes=>nodes.map(n=>n.getAttribute('aria-label')));
    assert.equal(new Set(labels).size,724);
    const colours=await polygons.evaluateAll(nodes=>[...new Set(nodes.map(n=>n.getAttribute('fill')))]);
    assert.ok(colours.some(c=>['#22c55e','#eab308','#f97316','#ef4444'].includes(c)));
    passed.push('Actual 725-district score snapshot populates Home risk cards and district fills');
    for(const width of [1440,768,390]) {
      await page.setViewportSize({width,height:1100});
      await page.getByRole('button',{name:'Show all India',exact:true}).click();
      await page.waitForFunction(()=>{
        const container=document.querySelector('.map-container').getBoundingClientRect();
        const boxes=Array.from(document.querySelectorAll('.map-container path[role="button"]')).map(p=>p.getBoundingClientRect());
        return boxes.length>700 && boxes.every(b=>b.left>=container.left-4&&b.right<=container.right+4&&b.top>=container.top-4&&b.bottom<=container.bottom+4);
      });
      await page.waitForFunction(()=>document.documentElement.scrollWidth<=innerWidth);
      await page.locator('.map-wrapper').screenshot({path:path.join(root,`scratch/scored-map-${width}.png`)});
    }
    passed.push('Country-wide bounds and reset work at desktop/tablet/mobile widths');
    await page.getByRole('button',{name:'Open district Kaithal, Haryana',exact:true}).focus();
    await page.getByRole('button',{name:'Open district Kaithal, Haryana',exact:true}).press('Enter');
    await page.locator('#forecast-graph').getByText(/Evidence tier A/).waitFor();
    passed.push('Coloured registered polygon opens the matching published twelve-month forecast');
    await page.goto(base+'/alerts');
    await page.waitForFunction(()=>document.querySelectorAll('.alert-card').length===725);
    assert.equal(await page.getByText('Risk index unavailable',{exact:true}).count(),4);
    for(const tier of ['Crisis','Warning','Watch','Safe']) {
      await page.getByRole('button',{name:new RegExp(tier+'$')}).click();
      await page.waitForFunction(count=>document.querySelectorAll('.alert-card').length===count,data.tier_counts[tier]);
      const badges=await page.locator('.alert-badge').allTextContents();assert.ok(badges.every(text=>text.endsWith('— '+tier)));
    }
    passed.push('Alerts All includes 725 results; four unavailable indices remain explicit; each risk filter matches API counts');
    await page.getByRole('button',{name:/Crisis$/}).click();
    await page.waitForFunction(()=>document.querySelectorAll('.alert-card').length===6);
    await page.waitForFunction(()=>Array.from(document.querySelectorAll('.alert-card')).every(card=>Number(getComputedStyle(card).opacity)>.99));
    await page.screenshot({path:path.join(root,'scratch/scored-alerts.png'),fullPage:true});
    const href=await page.locator('.alert-district').first().getAttribute('href');
    await page.locator('.alert-district').first().click();
    assert.ok(page.url().includes(href));await page.locator('#forecast-graph .forecast-facts').waitFor();
    passed.push('Filtered alert opens the corresponding district outlook');
    assert.deepEqual(errors,[]);
    const report={passed,errors,tier_counts:data.tier_counts,scoring_run:data.districts[0].run_id};
    fs.writeFileSync(path.join(root,'scratch/scored-dashboard-browser.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report,null,2));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
