/* Browser regression harness. Synthetic responses are confined to browser interception.
 * Uses an existing Playwright installation via NODE_PATH; installs no dependencies.
 * First build to scratch/xgb-states-build, then: node dashboard/tests/stateBrowser.cjs
 */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');

const root = path.resolve(__dirname, '../..');
const build = path.resolve(root, process.env.AQUAIQ_UI_BUILD || 'scratch/xgb-states-build');
const output = fs.mkdtempSync(path.join(root, 'scratch/state-browser-'));
const boundaries = JSON.parse(fs.readFileSync(path.join(root, 'dashboard/public/india_states.geojson')));
const version = '2.0-state-district-xgboost';
const states = boundaries.features.map(feature => ({ state_id: feature.properties.state_id,
  state_name: feature.properties.state_name, status: ['TN','HR'].includes(feature.properties.state_id) ? 'available' : 'insufficient_data',
  total_districts: 2, contributing_districts: ['TN','HR'].includes(feature.properties.state_id) ? 2 : 0,
  district_coverage_pct: ['TN','HR'].includes(feature.properties.state_id) ? 100 : 0,
  current_gwl_m_bgl: ['TN','HR'].includes(feature.properties.state_id) ? 10 : null,
  forecast_12m_gwl_m_bgl: ['TN','HR'].includes(feature.properties.state_id) ? 11.1 : null,
  projected_change_12m_m: ['TN','HR'].includes(feature.properties.state_id) ? 1.1 : null,
  last_observed_date: '2026-08-01' }));
const summary = {product:'state_groundwater_summary',model_version:version,horizon_months:12,as_of:'2026-10-25',
  computed_at:'2026-10-25T06:00:00Z',states,total_states:36,available_states_count:2,insufficient_data_states_count:34};
function forecast(id) {
  const state = states.find(s=>s.state_id===id), available=state?.status==='available';
  return {product:'state_groundwater_12m_forecast',model_version:version,model_name:'district_xgboost_equal_weight',state_id:id,state_name:state.state_name,
    units:'m_bgl',horizon_months:12,status:available?'forecast':'insufficient_data',as_of:summary.as_of,forecast_origin:'2026-10-01',computed_at:summary.computed_at,
    districts:[id+'-A',id+'-B'],contributing_district_ids:available?[id+'-A',id+'-B']:[],contributing_districts_count:available?2:0,
    total_districts_in_state:2,excluded_districts:[],district_coverage_pct:available?100:0,panel_id:'synthetic-test-panel',
    aggregation_method:'equal_weight_fixed_district_xgboost_panel',current_depth_basis:'estimated_district_inputs',estimated_current_gwl_m_bgl:available?10:null,
    history:[{date:'2026-08-01',gwl_m_bgl:9,contributing_districts_count:2,district_coverage_pct:100}],
    message:available?undefined:'Synthetic test: insufficient observations',
    limitations:['SYNTHETIC UI FIXTURE ONLY. These values are not observations or model results.'],
    forecast:available?Array.from({length:12},(_,i)=>({target_date:new Date(Date.UTC(2026,10+i,1)).toISOString().slice(0,10),horizon:i+1,predicted_gwl:10+i/10,delta_from_current_m:i/10})):[]};
}

