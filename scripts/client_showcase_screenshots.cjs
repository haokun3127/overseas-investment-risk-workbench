const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const base = process.env.SHOWCASE_BASE || 'http://127.0.0.1:8002';
const out = path.resolve(process.env.SHOWCASE_OUT || 'qa/client-showcase-20260914/images');
const password = 'UI-test-password-2026';

function clearImages() {
  fs.mkdirSync(out, { recursive: true });
  for (const name of fs.readdirSync(out)) {
    if (/\.(png|jpg|jpeg|webp)$/i.test(name)) fs.rmSync(path.join(out, name), { force: true });
  }
}

async function waitHeading(page, name) {
  await page.getByRole('heading', { name, exact: true }).waitFor({ state: 'visible' });
}

async function capture(page, name, label) {
  // Let transient notices disappear so the client pack shows the stable page state.
  await page.locator('#notice').waitFor({ state: 'hidden', timeout: 5200 }).catch(() => {});
  await page.screenshot({ path: path.join(out, `${name}.png`), fullPage: true });
  console.log(`captured ${label}: ${name}.png`);
}

async function navigate(page, hash, heading) {
  await page.goto(`${base}/${hash}`);
  await waitHeading(page, heading);
  await page.waitForTimeout(250);
}

(async () => {
  clearImages();
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
  const errors = [];
  page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error' && !/status of (401|409)/.test(message.text())) {
      errors.push(`console: ${message.text()}`);
    }
  });

  await page.goto(`${base}/`);
  await page.locator('#login-form').waitFor({ state: 'visible' });
  await capture(page, '01-login', '本地登录与首次初始化');
  await page.locator('input[name=password]').fill(password);
  if (await page.locator('input[name=confirm]').count()) await page.locator('input[name=confirm]').fill(password);
  await page.locator('#login-form button').click();
  await waitHeading(page, '风险总览');

  if (await page.locator('[data-demo]').count()) {
    await page.locator('[data-demo]').click();
    await page.getByText('示例：工业园区供电中断影响生产', { exact: true }).waitFor();
  }
  await page.waitForTimeout(300);
  if (await page.locator('[data-scope="demo"]').count()) {
    await page.locator('[data-scope="demo"]').click();
    await waitHeading(page, '风险总览');
  }
  await capture(page, '02-overview', '风险总览与风险信号');

  await navigate(page, '#events?demo=demo', '风险事件');
  await capture(page, '03-events', '风险事件筛选与台账');

  await navigate(page, '#overview?demo=demo', '风险总览');
  await page.getByText('示例：工业园区供电中断影响生产', { exact: true }).click();
  await page.getByRole('heading', { name: '判断依据与来源', exact: true }).waitFor();
  await page.waitForTimeout(250);
  await capture(page, '04-event-detail', '风险事件详情与业务复核');
  await page.getByRole('button', { name: '定位原文', exact: true }).first().click();
  await page.locator('#source-content mark').waitFor();
  await capture(page, '05-source-dialog', '原文追溯与引用高亮');
  await page.locator('#close-source').click();

  // Add clearly labelled synthetic records for demonstrating import, preflight and search controls.
  const requestHeaders = { 'X-Requested-With': 'risk-workbench' };
  const syntheticEvent = await page.request.post(`${base}/api/documents`, {
    headers: requestHeaders,
    data: {
      title: '甲方样例：印尼园区供应中断资料（合成）',
      date: '2026-09-10',
      source: '甲方演示材料（合成）',
      body: '本条资料为界面功能展示用合成文本。园区供应中断可能影响生产排期，应核实影响范围、恢复时间和替代供应方案。',
      kind: 'event',
      allow_external: false
    }
  });
  if (!syntheticEvent.ok()) throw new Error(`synthetic event creation failed: ${syntheticEvent.status()}`);
  const syntheticEventId = (await syntheticEvent.json()).id;
  const syntheticKnowledge = await page.request.post(`${base}/api/documents`, {
    headers: requestHeaders,
    data: {
      title: '甲方参考：园区供应中断应急处置（合成）',
      date: '2026-09-10',
      source: '甲方参考资料（合成）',
      body: '园区供应中断时，应核实停供范围与恢复时间，盘点库存缓冲，联系替代供应商，并保留现场记录供后续复盘。',
      kind: 'knowledge',
      allow_external: false
    }
  });
  if (!syntheticKnowledge.ok()) throw new Error(`synthetic knowledge creation failed: ${syntheticKnowledge.status()}`);

  await navigate(page, '#documents', '资料与导入');
  await capture(page, '06-documents', '资料导入、授权与分析入口');
  await page.locator(`[data-analyze="${syntheticEventId}"]`).click();
  await page.locator('#preflight-panel').waitFor({ state: 'visible' });
  await capture(page, '07-preflight', '分析前检查与阻断提示');
  await page.locator('#close-preflight').click();

  await navigate(page, '#knowledge', '知识库');
  await capture(page, '08-knowledge', '知识库资料与本地检索');
  await page.locator('#knowledge-search input').fill('供应中断');
  await page.getByRole('button', { name: '检索资料', exact: true }).click();
  await page.locator('.search-hit').first().waitFor();
  await capture(page, '09-knowledge-search', '知识库检索结果与原文入口');

  // The showcase instance disables the worker and model API. Add one queued row directly so the task page demonstrates queue state without running a real analysis.
  const dbPath = path.resolve(process.env.SHOWCASE_DB || 'qa/client-showcase-20260914/risk.db');
  execFileSync(path.resolve('.venv/Scripts/python.exe'), ['-c',
    'import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); db.execute("INSERT INTO jobs(document_id,status,created_at) VALUES (?,\'queued\',\'2026-09-14T09:00:00Z\')", (int(sys.argv[2]),)); db.commit()',
    dbPath, String(syntheticEventId)], { encoding: 'utf8' });
  await navigate(page, '#jobs', '分析任务');
  await capture(page, '10-jobs', '分析任务队列与状态');

  await navigate(page, '#report?demo=demo&level=red', '风险简报');
  await page.locator('.report-event').first().waitFor();
  await capture(page, '11-report', '风险简报与引用依据');

  await navigate(page, '#settings', '模型与规则');
  await capture(page, '12-settings', '模型接入、规则确认与运行状态');

  await page.setViewportSize({ width: 390, height: 844 });
  await navigate(page, '#overview?demo=demo', '风险总览');
  await capture(page, '13-mobile-overview', '移动端风险总览');
  await navigate(page, '#documents', '资料与导入');
  await capture(page, '14-mobile-documents', '移动端资料导入');
  if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)) {
    throw new Error('mobile viewport overflow detected');
  }

  await browser.close();
  if (errors.length) throw new Error(errors.join('\n'));
  console.log(`showcase screenshots complete: ${fs.readdirSync(out).length} image files`);
})().catch((error) => {
  console.error(error.stack || error.message || error);
  process.exit(1);
});
