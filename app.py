"""
医生小红书图文笔记生成器 v3
支持：多张系列笔记、8种版式、底图上传、6种插图风格
"""
import os, uuid, requests, base64, shutil, json, concurrent.futures, threading, time
from dotenv import load_dotenv

load_dotenv()
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from layouts import LAYOUTS, LAYOUT_LIST, ILLUSTRATION_STYLES, ILLUSTRATION_STYLE_LIST

app = FastAPI(title="医生海报科普图文生成器")

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if not ALLOWED_ORIGINS:
    # Dev default; production should set ALLOWED_ORIGINS explicitly.
    ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

AI_BASE = "https://yunwu.ai"

def _parse_key_list(env_value: str) -> list:
    return [k.strip() for k in (env_value or "").split(",") if k.strip()]

# AI key pool (comma-separated). Example: AI_KEYS=sk1,sk2,sk3
AI_KEYS = _parse_key_list(os.getenv("AI_KEYS", ""))
if not AI_KEYS:
    single = os.getenv("AI_KEY", "").strip()
    if single:
        AI_KEYS = [single]

if not AI_KEYS:
    raise RuntimeError("AI_KEYS (or AI_KEY) is required")

_ai_key_lock = threading.Lock()
_ai_key_idx = 0

def get_next_ai_key() -> str:
    global _ai_key_idx
    with _ai_key_lock:
        key = AI_KEYS[_ai_key_idx % len(AI_KEYS)]
        _ai_key_idx += 1
    return key
TEXT_MODEL = "gemini-2.0-flash"
IMAGE_MODEL = "gemini-3.1-flash-image-preview"

PENGIP_API = "https://pengip.com/api/v1"
POINTS_PER_IMAGE = 10  # 每张图片消耗积分

def charge_points(token: str, software: str, times: int, amount_per_time: int) -> dict:
    """预扣积分：调用 /proxy/use times 次。返回 {ok, error}。

    说明：主站扣费接口是按调用次数扣 Tool.points；这里通过循环实现按张计费的预扣。
    """
    try:
        for _ in range(times):
            resp = requests.post(
                f"{PENGIP_API}/proxy/use",
                headers={"Authorization": f"Bearer {token}"},
                json={"software": software},
                timeout=10,
            )
            if resp.status_code != 200:
                data = resp.json()
                return {"ok": False, "error": data.get("error", "积分不足或授权失效")}
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"积分扣除失败: {e}"}


def refund_points(token: str, user_id: str, amount: int, related_id: str, reason: str) -> dict:
    """按差额退回积分（调用主站 /points/refund，幂等由 relatedId 保证）"""
    try:
        resp = requests.post(
            f"{PENGIP_API}/points/refund",
            headers={
                "Authorization": f"Bearer {token}",
                "x-internal-refund-secret": os.environ.get("INTERNAL_REFUND_SECRET", ""),
            },
            json={
                "userId": user_id,
                "amount": amount,
                "relatedId": related_id,
                "reason": reason,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return {"ok": False, "error": resp.text[:200]}
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"退款失败: {e}"}

OUTPUT_DIR = "/var/www/xhs-doctor/output"
UPLOAD_DIR = "/var/www/xhs-doctor/uploads"
STATIC_DIR = "/var/www/xhs-doctor/static"
DEFAULT_SAMPLE = "/var/www/xhs-doctor/static/sample_poster.jpg"

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

tasks = {}
tasks_lock = threading.Lock()

TASK_TTL_HOURS = 2  # 任务保留 2 小时后清理

def cleanup_old_tasks():
    """清理超过 TTL 的已完成任务"""
    cutoff = datetime.now() - timedelta(hours=TASK_TTL_HOURS)
    with tasks_lock:
        expired = [
            k for k, v in tasks.items()
            if v.get("status") in ("done", "error")
            and datetime.fromisoformat(v.get("created_at", datetime.now().isoformat())) < cutoff
        ]
        for k in expired:
            tasks.pop(k, None)

def update_task(task_id, updates):
    """线程安全地更新任务状态"""
    with tasks_lock:
        if task_id in tasks:
            tasks[task_id].update(updates)

ALLOWED_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif"}
ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/gif"
}

