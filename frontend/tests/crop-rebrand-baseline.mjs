// Preserve the full baseline and also provide exact viewport-size comparisons.
import fs from 'node:fs';
import { chromium } from 'playwright';
const browser = await chromium.launch();
const page = await browser.newPage();
for (const width of [1440, 390]) {
  const height = width === 1440 ? 900 : 844;
  await page.setViewportSize({ width, height });
  for (const name of ['overview', 'estimate', 'scenarios', 'export']) {
    const path = `test-artifacts/rebrand/before-${name}-${width}x${height}.png`;
    const full = path.replace('.png', '-full.png');
    if (!fs.existsSync(full)) fs.copyFileSync(path, full);
    const data = fs.readFileSync(full).toString('base64');
    await page.setContent(`<style>body{margin:0}img{display:block;width:${width}px}</style><img src="data:image/png;base64,${data}">`);
    await page.locator('img').evaluate(img => img.decode());
    await page.screenshot({ path });
  }
}
await browser.close();
