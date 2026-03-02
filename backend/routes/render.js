import puppeteer from 'puppeteer';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { generateCardHTML } from '../templates/card.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUTPUT_DIR = path.join(__dirname, '../outputs');
const UPLOADS_DIR = path.join(__dirname, '../uploads');

// 把前端传来的相对URL转成 Puppeteer 可访问的路径
function resolveBgImage(bg_image) {
  if (!bg_image) return null;
  // 已经是 http(s) URL（AI生成的外链）直接用
  if (bg_image.startsWith('http')) return bg_image;
  // /xhs/uploads/xxx → file:// 绝对路径，验证安全性
  if (bg_image.startsWith('/xhs/uploads/')) {
    const filename = bg_image.replace('/xhs/uploads/', '');
    // 防止路径遍历：检查是否包含 .. 或绝对路径
    if (filename.includes('..') || filename.startsWith('/')) {
      throw new Error('非法的文件路径');
    }
    const filepath = path.join(UPLOADS_DIR, filename);
    const realpath = path.resolve(filepath);
    const uploadsReal = path.resolve(UPLOADS_DIR);
    if (!realpath.startsWith(uploadsReal)) {
      throw new Error('非法的文件路径');
    }
    return `file://${realpath}`;
  }
  // CSS渐变字符串（预设背景）直接透传
  return bg_image;
}

export async function renderCards(req, res) {
  const { cards, title, style = 'default', bg_image = null } = req.body;
  if (!cards || !cards.length) return res.status(400).json({ error: '缺少卡片数据' });

  let resolvedBg;
  try {
    resolvedBg = resolveBgImage(bg_image);
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }

  let browser;
  const maxRetries = 3;
  let lastError;

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      browser = await puppeteer.launch({
        headless: true,
        executablePath: '/usr/bin/chromium-browser',
        args: [
          '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
          '--disable-gpu', '--disable-software-rasterizer', '--no-first-run',
          '--no-zygote', '--disable-extensions', '--hide-scrollbars', '--mute-audio',
        ],
        timeout: 60000,
      });

      const page = await browser.newPage();
      await page.setViewport({ width: 1080, height: 1080 });

      const sessionId = Date.now();
      const urls = [];

      for (const card of cards) {
        const html = generateCardHTML(card, style, title, resolvedBg);
        await page.setContent(html, { waitUntil: 'networkidle0' });

        const filename = `card_${sessionId}_${card.index}.png`;
        const filepath = path.join(OUTPUT_DIR, filename);
        await page.screenshot({ path: filepath, type: 'png' });
        urls.push(`/xhs/outputs/${filename}`);
      }

      res.json({ success: true, urls, session_id: sessionId });
      return;
    } catch (err) {
      lastError = err;
      console.error(`Render attempt ${attempt + 1} failed:`, err.message);
      if (attempt < maxRetries - 1) {
        await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
      }
    } finally {
      if (browser) await browser.close();
    }
  }

  console.error('Render failed after retries:', lastError);
  res.status(500).json({ error: lastError?.message || '截图失败' });
}
