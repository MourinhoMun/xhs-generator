const YUNWU_API_KEY = process.env.YUNWU_API_KEY;
const YUNWU_BASE_URL = process.env.YUNWU_BASE_URL || 'https://yunwu.ai';

const SYSTEM_PROMPT = `你是一个专业的小红书内容创作者，擅长创作爆款图文内容。

生成规则：
- 标题：吸引眼球，带emoji，15字以内
- 正文：分3-6张卡片，每张卡片有标题+内容
- 风格：活泼、真实、有干货，符合小红书调性
- 每张卡片内容简洁，不超过80字
- 多用emoji增加视觉感

返回严格的JSON格式，不要有任何其他文字：
{
  "title": "笔记标题",
  "cover_text": "封面大字（10字以内）",
  "cards": [
    {
      "index": 1,
      "heading": "卡片标题",
      "body": "卡片正文内容",
      "emoji": "🌟"
    }
  ],
  "tags": ["标签1", "标签2", "标签3"],
  "caption": "发布时的文字描述（含话题标签）"
}`;

export async function generateCopy(req, res) {
  const { topic, style = 'default', card_count = 5, authorization = '' } = req.body;
  
  // Token 验证
  const token = authorization.replace('Bearer ', '').trim();
  if (!token) return res.status(401).json({ error: '授权失效，请重新激活' });
  
  if (!topic) return res.status(400).json({ error: '请输入主题' });

  try {
    const response = await fetch(`${YUNWU_BASE_URL}/v1/chat/completions`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${YUNWU_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 2000,
        messages: [
          { role: 'system', content: SYSTEM_PROMPT },
          { role: 'user', content: `请为以下主题创作小红书图文内容，生成${card_count}张卡片，风格：${style}。\n\n主题：${topic}` }
        ]
      })
    });

    const json = await response.json();
    if (!response.ok) throw new Error(json.error?.message || '调用失败');

    const text = json.choices[0].message.content;
    const match = text.match(/\{[\s\S]*\}/);
    if (!match) throw new Error('AI返回格式错误');

    let data;
    try {
      data = JSON.parse(match[0]);
    } catch (e) {
      throw new Error('JSON 解析失败: ' + e.message);
    }
    
    res.json({ success: true, data });
  } catch (err) {
    console.error('Generate error:', err.message);
    res.status(500).json({ error: err.message || '生成失败' });
  }
}
