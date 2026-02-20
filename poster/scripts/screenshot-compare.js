const { chromium } = require('/opt/node22/lib/node_modules/playwright/node_modules/playwright-core');
const path = require('path');

(async () => {
  const browser = await chromium.launch({
    executablePath: '/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome',
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  const posterPath = path.resolve(__dirname, '../html/zyra-poster.html');
  const fileUrl = `file://${posterPath}`;

  // Web view — full page screenshot
  console.log('Taking web view screenshot...');
  const webPage = await browser.newPage();
  await webPage.setViewportSize({ width: 1440, height: 900 });
  await webPage.goto(fileUrl, { waitUntil: 'networkidle' });
  await webPage.waitForTimeout(500);
  await webPage.screenshot({
    path: path.resolve(__dirname, '../html/screenshot-web.png'),
    fullPage: true,
  });
  console.log('Web view screenshot saved.');

  // Print view
  console.log('Taking print preview screenshot...');
  const printPage = await browser.newPage();
  await printPage.setViewportSize({ width: 14500, height: 11000 });
  await printPage.goto(fileUrl, { waitUntil: 'networkidle' });
  await printPage.waitForTimeout(500);
  await printPage.click('#toggleLink');
  await printPage.waitForTimeout(1500);

  // Crop individual sections for comparison
  const sections = [
    { sel: '.header', name: 'header' },
    { sel: '.pipeline-section', name: 'pipeline' },
    { sel: '.foundation-section', name: 'foundation' },
    { sel: '.get-started-footer', name: 'getstarted' },
  ];

  for (const s of sections) {
    const el = await printPage.$(s.sel);
    if (el) {
      await el.screenshot({
        path: path.resolve(__dirname, `../html/screenshot-print-${s.name}.png`),
      });
      console.log(`  ${s.name} crop saved.`);
    }
  }

  // Also get use case crops
  const ucCards = await printPage.$$('.usecase-card');
  for (let i = 0; i < ucCards.length; i++) {
    await ucCards[i].screenshot({
      path: path.resolve(__dirname, `../html/screenshot-print-uc${i}.png`),
    });
    console.log(`  usecase ${i} crop saved.`);
  }

  // Features
  const featCards = await printPage.$$('.features-card');
  if (featCards.length > 0) {
    await featCards[0].screenshot({
      path: path.resolve(__dirname, `../html/screenshot-print-features.png`),
    });
    console.log('  features crop saved.');
  }

  await browser.close();
  console.log('Done!');
})();
