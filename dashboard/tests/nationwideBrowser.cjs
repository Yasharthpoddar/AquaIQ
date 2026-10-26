/* Real local published API data; injected failures are labelled test cases only.
 * Build to scratch/nationwide-ui-build; start isolated API on 127.0.0.1:5057.
 */
const { chromium }=require(process.env.AQUAIQ_PLAYWRIGHT || 'playwright');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),build=path.resolve(process.env.AQUAIQ_UI_BUILD || path.join(root,'scratch/nationwide-ui-build'));
const districts=JSON.parse(fs.readFileSync(process.env.AQUAIQ_DISTRICT_OUTPUTS || path.join(root,'scratch/nationwide-complete/districts.json')));
const apiBase=process.env.AQUAIQ_API_URL || 'http://127.0.0.1:5057',asOf=process.env.AQUAIQ_AS_OF || '2026-10-25';
const results=[],errors=[];let failForecast=false,failSummary=false;
const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://127.0.0.1');
  if(url.pathname.startsWith('/api/')) {
    if(!url.searchParams.has('as_of'))url.searchParams.set('as_of',asOf);
    const proxied=http.get(apiBase+url.pathname+url.search,r=>{res.writeHead(r.statusCode,r.headers);r.pipe(res);});
    proxied.on('error',()=>{res.writeHead(503,{'content-type':'application/json'});res.end(JSON.stringify({error:'Local browser test proxy unavailable'}));});
    return;
  }
  let file=path.resolve(build,'.'+decodeURIComponent(url.pathname));
  if(!file.startsWith(build+path.sep)&&file!==build){res.writeHead(403);res.end();return;}
  if(!fs.existsSync(file)||!fs.statSync(file).isFile())file=path.join(build,'index.html');
  res.setHeader('content-type',({'.js':'text/javascript','.css':'text/css','.json':'application/json','.geojson':'application/json','.html':'text/html','.svg':'image/svg+xml'})[path.extname(file)]||'application/octet-stream');
  res.end(fs.readFileSync(file));
});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base='http://127.0.0.1:'+server.address().port;
  const browser=await chromium.launch({headless:true,executablePath:process.env.AQUAIQ_CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',async route=>{
      const u=new URL(route.request().url());
      if(u.origin!==base)return route.abort();
      if(failSummary&&u.pathname==='/api/states/summary')return route.fulfill({status:503,json:{error:'Injected summary failure'}});
      if(failForecast&&u.pathname.startsWith('/api/predict/climate-12m/'))return route.fulfill({status:503,json:{error:'Injected forecast failure'}});
      return route.continue();
    });
    await page.goto(base+'/states/TS');
    await page.locator('.state-chart .recharts-line-curve').last().waitFor();
    await page.getByText(/Evidence mix:.*Tier B/).waitFor();
    assert.equal(await page.locator('.state-district-grid a').count(),33);
    await page.getByText('View all 12 monthly estimates',{exact:true}).click();
    assert.equal(await page.locator('.state-chart-card tbody tr').count(),12);
    results.push('State TS shows all registered districts, 12 months, and mixed evidence');
    for(const width of [1440,768,390]){
      await page.setViewportSize({width,height:1000});
      await page.waitForFunction(()=>document.documentElement.scrollWidth<=innerWidth);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      await page.screenshot({path:path.join(root,`scratch/state-complete-${width}.png`),fullPage:false});
    }
    results.push('State page has no horizontal overflow at desktop/tablet/mobile widths');
    for(const tier of ['A','B','C','D']){
      const value=Object.values(districts).find(d=>d.evidence_tier===tier);
      await page.goto(base+'/district/'+encodeURIComponent(value.district_id));
      const card=page.locator('#forecast-graph');
      await card.getByText(new RegExp('Evidence tier '+tier)).waitFor();
      await card.getByText(/View all 12 monthly/).click();
      assert.equal(await card.locator('tbody tr').count(),12);
      assert.match(await card.innerText(),new RegExp(value.observation_count+' genuine observed district months'));
      if(tier==='C')assert.match(await card.innerText(),/No local groundwater observations/);
      if(tier==='D')for(const field of ['rainfall_current','temperature','evapotranspiration'])assert.match(await card.innerText(),new RegExp(field));
      await card.screenshot({path:path.join(root,`scratch/district-tier-${tier}.png`)});
      results.push('District tier '+tier+' renders real published values, evidence and historical ranges');
    }
    failForecast=true;await page.reload();await page.locator('#forecast-graph').getByRole('alert').waitFor();
    failForecast=false;await page.locator('#forecast-graph').getByRole('button',{name:'Retry forecast'}).click();
    await page.locator('#forecast-graph').getByText(/Evidence tier D/).waitFor();results.push('District API failure and retry recover without hiding forecast card');
    failSummary=true;await page.goto(base+'/states/HR');await page.getByText('State comparison unavailable',{exact:true}).waitFor();
    await page.locator('.state-chart .recharts-line-curve').last().waitFor();
    failSummary=false;await page.getByRole('button',{name:'Retry state summary'}).click();
    await page.locator('.state-summary-scroll tbody tr').first().waitFor();
    results.push('State summary failure leaves selected state usable; retry recovers');
    const search=page.getByRole('combobox');await search.fill('tamil');await search.press('ArrowDown');await search.press('Enter');
    await page.getByRole('heading',{name:'Tamil Nadu forecast',exact:true}).waitFor();
    results.push('State search and keyboard navigation update the selected forecast');
    assert.deepEqual(errors,[]);
    const report={passed:results,errors,source:'real isolated published generation',as_of:asOf};
    fs.writeFileSync(process.env.AQUAIQ_BROWSER_REPORT || path.join(root,'reports/nationwide_20261025/browser.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
  } finally {await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
