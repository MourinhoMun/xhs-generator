"""
医生小红书图文笔记生成器 v3
支持：多张系列笔记、8种版式、底图上传、6种插图风格
"""
import os, uuid, requests, base64, shutil, json, concurrent.futures, threading
from datetime import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from layouts import LAYOUTS, LAYOUT_LIST, ILLUSTRATION_STYLES, ILLUSTRATION_STYLE_LIST

app = FastAPI(title="医生小红书图文生成器")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

AI_BASE = "https://yunwu.ai"
AI_KEY = "sk-GOthcTYIVEdXznmrcdxs2CDV51lb9qalw5vMbSBxeFaQFG4f"
TEXT_MODEL = "gemini-2.0-flash"
IMAGE_MODEL = "gemini-3.1-flash-image-preview"

OUTPUT_DIR = "/root/projects/xhs-generator/output"
UPLOAD_DIR = "/root/projects/xhs-generator/uploads"
STATIC_DIR = "/root/projects/xhs-generator/static"
DEFAULT_SAMPLE = "/root/projects/xhs-generator/static/sample_poster.jpg"

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

tasks = {}
tasks_lock = threading.Lock()

def update_task(task_id, updates):
    """线程安全地更新任务状态"""
    with tasks_lock:
        if task_id in tasks:
            tasks[task_id].update(updates)

ALLOWED_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif"}

def validate_image_ext(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_IMAGE_EXTS:
        raise HTTPException(400, f"不支持的文件类型: {ext}，请上传 jpg/png/webp")
    return ext

PRESET_TOPICS = [
    "双眼皮术后护理注意事项", "隆鼻手术前后须知", "面部轮廓整形恢复指南",
    "抗衰老治疗方案选择", "吸脂手术常见问题解答", "植发手术全流程解析",
    "医美项目如何避坑", "术后饮食与生活注意事项",
]

POINTS_PER_PAGE = {1: (3,5), 2: (3,4), 3: (3,4), 4: (3,4), 5: (3,4)}

POINTS_PROMPT = """你是医疗科普内容专家。请为以下主题生成小红书系列笔记的要点内容。

主题：{topic}
科室：{department}
总共需要：{total_pages}张图，每张{points_min}-{points_max}个要点
用户自定义要点（若有请润色扩充，若无则自由发挥）：{user_points}

输出JSON格式：
{{
  "series_title": "系列总标题（10-20字）",
  "pages": [
    {{
      "page_num": 1,
      "chapter_title": "第一章标题（6-12字，概括本页主题）",
      "points": [
        {{
          "heading": "小标题（4-8字）",
          "body": "1-2句通俗说明，不超过40字",
          "illustration_hint": "适合配什么插图（一句话）"
        }}
      ]
    }}
  ]
}}

要求：各章节内容连贯但各自完整；语言通俗；禁止营销词；只返回JSON"""

# ── 工具函数 ──────────────────────────────────────────

def load_image_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def get_mime(path):
    ext = path.rsplit(".", 1)[-1].lower()
    return {"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png","webp":"image/webp"}.get(ext,"image/jpeg")

def text_call(prompt):
    resp = requests.post(
        f"{AI_BASE}/v1/chat/completions",
        headers={"Authorization": f"Bearer {AI_KEY}", "Content-Type": "application/json"},
        json={"model": TEXT_MODEL, "messages": [{"role":"user","content":prompt}], "max_tokens":3000, "temperature":0.7},
        timeout=120,
    )
    if resp.status_code != 200:
        raise Exception(f"Text AI error: {resp.status_code} {resp.text[:200]}")
    return resp.json()["choices"][0]["message"]["content"]

def image_call(parts_list):
    resp = requests.post(
        f"{AI_BASE}/v1beta/models/{IMAGE_MODEL}:generateContent",
        headers={"Content-Type": "application/json", "x-goog-api-key": AI_KEY},
        json={"contents":[{"parts":parts_list}],"generationConfig":{"responseModalities":["IMAGE"]}},
        timeout=180,
    )
    if resp.status_code != 200:
        raise Exception(f"Image AI error: {resp.status_code} {resp.text[:300]}")
    for p in resp.json()["candidates"][0]["content"]["parts"]:
        if "inlineData" in p:
            return p["inlineData"]["data"], p["inlineData"]["mimeType"]
    raise Exception("Gemini 未返回图片")

def gen_all_points(topic, department, total_pages, user_points):
    pmin, pmax = POINTS_PER_PAGE.get(total_pages, (3,4))
    raw = text_call(POINTS_PROMPT.format(
        topic=topic, department=department,
        total_pages=total_pages, points_min=pmin, points_max=pmax,
        user_points=user_points or "无"
    ))
    if "```json" in raw: raw = raw.split("```json")[1].split("```")[0]
    elif "```" in raw: raw = raw.split("```")[1].split("```")[0]
    return json.loads(raw.strip())

def gen_illustration(hint, style_id):
    style = ILLUSTRATION_STYLES.get(style_id, ILLUSTRATION_STYLES["flat"])
    prompt = f"为医疗科普小红书笔记生成一张配图。内容：{hint}。风格：{style['prompt_suffix']}。正方形构图。"
    return image_call([{"text": prompt}])

def gen_one_poster(page_data, doctor_info, sample_path, photo_path, layout_id, illustrations):
    layout = LAYOUTS.get(layout_id, LAYOUTS["A"])
    points_lines = "\n".join(
        f"{i+1}. 【{p['heading']}】{p['body']}"
        for i, p in enumerate(page_data.get("points", []))
    )
    chapter = page_data.get("chapter_title", "")
    points_section = f"本章主题：{chapter}\n{points_lines}"

    prompt = layout["prompt"].format(
        doctor_name=doctor_info.get("name",""),
        hospital=doctor_info.get("hospital",""),
        department=doctor_info.get("department",""),
        points_section=points_section,
    )

    parts = [
        {"inlineData": {"mimeType": get_mime(sample_path), "data": load_image_b64(sample_path)}},
        {"text": prompt},
    ]
    if photo_path and os.path.exists(photo_path):
        parts.append({"inlineData": {"mimeType": get_mime(photo_path), "data": load_image_b64(photo_path)}})
    for ill_b64, ill_mime in illustrations:
        parts.append({"inlineData": {"mimeType": ill_mime, "data": ill_b64}})

    return image_call(parts)

# ── API ──────────────────────────────────────────

@app.get("/api/config")
def get_config():
    return {"topics": PRESET_TOPICS, "layouts": LAYOUT_LIST, "illustration_styles": ILLUSTRATION_STYLE_LIST}

@app.post("/api/upload-photo")
async def upload_photo(file: UploadFile = File(...)):
    ext = validate_image_ext(file.filename)
    fname = f"photo_{uuid.uuid4().hex[:8]}.{ext}"
    fpath = os.path.join(UPLOAD_DIR, fname)
    with open(fpath, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"url": f"/uploads/{fname}", "local_path": fpath}

@app.post("/api/upload-sample")
async def upload_sample(file: UploadFile = File(...)):
    ext = validate_image_ext(file.filename)
    fname = f"sample_{uuid.uuid4().hex[:8]}.{ext}"
    fpath = os.path.join(UPLOAD_DIR, fname)
    with open(fpath, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"url": f"/uploads/{fname}", "local_path": fpath}

@app.post("/api/generate")
async def generate(bg: BackgroundTasks,
    topic: str = Form(...),
    doctor_name: str = Form(""),
    hospital: str = Form(""),
    department: str = Form(""),
    photo_local_path: str = Form(""),
    sample_local_path: str = Form(""),
    user_points: str = Form(""),
    total_pages: int = Form(1),
    layout_id: str = Form("A"),
    illustration_style: str = Form("flat")):

    task_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]
    doctor_info = {"name": doctor_name, "hospital": hospital, "department": department}
    # Bug fix: strip 空格防止路径判断失败
    sample_local_path = (sample_local_path or "").strip()
    sample_path = sample_local_path if sample_local_path and os.path.exists(sample_local_path) else DEFAULT_SAMPLE
    with tasks_lock:
        tasks[task_id] = {"status": "pending", "task_id": task_id, "total_pages": total_pages, "results": []}
    bg.add_task(do_generate, task_id, topic, user_points, doctor_info,
                (photo_local_path or "").strip(), sample_path, total_pages, layout_id, illustration_style)
    return {"task_id": task_id}

