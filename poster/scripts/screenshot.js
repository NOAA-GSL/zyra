const { chromium } = require('/opt/node22/lib/node_modules/playwright/node_modules/playwright-core');
const path = require('path');

(async () => {
  const browser = await chromium.launch({
    executablePath: '/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome',
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  // Use the dedicated print page — no toggle needed
  const posterPath = path.resolve(__dirname, '../html/zyra-poster-print.html');
  const fileUrl = `file://${posterPath}`;

  console.log('Taking print screenshot (14400×10800 poster)...');
  const page = await browser.newPage();
  await page.setViewportSize({ width: 14500, height: 11000 });
  await page.goto(fileUrl, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);

  const poster = await page.$('.poster');
  if (poster) {
    await poster.screenshot({
      path: path.resolve(__dirname, '../html/screenshot-print.png'),
    });
    console.log('Print screenshot saved.');
  }

  await browser.close();
  console.log('Done!');
})();
