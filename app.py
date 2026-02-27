"""
医生小红书图文笔记生成器
输入主题 → AI生成科普内容 → 渲染专业海报 → 导出PNG
"""
import os, json, uuid, requests, base64, shutil
from datetime import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="医生小红书图文生成器")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

AI_BASE = "https://yunwu.ai"
AI_KEY = "sk-GOthcTYIVEdXznmrcdxs2CDV51lb9qalw5vMbSBxeFaQFG4f"
AI_MODEL = "gemini-2.5-pro"
OUTPUT_DIR = "/root/projects/xhs-generator/output"
UPLOAD_DIR = "/root/projects/xhs-generator/uploads"
STATIC_DIR = "/root/projects/xhs-generator/static"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

tasks = {}

CONTENT_PROMPT = """你是一位医美/医疗领域的小红书内容专家，擅长把专业医学知识写成通俗易懂、有干货的科普笔记。

现在要为一位医生生成小红书图文笔记内容。

【医生信息】
- 姓名：{doctor_name}
- 医院：{hospital}
- 科室：{department}

【笔记主题】
{topic}

【额外要求】
{extra}

请生成一篇小红书图文笔记的内容，输出JSON格式：

{{
  "title": "笔记大标题（10-20字，有吸引力，可以用数字开头，比如'双眼皮术后护理17条'）",
  "sections": [
    {{
      "heading": "小标题（4-8字）",
      "icon": "一个相关的emoji",
      "points": [
        "要点1（一句话，简洁有力）",
        "要点2",
        "要点3"
      ]
    }}
  ],
  "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"]
}}

要求：
- sections控制在3-5个，每个2-4个要点
- 语言通俗但专业，像医生在跟患者聊天
- 要点简洁，每条不超过30字
- 标签5个左右，跟主题和科室相关
- 不要用"赋能""助力"这种词
- 只返回JSON"""

def ai_call(prompt, max_tokens=3000):
    resp = requests.post(
        f"{AI_BASE}/v1/chat/completions",
        headers={"Authorization": f"Bearer {AI_KEY}", "Content-Type": "application/json"},
        json={"model": AI_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": 0.7},
        timeout=120,
    )
    if resp.status_code != 200:
        raise Exception(f"AI error: {resp.status_code} {resp.text[:200]}")
    return resp.json()["choices"][0]["message"]["content"]

def generate_poster_html(task_id, content, doctor_info):
    """生成海报HTML页面"""
    title = content.get("title", "")
    sections = content.get("sections", [])
    tags = content.get("tags", [])
    d = doctor_info

    sections_html = ""
    for s in sections:
        points_html = "".join(f'<div class="point">{p}</div>' for p in s.get("points", []))
        sections_html += f'''
        <div class="section">
            <div class="section-head"><span class="sec-icon">{s.get("icon","📌")}</span><span class="sec-title">{s.get("heading","")}</span></div>
            {points_html}
        </div>'''

    tags_html = " ".join(f'<span class="tag">#{t}</span>' for t in tags)
    photo_html = ""
    if d.get("photo_url"):
        photo_html = f'<img class="doc-photo" src="{d["photo_url"]}" alt="{d.get("name","")}">'

    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"PingFang SC","Microsoft YaHei",sans-serif;background:#f5f0eb;margin:0;padding:20px;display:flex;justify-content:center}}
.poster{{width:750px;min-height:1000px;background:#faf7f2;border-radius:12px;padding:48px 44px;position:relative;overflow:hidden}}
.poster::before{{content:"";position:absolute;top:0;right:0;width:200px;height:200px;background:radial-gradient(circle,rgba(200,180,160,0.1) 0%,transparent 70%);border-radius:50%}}
h1{{font-size:32px;font-weight:900;color:#2c2c2c;line-height:1.4;margin-bottom:24px;padding-bottom:16px;border-bottom:2px dashed #d4c5b5}}
.section{{margin-bottom:22px}}
.section-head{{display:flex;align-items:center;gap:8px;margin-bottom:10px}}
.sec-icon{{font-size:22px}}
.sec-title{{font-size:20px;font-weight:700;color:#3a3a3a}}
.point{{font-size:15px;color:#555;line-height:1.8;padding:2px 0 2px 12px;border-left:2px solid transparent}}
.point:hover{{border-left-color:#c4a882}}
.doc-area{{display:flex;align-items:center;gap:16px;margin:28px 0 18px;padding:18px;background:#fff;border-radius:10px;border:1px solid #e8e0d6}}
.doc-photo{{width:80px;height:80px;border-radius:50%;object-fit:cover;border:2px solid #d4c5b5}}
.doc-info{{flex:1}}
.doc-name{{font-size:18px;font-weight:700;color:#2c2c2c}}
.doc-dept{{font-size:13px;color:#888;margin-top:4px}}
.tags-area{{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}}
.tag{{font-size:12px;color:#b08d6a;background:#f0e8de;padding:4px 12px;border-radius:14px}}
.xhs-id{{font-size:12px;color:#aaa;margin-top:12px;text-align:right}}
</style></head><body>
<div class="poster" id="poster">
<h1>{title}</h1>
{sections_html}
<div class="doc-area">
{photo_html}
<div class="doc-info">
<div class="doc-name">{d.get("name","")}</div>
<div class="doc-dept">{d.get("hospital","")} {d.get("department","")}</div>
</div>
</div>
<div class="tags-area">{tags_html}</div>
<div class="xhs-id">小红书号: {d.get("xhs_id","")}</div>
</div>
</body></html>'''

# ========== API ==========

@app.post("/api/upload-photo")
async def upload_photo(file: UploadFile = File(...)):
    """上传医生照片"""
    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    fname = f"{uuid.uuid4().hex[:8]}.{ext}"
    fpath = os.path.join(UPLOAD_DIR, fname)
    with open(fpath, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"url": f"/uploads/{fname}", "filename": fname}

@app.post("/api/generate")
async def generate(bg: BackgroundTasks,
    topic: str = Form(...),
    doctor_name: str = Form(""),
    hospital: str = Form(""),
    department: str = Form(""),
    xhs_id: str = Form(""),
    photo_url: str = Form(""),
    extra: str = Form("")):
    task_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]
    doctor_info = {
        "name": doctor_name, "hospital": hospital,
        "department": department, "xhs_id": xhs_id,
        "photo_url": photo_url,
    }
    tasks[task_id] = {"status": "pending", "task_id": task_id}
    bg.add_task(do_generate, task_id, topic, extra, doctor_info)
    return {"task_id": task_id}

def do_generate(task_id, topic, extra, doctor_info):
    try:
        tasks[task_id]["status"] = "generating"
        prompt = CONTENT_PROMPT.format(
            doctor_name=doctor_info.get("name", ""),
            hospital=doctor_info.get("hospital", ""),
            department=doctor_info.get("department", ""),
            topic=topic,
            extra=extra,
        )
        raw = ai_call(prompt)
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        content = json.loads(raw)

        html = generate_poster_html(task_id, content, doctor_info)
        fpath = os.path.join(OUTPUT_DIR, f"{task_id}.html")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(html)

        tasks[task_id]["status"] = "done"
        tasks[task_id]["content"] = content
        tasks[task_id]["poster_url"] = f"/output/{task_id}.html"
    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["error"] = str(e)

@app.get("/api/task/{task_id}")
def get_task(task_id: str):
    if task_id not in tasks:
        raise HTTPException(404, "Task not found")
    return tasks[task_id]

# 静态文件
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