(async()=>{
  const server=http.createServer((req,res)=>{
    const pathname=new URL(req.url,'http://localhost').pathname;
    const candidate=path.resolve(build,'.'+decodeURIComponent(pathname));
    if (!candidate.startsWith(build+path.sep) && candidate!==build) {res.writeHead(403);res.end();return;}
    const file=fs.existsSync(candidate)&&fs.statSync(candidate).isFile()?candidate:path.join(build,'index.html');
    const mime={'.js':'text/javascript','.css':'text/css','.json':'application/json','.geojson':'application/json','.html':'text/html','.svg':'image/svg+xml'};
    res.setHeader('Content-Type',mime[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const url='http://127.0.0.1:'+server.address().port;
  let browser;
  const results=[];
  try {
    browser=await chromium.launch({headless:true, executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined});
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[],requests=[];
    page.on('pageerror',error=>errors.push(error.message));
    let failSummary=false,failForecast=false,failBoundary=false,slowTN=false;
    await page.route('**/*',async route=>{
      const u=new URL(route.request().url());
      if(u.origin!==url) return route.abort(); // No external downloads, fonts or tiles.
      if(u.pathname==='/india_states.geojson') return route.fulfill({status:failBoundary?503:200,contentType:'application/json',body:JSON.stringify(boundaries)});
      if(!u.pathname.startsWith('/api/')) return route.continue();
      requests.push(u.pathname+u.search);
      if(u.pathname==='/api/states/summary') return route.fulfill({status:failSummary?503:200,json:failSummary?{error:'synthetic service failure'}:summary});
      const id=u.pathname.match(/^\/api\/predict\/state\/([A-Z]{2})$/)?.[1];
      if(id) {
        if(id==='TN'&&slowTN) await new Promise(resolve=>setTimeout(resolve,700));
        return route.fulfill({status:failForecast?503:200,json:failForecast?{...forecast(id),status:'model_unavailable',forecast:[],message:'Synthetic missing model'}:forecast(id)});
      }
      return route.fulfill({status:503,json:{error:'Synthetic test has no district service'}});
    });
    await page.goto(url+'/states/HR');
    const chart=page.locator('.state-chart-card');
    await chart.getByRole('heading',{name:'Haryana forecast',exact:true}).waitFor();
    await chart.locator('.recharts-line-curve').last().waitFor();
    assert.equal(await chart.locator('.recharts-legend-item-text').allTextContents().then(a=>a.filter(s=>s==='XGBoost Forecast').length),1);
    await chart.getByText('View all 12 monthly XGBoost values',{exact:true}).click();
    assert.equal(await chart.locator('tbody tr').count(),12);
    const search=page.getByRole('combobox');
    await search.fill('tamil');await search.press('ArrowDown');await search.press('Enter');
    await chart.getByRole('heading',{name:'Tamil Nadu forecast',exact:true}).waitFor();
    assert.ok(page.url().endsWith('/states/TN'));
    results.push('Search typing, ArrowDown/Enter selection, route and twelve forecast values');
    await page.getByRole('button',{name:'Select Haryana',exact:true}).click();
    await chart.getByRole('heading',{name:'Haryana forecast',exact:true}).waitFor();
    assert.equal(await page.getByRole('button',{name:'Select Haryana',exact:true}).getAttribute('aria-pressed'),'true');
    results.push('Map click selects and highlights correct state');
    slowTN=true;
    await search.fill('TN');await search.press('Enter');
    await page.getByRole('button',{name:'Select Haryana',exact:true}).click();
    await chart.getByRole('heading',{name:'Haryana forecast',exact:true}).waitFor();
    await page.waitForTimeout(850);
    assert.equal(await chart.getByRole('heading',{name:'Tamil Nadu forecast',exact:true}).count(),0);
    slowTN=false;results.push('Late response from previous state cannot replace selected state');
    const dot=chart.locator('.recharts-line-dot').last();await dot.hover({force:true});
    await chart.getByRole('tooltip').waitFor();
    assert.match(await chart.getByRole('tooltip').innerText(),/m bgl/);
    results.push('Hover displays date and depth');
    assert.equal(await page.locator('.state-district-grid a').first().getAttribute('href'),'/district/HR-A#forecast-graph');
    await search.fill('Ladakh');await search.press('Enter');
    await chart.getByText('XGBoost forecast unavailable',{exact:true}).waitFor();
    assert.equal(await chart.locator('.recharts-line-curve').count(),0);
    results.push('Sparse state abstains without fallback');
    failForecast=true;await search.fill('HR');await search.press('Enter');
    await chart.getByText('Synthetic missing model',{exact:true}).waitFor();
    failForecast=false;await chart.getByRole('button',{name:'Retry state forecast'}).click();
    await chart.getByRole('heading',{name:'Haryana forecast',exact:true}).waitFor();
    results.push('503 model failure and retry');
    for(const width of [1440,768,390]) {
      await page.setViewportSize({width,height:1000});await page.waitForTimeout(200);
      const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
      assert.equal(overflow,false,'page overflow at '+width);
      const box=await page.locator('.state-chart').boundingBox();assert.ok(box.width>0&&box.width<=width);
      await page.evaluate(()=>{const old=document.getElementById('fixture-label');old?.remove();const p=document.createElement('p');p.id='fixture-label';p.textContent='SYNTHETIC UI TEST — NOT REAL FORECASTS';p.style='position:fixed;bottom:0;left:0;background:#fff3cd;color:#000;padding:6px;z-index:9999';document.body.append(p);});
      await page.evaluate(()=>window.scrollTo(0,0));
      await page.screenshot({path:path.join(output,'synthetic-'+width+'.png'),fullPage:false});
      await chart.scrollIntoViewIfNeeded();
      await chart.screenshot({path:path.join(output,'synthetic-chart-'+width+'.png')});
    }
    results.push('Desktop, tablet and mobile chart/container widths');
    failSummary=true;await page.reload();await page.getByText('State dashboard unavailable',{exact:true}).waitFor();
    failSummary=false;await page.getByRole('button',{name:'Retry state dashboard'}).click();
    await chart.getByRole('heading',{name:'Haryana forecast',exact:true}).waitFor();
    failBoundary=true;await page.reload();await page.getByRole('button',{name:'Retry boundaries'}).waitFor();
    failBoundary=false;await page.getByRole('button',{name:'Retry boundaries'}).click();
    await page.getByRole('button',{name:'Select Haryana',exact:true}).waitFor();
    results.push('Summary failure, boundary failure and retries');
    assert.ok(requests.filter(u=>u.startsWith('/api/predict/')).every(u=>u.startsWith('/api/predict/state/')&&u.includes('horizon=12')&&u.includes('as_of=2026-10-25')));
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({fixture_type:'synthetic UI only',passed:results,requests,errors},null,2));
    console.log(JSON.stringify({output,passed:results},null,2));
  } finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
