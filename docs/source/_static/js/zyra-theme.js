// Compute contrast ratios and provide a simple theme toggle demo
(function () {
  function hexToRgb(hex) {
    const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex.trim());
    if (!m) return null;
    return { r: parseInt(m[1], 16), g: parseInt(m[2], 16), b: parseInt(m[3], 16) };
  }

  function srgbToLin(c) {
    const cs = c / 255;
    return cs <= 0.03928 ? cs / 12.92 : Math.pow((cs + 0.055) / 1.055, 2.4);
  }

  function relLuminance(rgb) {
    const R = srgbToLin(rgb.r);
    const G = srgbToLin(rgb.g);
    const B = srgbToLin(rgb.b);
    return 0.2126 * R + 0.7152 * G + 0.0722 * B;
  }

  function contrastRatio(hex1, hex2) {
    const rgb1 = hexToRgb(hex1);
    const rgb2 = hexToRgb(hex2);
    if (!rgb1 || !rgb2) return null;
    const L1 = relLuminance(rgb1) + 0.05;
    const L2 = relLuminance(rgb2) + 0.05;
    const ratio = L1 > L2 ? L1 / L2 : L2 / L1;
    return Math.round(ratio * 100) / 100; // 2 decimals
  }

  function annotateSwatches() {
    const metas = document.querySelectorAll('.swatch .meta');
    metas.forEach((meta) => {
      const text = meta.textContent || '';
      const m = text.match(/#([0-9A-Fa-f]{6})/g);
      if (!m || m.length === 0) return;
      const hex = m[m.length - 1]; // last hex on the line
      const ratioWhite = contrastRatio(hex, '#FFFFFF');
      const ratioDark = contrastRatio(hex, '#232323'); // Neutral 900
      const AA = 4.5; // AA normal text
      const AAA = 7.0; // AAA normal text

      function mk(label, ratio) {
        const row = document.createElement('div');
        row.className = 'contrast';
        row.style.fontSize = '0.8em';
        const aaSpan = document.createElement('span');
        aaSpan.className = 'result ' + (ratio >= AA ? 'pass' : ratio >= 3.0 ? 'warn' : 'fail');
        aaSpan.textContent = `AA ${ratio >= AA ? 'pass' : 'fail'}`;
        const aaaSpan = document.createElement('span');
        aaaSpan.className = 'result ' + (ratio >= AAA ? 'pass' : 'fail');
        aaaSpan.textContent = `AAA ${ratio >= AAA ? 'pass' : 'fail'}`;
        row.textContent = `${label}: ${ratio}:1 \u2014 `;
        row.appendChild(aaSpan);
        row.appendChild(document.createTextNode(' '));
        row.appendChild(aaaSpan);
        return row;
      }

      meta.appendChild(mk('Contrast vs white', ratioWhite));
      meta.appendChild(mk('Contrast vs neutral-900', ratioDark));
    });
  }

  function setupThemeToggle() {
    const btn = document.getElementById('demo-theme-toggle');
    const box = document.getElementById('demo-playground');
    if (!btn || !box) return;
    btn.addEventListener('click', () => {
      if (box.classList.contains('light')) {
        box.classList.remove('light');
        box.classList.add('dark');
        btn.textContent = 'Toggle Theme (Dark)';
      } else {
        box.classList.remove('dark');
        box.classList.add('light');
        btn.textContent = 'Toggle Theme (Light)';
      }
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    annotateSwatches();
    setupThemeToggle();
    try { buildRecommendations(); } catch (e) { /* noop */ }
  });
})();

// Build a foreground recommendation table based on contrast calculations
function buildRecommendations() {
  const mount = document.getElementById('recommendations-table');
  if (!mount) return;
  const url = DOCUMENTATION_OPTIONS.URL_ROOT + '_static/branding/zyra-colors.json';
  fetch(url)
    .then((r) => r.json())
    .then((tokens) => {
      const order = [
        ['Navy', 'navy'],
        ['Ocean Blue', 'blue'],
        ['Cable Blue', 'cable_blue'],
        ['Seafoam', 'sky'],
        ['Deep Teal', 'teal'],
        ['Mist', 'teal_accent'],
        ['Leaf Green', 'green'],
        ['Olive', 'olive'],
        ['Soil', 'soil'],
        ['Amber', 'amber'],
        ['Red', 'red'],
        ['Neutral 900', 'neutral_900'],
        ['Neutral 700', 'neutral_700'],
        ['Neutral 600', 'neutral_600'],
        ['Neutral 400', 'neutral_400'],
        ['Neutral 200', 'neutral_200'],
        ['Neutral 50', 'neutral_50'],
      ];
      const table = document.createElement('table');
      table.className = 'rec-table';
      const header = document.createElement('tr');
      ['Color', 'Hex', 'Contrast vs white', 'Contrast vs neutral-900', 'Recommended text'].forEach((h) => {
        const th = document.createElement('th');
        th.textContent = h;
        header.appendChild(th);
      });
      table.appendChild(header);
      order.forEach(([label, key]) => {
        if (!tokens[key]) return;
        const hex = tokens[key];
        const rW = contrastRatio(hex, '#FFFFFF');
        const rD = contrastRatio(hex, '#232323');
        // Decide recommendation: prefer AA; if both AA, choose higher contrast
        function tag(ratio) {
          if (ratio >= 7) return 'AAA';
          if (ratio >= 4.5) return 'AA';
          if (ratio >= 3) return 'AA (large)';
          return 'low';
        }
        const whiteTag = tag(rW);
        const darkTag = tag(rD);
        let rec = '';
        if ((rW >= 4.5 || rD >= 4.5)) {
          if (rW >= rD) rec = `white (${whiteTag})`;
          else rec = `neutral-900 (${darkTag})`;
        } else if (rW >= 3 || rD >= 3) {
          if (rW >= rD) rec = `white (${whiteTag})`;
          else rec = `neutral-900 (${darkTag})`;
        } else {
          rec = 'avoid small text';
        }
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><span class="chip" style="display:inline-block;width:1em;height:1em;vertical-align:middle;background:${hex};border:1px solid #ddd;margin-right:6px;"></span>${label}</td>
          <td><code>${hex}</code></td>
          <td>${rW}:1</td>
          <td>${rD}:1</td>
          <td>${rec}</td>
        `;
        table.appendChild(tr);
      });
      mount.appendChild(table);
    })
    .catch(() => {});
}
