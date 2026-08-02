const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const TABLE_THEME = {
  bg: '#1a1a2e', text: '#e0e0e0', headerBg: '#16213e',
  headerText: '#e2b714', border: '#2a2a4a', altRow: '#1e1e3a'
};

async function renderTableToBase64(page, tableHtml) {
  const fullHtml = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:${TABLE_THEME.bg};padding:20px;display:inline-block;font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",sans-serif}
table{border-collapse:collapse;font-size:13px;color:${TABLE_THEME.text};line-height:1.5}
th{background:${TABLE_THEME.headerBg};color:${TABLE_THEME.headerText};padding:8px 12px;text-align:center;font-weight:700;border:1px solid ${TABLE_THEME.border};white-space:nowrap}
td{padding:6px 12px;border:1px solid ${TABLE_THEME.border};text-align:center}
td:first-child{text-align:left;font-weight:600;white-space:nowrap}
tr:nth-child(even) td{background:${TABLE_THEME.altRow}}
tr:hover td{background:#252550}
</style></head><body>${tableHtml}</body></html>`;
  await page.setContent(fullHtml, { waitUntil: 'networkidle' });
  await page.waitForTimeout(200);
  return await page.locator('table').screenshot();
}

function extractTables(markdown) {
  const lines = markdown.split('\n');
  const tables = []; let i = 0;
  while (i < lines.length) {
    if (lines[i].trim().startsWith('|')) {
      const start = i;
      while (i < lines.length && lines[i].trim().startsWith('|')) i++;
      tables.push({ start, end: i, text: lines.slice(start, i).join('\n') });
    } else i++;
  }
  return tables;
}

function mdToHtmlTable(mdTable) {
  const rows = mdTable.split('\n').filter(l => l.trim().startsWith('|'));
  const headers = rows[0].split('|').filter(c => c.trim()).map(c => c.trim().replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>'));
  const alignments = rows[1] ? rows[1].split('|').filter(c => c.trim()).map(c => {
    if (c.startsWith(':') && c.endsWith(':')) return 'center';
    if (c.endsWith(':')) return 'right'; return 'left';
  }) : [];
  let html = '<table><thead><tr>';
  headers.forEach((h, i) => { html += `<th style="text-align:${alignments[i]||'left'}">${h}</th>`; });
  html += '</tr></thead><tbody>';
  for (let r = 2; r < rows.length; r++) {
    const cells = rows[r].split('|').filter(c => c.trim()).map(c => c.trim());
    if (cells.length === 0) continue;
    html += '<tr>';
    cells.forEach((c, i) => {
      const styled = c.replace(/\*\*(.+?)\*\*/g, '<strong style="color:#e2b714">$1</strong>');
      html += `<td style="text-align:${alignments[i]||'left'}">${styled}</td>`;
    });
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}

async function generateCoverImage(page, baseName) {
  const industry = baseName.replace(/行业_俯瞰分析|_俯瞰分析/g, '').replace('.md', '');
  const shortName = industry.replace(/行业/g, '').replace(/全景/g,'').trim().replace(/[：:].*/,'').trim();
  const fullHtml = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
body{width:1800px;height:766px;background:linear-gradient(150deg,#08081a 0%,#12122a 30%,#0c1a3a 60%,#1a1a2e 100%);display:flex;flex-direction:column;justify-content:center;align-items:center;padding:60px 517px;font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",sans-serif;text-align:center;position:relative;overflow:hidden}
.glow1{position:absolute;width:500px;height:500px;border-radius:50%;background:radial-gradient(circle,rgba(226,183,20,0.06) 0%,transparent 70%);top:-150px;right:-100px}
.glow2{position:absolute;width:350px;height:350px;border-radius:50%;background:radial-gradient(circle,rgba(74,144,226,0.05) 0%,transparent 70%);bottom:-80px;left:-80px}
.grid{position:absolute;inset:0;opacity:0.03;background-image:linear-gradient(rgba(255,255,255,0.1) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,0.1) 1px,transparent 1px);background-size:60px 60px}
.content{position:relative;z-index:1;width:100%;display:flex;flex-direction:column;align-items:center}
.badge{font-size:13px;font-weight:600;color:#e2b714;border:1px solid rgba(226,183,20,0.5);padding:6px 22px;letter-spacing:4px;margin-bottom:28px}
.ctitle{font-size:44px;font-weight:800;color:#fff;line-height:1.35;letter-spacing:5px;margin-bottom:0}
.line{width:70px;height:3px;background:#e2b714;margin:22px auto;border-radius:2px}
.sub{font-size:15px;font-weight:300;color:#8899aa;letter-spacing:3px}
.corp{position:absolute;bottom:28px;font-size:11px;color:rgba(255,255,255,0.15);letter-spacing:2px}
</style></head><body><div class="grid"></div><div class="glow1"></div><div class="glow2"></div><div class="content">
<div class="badge">行业全景 · 俯瞰分析</div>
<div class="ctitle">${shortName}</div>
<div class="line"></div>
<div class="sub">AI蒸馏专家框架 · 2025年报</div>
<div class="corp">浩哥AI量化财报</div>
</div></body></html>`;
  await page.setContent(fullHtml, { waitUntil: 'networkidle' });
  await page.waitForTimeout(300);
  return await page.screenshot({ fullPage: true });
}

async function processFile(browser, page, inputPath, outputDir) {
  const baseName = path.basename(inputPath);
  const content = fs.readFileSync(inputPath, 'utf-8');
  const lines = content.split('\n');
  const tables = extractTables(content);
  console.log(`\n[${baseName.replace('.md','')}] Tables: ${tables.length}`);
  const coverBuf = await generateCoverImage(page, baseName);
  const coverB64 = `data:image/png;base64,${coverBuf.toString('base64')}`;
  let result = `![cover](${coverB64})\n\n`;
  let lastLine = 0;
  for (let t = 0; t < tables.length; t++) {
    for (let i = lastLine; i < tables[t].start; i++) result += lines[i] + '\n';
    const htmlTable = mdToHtmlTable(tables[t].text);
    const buf = await renderTableToBase64(page, htmlTable);
    if (buf) result += `\n\n![table-${t+1}](data:image/png;base64,${buf.toString('base64')})\n\n\n`;
    lastLine = tables[t].end;
  }
  for (let i = lastLine; i < lines.length; i++) result += lines[i] + '\n';
  fs.writeFileSync(path.join(outputDir, baseName), result, 'utf-8');
  console.log(`  OK`);
}

async function main() {
  const inputDir = process.argv[2];
  const outputDir = process.argv[3];
  if (!inputDir || !outputDir) { console.error('Usage: node process_wechat.js <input_dir> <output_dir>'); process.exit(1); }
  fs.mkdirSync(outputDir, { recursive: true });
  const files = fs.readdirSync(inputDir).filter(f => f.endsWith('.md'));
  console.log(`Processing ${files.length} files...`);
  const browser = await chromium.launch();
  const page = await browser.newPage();
  let ok = 0, fail = 0;
  for (const f of files) {
    try {
      await processFile(browser, page, path.join(inputDir, f), outputDir);
      ok++;
    } catch(e) {
      console.error(`  ERROR: ${e.message}`);
      fail++;
    }
  }
  await browser.close();
  console.log(`\nDone! ${ok} OK, ${fail} failed`);
}

main().catch(e => { console.error(e); process.exit(1); });