def do_generate(task_id, topic, user_points, doctor_info, photo_path, sample_path, total_pages, layout_id, illus_style):
    try:
        # Step 1: 生成所有页的要点
        update_task(task_id, {"status": "generating_points"})
        series_data = gen_all_points(topic, doctor_info.get("department",""), total_pages, user_points)
        pages = series_data.get("pages", [])[:total_pages]
        # Bug fix: AI返回页数不足时补齐（复制最后一页）
        while len(pages) < total_pages and pages:
            pages.append(pages[-1])
        update_task(task_id, {"series_title": series_data.get("series_title","")})

        # Step 2: 逐页生成插图（Bug fix: 避免嵌套ThreadPoolExecutor死锁，改为顺序生成插图）
        update_task(task_id, {"status": "generating_illustrations"})
        page_illustrations = []
        for page in pages:
            hints = [p.get("illustration_hint", p["heading"]) for p in page.get("points", [])[:2]]
            ills = []
            for hint in hints:
                try:
                    ills.append(gen_illustration(hint, illus_style))
                except Exception as e:
                    print(f"插图生成失败: {e}")
            page_illustrations.append(ills)

        # Step 3: 逐页生成海报
        results = []
        for i, (page, ills) in enumerate(zip(pages, page_illustrations)):
            update_task(task_id, {"status": f"generating_poster_{i+1}_of_{total_pages}"})
            img_b64, mime = gen_one_poster(page, doctor_info, sample_path, photo_path, layout_id, ills)
            ext = "png" if "png" in mime else "jpg"
            fname = f"{task_id}_p{i+1}.{ext}"
            fpath = os.path.join(OUTPUT_DIR, fname)
            with open(fpath, "wb") as f:
                f.write(base64.b64decode(img_b64))
            results.append({
                "page": i+1,
                "chapter_title": page.get("chapter_title",""),
                "poster_url": f"/output/{fname}"
            })
            # Bug fix: 线程安全地更新 results（用副本替换）
            update_task(task_id, {"results": list(results)})

        update_task(task_id, {"status": "done"})
    except Exception as e:
        update_task(task_id, {"status": "error", "error": str(e)})

@app.get("/api/task/{task_id}")
def get_task(task_id: str):
    if task_id not in tasks:
        raise HTTPException(404, "Task not found")
    return tasks[task_id]

app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

