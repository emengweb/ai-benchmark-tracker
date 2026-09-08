// render_page.cjs — 用 Playwright 渲染动态页面并输出正文文本（供 render_sources.py 调用）
//
// 用法：node render_page.cjs <url> [waitMs] [selector]
// 输出：stdout 一行 JSON：{status, finalUrl, title, text} 或 {status:"error", error}
//
// 依赖：全局 playwright 包（npm i -g playwright && playwright install chromium），
// 由 Python 侧以 NODE_PATH=$(npm root -g) 注入；ESM 不读 NODE_PATH，故用 CJS。
const { chromium } = require('playwright');

async function main() {
  const url = process.argv[2];
  const waitMs = parseInt(process.argv[3] || '8000', 10);
  const selector = process.argv[4] || null;
  if (!url) {
    console.log(JSON.stringify({ status: 'error', error: 'usage: node render_page.cjs <url> [waitMs] [selector]' }));
    process.exit(1);
  }
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-blink-features=AutomationControlled'],
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 }).catch((e) => {
      console.log(JSON.stringify({ status: 'goto_error', error: String(e).slice(0, 300), finalUrl: page.url(), title: '' , text: '' }));
    });
    if (selector) {
      await page.waitForSelector(selector, { timeout: 20000 }).catch(() => {});
    }
    await page.waitForTimeout(waitMs);
    const text = await page.evaluate(() => document.body ? document.body.innerText : '');
    const title = await page.title();
    console.log(JSON.stringify({ status: 'ok', finalUrl: page.url(), title, text }));
  } catch (e) {
    console.log(JSON.stringify({ status: 'error', error: String(e).slice(0, 500) }));
  } finally {
    await browser.close().catch(() => {});
  }
}

main();