def validate_mime_type(content: bytes):
    """通过文件魔数验证 MIME 类型"""
    signatures = {
        b"\xff\xd8\xff": "image/jpeg",
        b"\x89PNG\r\n\x1a\n": "image/png",
        b"RIFF": "image/webp",  # RIFF....WEBP
        b"GIF87a": "image/gif",
        b"GIF89a": "image/gif",
    }
    for sig, mime in signatures.items():
        if content[:len(sig)] == sig:
            # webp 需额外确认
            if mime == "image/webp" and content[8:12] != b"WEBP":
                continue
            return mime
    raise HTTPException(400, "不支持的文件类型，请上传图片文件")
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def validate_image_ext(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_IMAGE_EXTS:
        raise HTTPException(400, f"不支持的文件类型: {ext}，请上传 jpg/png/webp")
    return ext

def validate_file_size(file_size):
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(413, f"文件过大，最大 {MAX_FILE_SIZE // 1024 // 1024}MB")

def validate_upload_path(fpath):
    """验证路径安全性，防止路径遍历"""
    real_path = os.path.realpath(fpath)
    upload_dir = os.path.realpath(UPLOAD_DIR)
    if not real_path.startswith(upload_dir):
        raise HTTPException(400, "非法的文件路径")
    return real_path

PRESET_TOPICS = [
    "双眼皮术后护理注意事项", "隆鼻手术前后须知", "面部轮廓整形恢复指南",
    "抗衰老治疗方案选择", "吸脂手术常见问题解答", "植发手术全流程解析",
    "医美项目如何避坑", "术后饮食与生活注意事项",
]

POINTS_PER_PAGE = {1: (3,5), 2: (3,4), 3: (3,4), 4: (3,4), 5: (3,4)}

POINTS_PROMPT = """你是小红书医疗科普博主，擅长用接地气、有温度的语言写笔记。

主题：{topic}
科室：{department}
总共需要：{total_pages}张图，每张{points_min}-{points_max}个要点
用户自定义要点（若有请润色扩充，若无则自由发挥）：{user_points}

写作风格要求：
- 像真人医生在朋友圈分享，不像教科书
- 多用"其实""很多人不知道""说真的""划重点"等口语词
- 正文每句话不超过25字，简短有力
- 小标题可以用疑问句或感叹句，引发共鸣
- 禁止"专业团队""权威认证"等营销词

输出JSON格式：
{{
  "series_title": "系列总标题（10-20字，口语化）",
  "pages": [
    {{
      "page_num": 1,
      "chapter_title": "第一章标题（6-12字，可以是疑问句）",
      "points": [
        {{
          "heading": "小标题（4-8字，口语化）",
          "body": "1-2句通俗说明，不超过25字，像朋友聊天",
          "illustration_hint": "适合配什么插图（一句话）"
        }}
      ]
    }}
  ]
}}

只返回JSON"""

# ── 工具函数 ──────────────────────────────────────────

def load_image_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def get_mime(path):
    ext = path.rsplit(".", 1)[-1].lower()
    return {"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png","webp":"image/webp"}.get(ext,"image/jpeg")

def retry_with_backoff(max_retries=3, base_delay=1):
    """指数退避重试装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
        return wrapper
    return decorator

@retry_with_backoff(max_retries=3)
def text_call(prompt):
    resp = requests.post(
        f"{AI_BASE}/v1/chat/completions",
        headers={"Authorization": f"Bearer {get_next_ai_key()}", "Content-Type": "application/json"},
        json={"model": TEXT_MODEL, "messages": [{"role":"user","content":prompt}], "max_tokens":3000, "temperature":0.7},
        timeout=120,
    )
    if resp.status_code != 200:
        raise Exception(f"Text AI error: {resp.status_code} {resp.text[:200]}")
    return resp.json()["choices"][0]["message"]["content"]

@retry_with_backoff(max_retries=3)
def image_call(parts_list):
    resp = requests.post(
        f"{AI_BASE}/v1beta/models/{IMAGE_MODEL}:generateContent",
        headers={"Authorization": f"Bearer {get_next_ai_key()}", "Content-Type": "application/json"},
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

def gen_one_poster(page_data, doctor_info, sample_path, photo_path, layout_id, illustrations, title_color="#1e293b", body_color="#475569", font_size="medium"):
    font_size_map = {"small": "标题20px，正文12px", "medium": "标题22px，正文14px", "large": "标题26px，正文16px"}
    font_note = font_size_map.get(font_size, font_size_map["medium"])
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
    ) + f"\n\n【字体颜色要求】标题颜色：{title_color}，正文颜色：{body_color}，字号：{font_note}"

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

@app.post("/api/ocr")
async def ocr_reference(file: UploadFile = File(...), authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "请先激活")

    # 扣费（OCR 1积分）
    try:
        resp = requests.post(
            f"{PENGIP_API}/proxy/use",
            headers={"Authorization": f"Bearer {token}"},
            json={"software": "xhs_doctor_ocr"},
            timeout=10,
        )
        if resp.status_code != 200:
            data = resp.json()
            raise HTTPException(402, data.get("error", "积分不足或授权失效"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"积分校验失败: {e}")

    ext = validate_image_ext(file.filename)
    fname = f"ref_{uuid.uuid4().hex[:8]}.{ext}"
    fpath = os.path.join(UPLOAD_DIR, fname)
    with open(fpath, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # 用视觉模型识别文本
    prompt = "请识别这张小红书笔记截图中的所有文字内容，包括标题、正文、要点等。只输出识别到的文字，保持原有结构，不要添加任何解释。"
    resp = requests.post(
        f"{AI_BASE}/v1/chat/completions",
        headers={"Authorization": f"Bearer {get_next_ai_key()}", "Content-Type": "application/json"},
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:{get_mime(fpath)};base64,{load_image_b64(fpath)}"}},
            {"type": "text", "text": prompt}
        ]}], "max_tokens": 1000},
        timeout=60,
    )
    if resp.status_code != 200:
        raise HTTPException(500, f"OCR失败: {resp.text[:200]}")
    text = resp.json()["choices"][0]["message"]["content"]
    # OCR 完成后删除临时文件，避免堆积
    try:
        os.remove(fpath)
    except Exception:
        pass
    return {"text": text}


@app.post("/api/preview-content")
async def preview_content(
    reference_text: str = Form(...),
    topic: str = Form(""),
    department: str = Form(""),
    total_pages: int = Form(1),
    authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "请先激活")

    # 扣费（文案预览 2积分）
    try:
        resp = requests.post(
            f"{PENGIP_API}/proxy/use",
            headers={"Authorization": f"Bearer {token}"},
            json={"software": "xhs_doctor_preview"},
            timeout=10,
        )
        if resp.status_code != 200:
            data = resp.json()
            raise HTTPException(402, data.get("error", "积分不足或授权失效"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"积分校验失败: {e}")

    pmin, pmax = POINTS_PER_PAGE.get(total_pages, (3, 4))
    prompt = f"""你是小红书医疗科普博主。下面是一篇对标笔记的文字内容，请学习其风格和表达方式，生成一篇全新的、不重复的笔记内容。

对标笔记内容：
{reference_text}

新笔记要求：
- 主题：{topic or '根据对标笔记自动判断'}
- 科室：{department or '根据对标笔记自动判断'}
- 共{total_pages}张图，每张{pmin}-{pmax}个要点
- 风格与对标笔记相似（口语化程度、句式、语气），但内容完全不同
- 禁止抄袭原文任何句子

输出JSON格式：
{{
  "series_title": "系列总标题",
  "pages": [
    {{
      "page_num": 1,
      "chapter_title": "章节标题",
      "points": [
        {{"heading": "小标题", "body": "正文内容", "illustration_hint": "插图描述"}}
      ]
    }}
  ]
}}

只返回JSON"""

    raw = text_call(prompt)
    if "```json" in raw: raw = raw.split("```json")[1].split("```")[0]
    elif "```" in raw: raw = raw.split("```")[1].split("```")[0]
    return json.loads(raw.strip())


@app.get("/api/config")
def get_config():
    return {"topics": PRESET_TOPICS, "layouts": LAYOUT_LIST, "illustration_styles": ILLUSTRATION_STYLE_LIST}

async def require_auth_token(authorization: str) -> str:
    token = (authorization or "").replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "授权失效，请重新激活")

    # Validate token once (fail closed)
    try:
        r = requests.get(
            f"{PENGIP_API}/user/balance",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if r.status_code != 200:
            raise HTTPException(401, "授权失效，请重新激活")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "授权服务暂不可用，请稍后重试")

    return token


@app.post("/api/upload-photo")
async def upload_photo(file: UploadFile = File(...), authorization: str = Header(default="")):
    await require_auth_token(authorization)

    ext = validate_image_ext(file.filename)
    content = await file.read()
    validate_file_size(len(content))
    validate_mime_type(content)
    fname = f"photo_{uuid.uuid4().hex[:8]}.{ext}"
    fpath = os.path.join(UPLOAD_DIR, fname)
    validate_upload_path(fpath)
    with open(fpath, "wb") as f:
        f.write(content)
    return {"url": f"/api/files/{fname}"}


@app.post("/api/upload-sample")
async def upload_sample(file: UploadFile = File(...), authorization: str = Header(default="")):
    await require_auth_token(authorization)

    ext = validate_image_ext(file.filename)
    content = await file.read()
    validate_file_size(len(content))
    validate_mime_type(content)
    fname = f"sample_{uuid.uuid4().hex[:8]}.{ext}"
    fpath = os.path.join(UPLOAD_DIR, fname)
    validate_upload_path(fpath)
    with open(fpath, "wb") as f:
        f.write(content)
    return {"url": f"/api/files/{fname}"}

@app.post("/api/generate")
async def generate(bg: BackgroundTasks,
    topic: str = Form(...),
    doctor_name: str = Form(""),
    hospital: str = Form(""),
    department: str = Form(""),
    photo_url: str = Form(""),
    sample_url: str = Form(""),
    # Back-compat: accept old local path fields but ignore them.
    photo_local_path: str = Form(""),
    sample_local_path: str = Form(""),
    user_points: str = Form(""),
    total_pages: int = Form(1),
    layout_id: str = Form("A"),
    illustration_style: str = Form("flat"),
    title_color: str = Form("#1e293b"),
    body_color: str = Form("#475569"),
    font_size: str = Form("medium"),
    confirmed_content: str = Form(""),
    authorization: str = Header(default="")):

    # 积分预扣（按张数 * 10），最终按成功张数结算并退差额
    token = await require_auth_token(authorization)

    charge = charge_points(token, "xhs_doctor_generate", total_pages, POINTS_PER_IMAGE)
    if not charge["ok"]:
        raise HTTPException(402, charge["error"])

    task_id = uuid.uuid4().hex
    doctor_info = {"name": doctor_name, "hospital": hospital, "department": department}
    
    def _url_to_upload_path(url: str) -> str:
        url = (url or "").strip()
        if not url:
            return ""
        # Expect /api/files/<filename>
        if not url.startswith("/api/files/"):
            raise HTTPException(400, "非法文件URL")
        filename = url.split("/api/files/", 1)[1]
        if not filename:
            raise HTTPException(400, "非法文件URL")
        fpath = os.path.join(UPLOAD_DIR, filename)
        return validate_upload_path(fpath)

    photo_path = _url_to_upload_path(photo_url)
    sample_path_from_upload = _url_to_upload_path(sample_url)

    sample_path = sample_path_from_upload if sample_path_from_upload and os.path.exists(sample_path_from_upload) else DEFAULT_SAMPLE
    
    with tasks_lock:
        cleanup_old_tasks()
        tasks[task_id] = {
            "status": "pending",
            "task_id": task_id,
            "total_pages": total_pages,
            "results": [],
            "created_at": datetime.now().isoformat(),
            # Do not keep bearer token in task state.
            "refund_settled": False,
        }

    # Get userId for refunds (fail closed)
    bal = requests.get(
        f"{PENGIP_API}/user/balance",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if bal.status_code != 200:
        raise HTTPException(503, "授权服务暂不可用，请稍后重试")

    user_id = None
    try:
        user_id = bal.json().get("userId")
    except Exception:
        user_id = None

    if not user_id:
        raise HTTPException(503, "授权服务暂不可用，请稍后重试")

    update_task(task_id, {"charged_pages": total_pages, "success_pages": 0, "user_id": user_id})

    bg.add_task(do_generate, task_id, token, user_id, topic, user_points, doctor_info,
                photo_path, sample_path, total_pages, layout_id, illustration_style,
                title_color, body_color, font_size, confirmed_content)
    return {"task_id": task_id}

def do_generate(task_id, token, user_id, topic, user_points, doctor_info, photo_path, sample_path, total_pages, layout_id, illus_style, title_color="#1e293b", body_color="#475569", font_size="medium", confirmed_content=""):
    """生成图片任务。

    计费规则：请求开始时已按 total_pages 预扣积分；这里按实际成功页数结算并退差额。
    """
    success_pages = 0
    try:
        update_task(task_id, {"status": "generating_points"})
        # 对标模式：直接用确认好的文案，跳过AI生成
        if confirmed_content:
            try:
                series_data = json.loads(confirmed_content)
            except Exception:
                series_data = gen_all_points(topic, doctor_info.get("department",""), total_pages, user_points)
        else:
            series_data = gen_all_points(topic, doctor_info.get("department",""), total_pages, user_points)
        pages = series_data.get("pages", [])[:total_pages]
        # Bug fix: AI返回页数不足时补齐（复制最后一页）
        while len(pages) < total_pages and pages:
            pages.append(pages[-1])
        update_task(task_id, {"series_title": series_data.get("series_title","")})

        # Step 2: 逐页生成插图
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
            img_b64, mime = gen_one_poster(page, doctor_info, sample_path, photo_path, layout_id, ills, title_color, body_color, font_size)
            ext = "png" if "png" in mime else "jpg"
            fname = f"{task_id}_p{i+1}.{ext}"
            fpath = os.path.join(OUTPUT_DIR, fname)
            with open(fpath, "wb") as f:
                f.write(base64.b64decode(img_b64))
            results.append({
                "page": i+1,
                "chapter_title": page.get("chapter_title",""),
                "poster_url": f"/api/files/{fname}",
            })
            success_pages += 1
            update_task(task_id, {"results": list(results)})

        update_task(task_id, {"status": "done", "success_pages": success_pages})
    except Exception as e:
        update_task(task_id, {"status": "error", "error": str(e), "success_pages": success_pages})
    finally:
        # Settle refund once at task completion.
        try:
            charged_pages = int((tasks.get(task_id) or {}).get("charged_pages") or 0)
            success_pages2 = int((tasks.get(task_id) or {}).get("success_pages") or 0)
            to_refund = max(0, (charged_pages - success_pages2) * POINTS_PER_IMAGE)
            if to_refund > 0 and user_id:
                related_id = f"xhs_doctor_{task_id}"
                rr = refund_points(
                    token=token,
                    user_id=user_id,
                    amount=to_refund,
                    related_id=related_id,
                    reason=f"xhs-doctor refund: success={success_pages2}/{charged_pages}",
                )
                if not rr.get("ok"):
                    update_task(task_id, {"refund_error": rr.get("error")})
            update_task(task_id, {"refund_settled": True})
        except Exception as _e:
            update_task(task_id, {"refund_error": str(_e)})

@app.get("/api/task/{task_id}")
def get_task(task_id: str):
    if task_id not in tasks:
        raise HTTPException(404, "Task not found")

    # GET should be read-only: no settlement side effects here.
    return tasks[task_id]

@app.get("/api/files/{filename}")
async def download_file(filename: str, authorization: str = Header(default="")):
    # Basic auth gate (no deduction)
    await require_auth_token(authorization)

    # Only allow serving from known directories
    candidate_paths = [
        os.path.join(UPLOAD_DIR, filename),
        os.path.join(OUTPUT_DIR, filename),
    ]
    real_paths = []
    for p in candidate_paths:
        try:
            real_paths.append(validate_upload_path(p) if p.startswith(UPLOAD_DIR) else os.path.realpath(p))
        except Exception:
            pass

    for p in candidate_paths:
        rp = os.path.realpath(p)
        # uploads must pass validate_upload_path; outputs must be within OUTPUT_DIR
        if rp.startswith(os.path.realpath(UPLOAD_DIR)) or rp.startswith(os.path.realpath(OUTPUT_DIR)):
            if os.path.isfile(rp):
                from fastapi.responses import FileResponse
                return FileResponse(rp)

    raise HTTPException(404, "File not found")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

