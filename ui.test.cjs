// Local acceptance test: NODE_PATH=<playwright installation> node ui.test.cjs
// Uses an isolated browser, never the user's profile or real personal state.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||'chrome'});
 const context=await browser.newContext({viewport:{width:1440,height:1050},acceptDownloads:true});
 const page=await context.newPage(),errors=[],requests=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(r.url()));
 await page.goto(process.env.PREVIEW_URL||'http://127.0.0.1:8765/');await page.locator('.job').first().waitFor();
 assert.equal(await page.locator('#heading').innerText(),'待查看');
 const first=page.locator('.job').first(),title=await first.locator('.job-title').innerText();
 const n=requests.length;
 await first.getByRole('button',{name:'☆ 收藏',exact:true}).click();
 await page.getByRole('button',{name:/^收藏\s*\d/}).click();
 assert.ok((await page.locator('#jobs').innerText()).includes(title));
 await page.locator('.job').first().locator('.actions summary').click();
 await page.getByRole('button',{name:'已投递',exact:true}).click();
 await page.getByRole('button',{name:/^已投递\s*\d/}).click();
 assert.ok((await page.locator('#jobs').innerText()).includes(title));
 await page.reload();await page.getByRole('button',{name:/^已投递\s*\d/}).click();
 assert.ok((await page.locator('#jobs').innerText()).includes(title));
 await page.locator('.job').first().getByRole('button',{name:'已读',exact:true}).click();
 await page.getByRole('button',{name:'撤销',exact:true}).click();
 assert.ok(await page.locator('.job').first().getByRole('button',{name:'已读',exact:true}).isVisible());
 const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'导出记录'}).click()]);
 const downloadPath=await download.path();
 await page.locator('#import-file').setInputFiles(downloadPath);
 await page.getByRole('button',{name:/^待核实\s*\d/}).click();
 await page.getByRole('button',{name:'计划与库存',exact:true}).click();
 await page.getByRole('button',{name:'计划与库存',exact:true}).click();
 await page.locator('#more-filters summary').click();
 await page.locator('#status').selectOption('read');
 await page.getByRole('button',{name:'重置筛选',exact:true}).click();
 // No fetch/XHR at all, and no third-party asset requests while filtering.
 assert.ok(requests.every(u=>u.startsWith(process.env.PREVIEW_URL||'http://127.0.0.1:8765/')));
 assert.ok(requests.length<=10); // two document loads plus four versioned assets each
 assert.deepEqual(errors,[]);
 const clean=await browser.newContext({viewport:{width:1440,height:1050}}),desktop=await clean.newPage();
 await desktop.goto(process.env.PREVIEW_URL||'http://127.0.0.1:8765/');await desktop.locator('.job').first().waitFor();
 await desktop.screenshot({path:'output/desktop.png',fullPage:false});
 await desktop.keyboard.press('Tab');assert.ok(await desktop.locator('.skip').evaluate(n=>n===document.activeElement));
 const mobile=await browser.newContext({viewport:{width:390,height:844},isMobile:true,deviceScaleFactor:1}),mp=await mobile.newPage();
 await mp.goto(process.env.PREVIEW_URL||'http://127.0.0.1:8765/');await mp.locator('.job').first().waitFor();
 assert.ok(await mp.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
 await mp.screenshot({path:'output/mobile.png',fullPage:false});
 console.log(JSON.stringify({result:'pass',pageErrors:errors,networkRequests:requests.length,initialRequests:n,preview:['output/desktop.png','output/mobile.png']}));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
