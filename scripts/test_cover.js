const { chromium } = require('@playwright/test');
const fs = require('fs');

async function testCover() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  const shortName = 'IT通信设备';
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
  await page.waitForTimeout(500);
  
  // Full cover
  await page.screenshot({ path: '/tmp/cover_full.png', fullPage: true });
  console.log('Full cover saved to /tmp/cover_full.png (1800x766)');
  
  // Crop center 766x766 to simulate mobile moments share
  await page.setViewportSize({ width: 766, height: 766 });
  const clip = { x: (1800-766)/2, y: 0, width: 766, height: 766 };
  await page.screenshot({ path: '/tmp/cover_mobile.png', clip });
  console.log('Mobile crop saved to /tmp/cover_mobile.png (766x766)');
  
  await browser.close();
}

testCover().catch(console.error);
