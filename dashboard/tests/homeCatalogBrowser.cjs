/* Regression for the user's Home screenshot: scores missing/failed/delayed.
 * Uses the running local frontend/backend; no model or scoring job is started.
 */
const {chromium}=require(process.env.AQUAIQ_PLAYWRIGHT || 'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'../..'),base=process.env.AQUAIQ_UI_URL || 'http://127.0.0.1:5173';
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.AQUAIQ_CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const passed=[],errors=[];
  try {
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    page.on('pageerror',e=>errors.push(e.message));let mode='empty',registryFailure=false;
    await page.route('**/*',async route=>{
      const url=new URL(route.request().url());
      if(url.origin!==new URL(base).origin)return route.abort();
      if(url.pathname==='/api/scores') {
        if(mode==='slow')await new Promise(resolve=>setTimeout(resolve,2500));
        return route.fulfill({status:mode==='error'?503:200,json:mode==='error'?{error:'Injected score failure'}:{status:'awaiting_complete_scoring_run',total:0,districts:[]}});
      }
      if(registryFailure&&url.pathname==='/api/districts')return route.fulfill({status:503,json:{error:'Injected registry failure'}});
      return route.continue();
    });
    for(mode of ['empty','error','slow']) {
      await page.goto(base+'/');
      await page.getByText('725 / 725 districts',{exact:true}).waitFor();
      const search=page.getByRole('combobox',{name:'Search district',exact:true});
      await search.waitFor();await page.waitForFunction(()=>!document.querySelector('[role="combobox"]').disabled);
      assert.equal(await search.isEnabled(),true);
      if(mode==='empty') {
        for(const width of [1440,768,390]) {
          await page.setViewportSize({width,height:1000});await page.waitForFunction(()=>document.documentElement.scrollWidth<=innerWidth);
          await page.screenshot({path:path.join(root,`scratch/home-catalog-${width}.png`),fullPage:false});
        }
        const polygon=page.getByRole('button',{name:'Open district Kaithal, Haryana',exact:true});
        await polygon.focus();await polygon.press('Enter');
      } else {await search.fill('HR-Kaithal');await search.press('Enter');}
      await page.locator('#forecast-graph').getByText(/Evidence tier A/).waitFor();
      assert.ok(page.url().includes('/district/HR-Kaithal'));
      passed.push(mode+' risk scores: registry search/map and actual district forecast remain usable');
    }
    mode='empty';await page.goto(base+'/');
    const search=page.getByRole('combobox',{name:'Search district',exact:true});
    await search.fill('AN-Nicobars');await search.press('Enter');
    await page.locator('#forecast-graph').getByText(/Evidence tier C/).waitFor();
    passed.push('Zero-history district remains searchable and opens its reference estimate');
    await page.goto(base+'/simulate');
    const simulate=page.getByRole('combobox',{name:'Simulation district',exact:true});
    await simulate.waitFor();await page.waitForFunction(()=>!document.querySelector('[role="combobox"]').disabled);
    await simulate.fill('AN-Nicobars');await simulate.press('Enter');
    assert.equal(await page.getByRole('button',{name:'Run scenario',exact:true}).isEnabled(),true);
    passed.push('Simulate can select any registered district without a completed scoring run');
    registryFailure=true;await page.goto(base+'/');
    await page.getByRole('button',{name:'Retry district list',exact:true}).waitFor();
    assert.equal(await page.getByRole('combobox',{name:'Search district',exact:true}).isDisabled(),true);
    await page.getByText('725 / 725 districts',{exact:true}).waitFor();
    registryFailure=false;await page.getByRole('button',{name:'Retry district list',exact:true}).click();
    await page.waitForFunction(()=>!document.querySelector('[role="combobox"]').disabled);
    passed.push('Actual registry failure is shown separately; retry restores search');
    assert.deepEqual(errors,[]);
    const report={passed,errors};fs.writeFileSync(path.join(root,'scratch/home-catalog-browser.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report,null,2));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
