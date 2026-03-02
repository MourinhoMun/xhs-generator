const YUNWU_API_KEY = process.env.YUNWU_API_KEY;
const YUNWU_BASE_URL = process.env.YUNWU_BASE_URL || 'https://yunwu.ai';

// 根据主题生成 Flux prompt
function buildBgPrompt(topic, bgStyle) {
  const styleMap = {
    abstract: 'abstract fluid art, colorful flowing shapes, smooth gradients',
    nature: 'beautiful nature scenery, soft bokeh, peaceful atmosphere',
    tech: 'futuristic technology background, circuit patterns, neon glow, dark theme',
    minimal: 'minimal clean background, soft pastel colors, simple geometric shapes',
    texture: 'elegant paper texture, subtle grain, warm tones',
    city: 'modern city skyline, golden hour, cinematic',
  };
  const styleDesc = styleMap[bgStyle] || styleMap.abstract;
  return `${styleDesc}, related to "${topic}", no text, no people, high quality, 1:1 square format, suitable as social media card background`;
}

export async function generateBackground(req, res) {
  const { topic, bg_style = 'abstract' } = req.body;
  if (!topic) return res.status(400).json({ error: '请输入主题' });

  try {
    const response = await fetch(`${YUNWU_BASE_URL}/v1/images/generations`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${YUNWU_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: 'gemini-3.1-flash-image-preview',
        prompt: buildBgPrompt(topic, bg_style),
        n: 1,
        size: '1024x1024',
      })
    });

    const json = await response.json();
    if (!response.ok) throw new Error(json.error?.message || '生成失败');

    const imageUrl = json.data?.[0]?.url;
    if (!imageUrl) throw new Error('未返回图片URL');

    res.json({ success: true, url: imageUrl });
  } catch (err) {
    console.error('BG gen error:', err.message);
    res.status(500).json({ error: err.message });
  }
}
