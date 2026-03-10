const { chromium } = require('playwright-core');
const path = require('path');

(async () => {
  const launchOptions = {
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  };

  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) {
    launchOptions.executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  }

  const browser = await chromium.launch(launchOptions);

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
