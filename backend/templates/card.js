const THEMES = {
  default: { card_bg: 'rgba(255,255,255,0.12)', text: '#ffffff', heading_color: '#ffffff', accent: '#ffd700', fallback_bg: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' },
  pink:    { card_bg: 'rgba(255,255,255,0.15)', text: '#ffffff', heading_color: '#fff0f5', accent: '#ffe4e1', fallback_bg: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)' },
  green:   { card_bg: 'rgba(0,0,0,0.08)',       text: '#1a3a2a', heading_color: '#0d2b1e', accent: '#ffffff', fallback_bg: 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)' },
  dark:    { card_bg: 'rgba(255,255,255,0.06)', text: '#e0e0e0', heading_color: '#ffffff', accent: '#00d4ff', fallback_bg: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)' },
  warm:    { card_bg: 'rgba(255,255,255,0.2)',  text: '#3d2000', heading_color: '#1a0d00', accent: '#ffffff', fallback_bg: 'linear-gradient(135deg, #f7971e 0%, #ffd200 100%)' },
};

const FONT = 'PingFang SC, Hiragino Sans GB, Microsoft YaHei, sans-serif';

export function generateCardHTML(card, style = 'default', title = '', bg_image = null) {
  const theme = THEMES[style] || THEMES.default;
  const isCover = card.index === 0;

  // 背景：图片优先，否则用渐变
  const bodyBg = bg_image
    ? `background: url('${bg_image}') center/cover no-repeat; background-color: #333;`
    : `background: ${theme.fallback_bg};`;

  // 有背景图时加深遮罩，保证文字可读
  const overlay = bg_image
    ? `<div style="position:absolute;inset:0;background:rgba(0,0,0,0.35);border-radius:inherit;"></div>`
    : '';

  // 有背景图时文字强制白色
  const textColor = bg_image ? '#ffffff' : theme.text;
  const headingColor = bg_image ? '#ffffff' : theme.heading_color;

  return `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    width: 1080px; height: 1080px;
    font-family: ${FONT};
    display: flex; align-items: center; justify-content: center;
    overflow: hidden;
    ${bodyBg}
  }
  .card {
    width: 960px; height: 960px;
    background: ${bg_image ? 'transparent' : theme.card_bg};
    border-radius: 32px;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 64px;
    backdrop-filter: ${bg_image ? 'none' : 'blur(10px)'};
    border: 1px solid rgba(255,255,255,0.2);
    position: relative;
  }
  .content { position: relative; z-index: 1; display: flex; flex-direction: column; align-items: center; width: 100%; }
  .index { position: absolute; top: 36px; right: 44px; z-index: 2; font-size: 28px; color: ${theme.accent}; font-weight: 700; opacity: 0.9; }
  .emoji { font-size: 96px; margin-bottom: 32px; line-height: 1; }
  .heading {
    font-size: 56px; font-weight: 800;
    color: ${headingColor};
    text-align: center; line-height: 1.3; margin-bottom: 32px;
    text-shadow: 0 2px 12px rgba(0,0,0,0.4);
  }
  .body {
    font-size: 36px; color: ${textColor};
    text-align: center; line-height: 1.7;
    opacity: 0.95; max-width: 780px;
    text-shadow: 0 1px 6px rgba(0,0,0,0.3);
  }
  .cover-title {
    font-size: 72px; font-weight: 900;
    color: ${headingColor};
    text-align: center; line-height: 1.25; margin-bottom: 24px;
    text-shadow: 0 4px 20px rgba(0,0,0,0.5);
  }
  .cover-sub { font-size: 36px; color: ${textColor}; opacity: 0.85; text-align: center; text-shadow: 0 2px 8px rgba(0,0,0,0.3); }
  .watermark { position: absolute; bottom: 32px; z-index: 2; font-size: 24px; color: rgba(255,255,255,0.5); letter-spacing: 2px; }
</style>
</head>
<body>
<div class="card">
  ${overlay}
  ${!isCover ? `<div class="index">${card.index}</div>` : ''}
  <div class="content">
    ${isCover ? `
      <div class="emoji">${card.emoji || '✨'}</div>
      <div class="cover-title">${card.heading}</div>
      <div class="cover-sub">${card.body || ''}</div>
    ` : `
      <div class="emoji">${card.emoji || '💡'}</div>
      <div class="heading">${card.heading}</div>
      <div class="body">${card.body}</div>
    `}
  </div>
  <div class="watermark">pengip.com</div>
</div>
</body>
</html>`;
}
