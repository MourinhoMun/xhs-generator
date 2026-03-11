const BASE = window.location.pathname.replace(/\/[^/]*$/, '').replace(/\/$/, '');

let photoUrl = "", sampleUrl = "", selectedPages = 1;
let selectedLayout = "A", selectedStyle = "flat", selectedFontSize = "medium";
let selectedTitleColor = "#1e293b", selectedBodyColor = "#475569";
let currentMode = "normal", confirmedContent = null, pollTimer = null;

// 页面卸载时清理定时器
window.addEventListener("beforeunload", () => {
  if (pollTimer) clearInterval(pollTimer);
});

window.onload = async () => {
  const res = await fetch(`${BASE}/api/config`);
  const cfg = await res.json();

  document.getElementById("layoutGrid").innerHTML = cfg.layouts.map(l =>
    `<div class="option-card ${l.id==='A'?'active':''}" onclick="selectLayout(this,'${l.id}')">
      <div class="name">${l.name}</div><div class="desc">${l.desc}</div>
    </div>`).join("");

  document.getElementById("styleGrid").innerHTML = cfg.illustration_styles.map(s =>
    `<div class="option-card ${s.id==='flat'?'active':''}" onclick="selectStyle(this,'${s.id}')">
      <div class="icon">${s.emoji}</div><div class="name">${s.name}</div><div class="desc">${s.desc}</div>
    </div>`).join("");

  const savedToken = localStorage.getItem("user_token");

  // 尝试从主站 cookie 静默换取 token（同域，cookie 自动携带）
  try {
    const r = await fetch("https://pengip.com/api/v1/user/token", { credentials: "include" });
    if (r.ok) {
      const data = await r.json();
      if (data.token) {
        localStorage.setItem("user_token", data.token);
        const tokenSection = document.getElementById("tokenSection");
        if (tokenSection) tokenSection.style.display = "none";
      } else {
        // 登录态有效但无 token，显示提示
        if (!savedToken) {
          const tokenSection = document.getElementById("tokenSection");
          if (tokenSection) tokenSection.style.display = "block";
        }
      }
    } else {
      // 未登录，显示提示
      if (!savedToken) {
        const tokenSection = document.getElementById("tokenSection");
        if (tokenSection) tokenSection.style.display = "block";
      }
    }
  } catch(e) {
    if (!savedToken) {
      const tokenSection = document.getElementById("tokenSection");
      if (tokenSection) tokenSection.style.display = "block";
    }
  }

  const saved = localStorage.getItem("doctor_info");
  if (saved) {
    const d = JSON.parse(saved);
    document.getElementById("doctorName").value = d.name || "";
    document.getElementById("hospital").value = d.hospital || "";
    document.getElementById("department").value = d.department || "";
    if (d.photo_url) {
      document.getElementById("photoPreview").innerHTML = `<img src="${d.photo_url}">`;
      photoUrl = d.photo_url || "";
    }
  }
};

function switchMode(mode, el) {
  currentMode = mode;
  confirmedContent = null;
  document.querySelectorAll(".mode-tab").forEach(t => t.classList.remove("active"));
  el.classList.add("active");
  document.querySelectorAll(".mode-panel").forEach(p => p.classList.remove("active"));
  document.getElementById(mode === "normal" ? "modeNormal" : "modeRef").classList.add("active");
}

function selectPages(el, n) {
  document.querySelectorAll(".page-btn").forEach(b => b.classList.remove("active"));
  el.classList.add("active");
  selectedPages = n;
}

function selectLayout(el, id) {
  document.querySelectorAll("#layoutGrid .option-card").forEach(c => c.classList.remove("active"));
  el.classList.add("active");
  selectedLayout = id;
}

function selectStyle(el, id) {
  document.querySelectorAll("#styleGrid .option-card").forEach(c => c.classList.remove("active"));
  el.classList.add("active");
  selectedStyle = id;
}

function selectFontSize(el, size) {
  el.closest(".pages-grid").querySelectorAll(".page-btn").forEach(b => b.classList.remove("active"));
  el.classList.add("active");
  selectedFontSize = size;
}

function selectColor(type, el) {
  const rowId = type === "title" ? "titleColorRow" : "bodyColorRow";
  document.querySelectorAll(`#${rowId} .color-swatch`).forEach(s => s.classList.remove("active"));
  el.classList.add("active");
  if (type === "title") selectedTitleColor = el.dataset.color;
  else selectedBodyColor = el.dataset.color;
}

function customColor(type, val) {
  if (type === "title") { selectedTitleColor = val; document.querySelectorAll("#titleColorRow .color-swatch").forEach(s => s.classList.remove("active")); }
  else { selectedBodyColor = val; document.querySelectorAll("#bodyColorRow .color-swatch").forEach(s => s.classList.remove("active")); }
}

function saveDoctorInfo(photoUrl) {
  localStorage.setItem("doctor_info", JSON.stringify({
    name: document.getElementById("doctorName").value,
    hospital: document.getElementById("hospital").value,
    department: document.getElementById("department").value,
    photo_url: photoUrl || document.getElementById("photoPreview").querySelector("img")?.src || "",
  }));
}

async function uploadPhoto(input) {
  const file = input.files[0]; if (!file) return;
  const token = localStorage.getItem("user_token") || "";
  if (!token) { alert("请先登录（或填写 Token）"); return; }

  const fd = new FormData(); fd.append("file", file);
  const res = await fetch(`${BASE}/api/upload-photo`, { method: "POST", body: fd, headers: { "Authorization": `Bearer ${token}` } });
  const data = await res.json();
  if (!res.ok) {
    alert(data?.detail || data?.error || "上传失败");
    return;
  }
  document.getElementById("photoPreview").innerHTML = `<img src="${data.url}">`;
  photoUrl = data.url;
  saveDoctorInfo(data.url);
}

async function uploadSample(input) {
  const file = input.files[0]; if (!file) return;
  const token = localStorage.getItem("user_token") || "";
  if (!token) { alert("请先登录（或填写 Token）"); return; }

  const fd = new FormData(); fd.append("file", file);
  const res = await fetch(`${BASE}/api/upload-sample`, { method: "POST", body: fd, headers: { "Authorization": `Bearer ${token}` } });
  const data = await res.json();
  if (!res.ok) {
    alert(data?.detail || data?.error || "上传失败");
    return;
  }
  document.getElementById("samplePreview").innerHTML = `<img src="${data.url}">`;
  sampleUrl = data.url;
}

async function uploadRef(input) {
  const file = input.files[0]; if (!file) return;
  const token = localStorage.getItem("user_token") || "";
  if (!token) { alert("请先填写 Token"); return; }

  document.getElementById("refPreview").innerHTML = `<div class="spinner" style="width:24px;height:24px;margin:auto"></div>`;
  const fd = new FormData(); fd.append("file", file);
  const res = await fetch(`${BASE}/api/ocr`, { method: "POST", body: fd, headers: { "Authorization": `Bearer ${token}` } });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 || res.status === 403) {
      localStorage.removeItem("user_token");
      document.getElementById("tokenSection").style.display = "block";
      alert("登录已过期，请前往 pengip.com 重新登录后刷新此页面");
    } else if (res.status === 402) {
      alert("积分不足，请前往 pengip.com 充值");
    } else {
      alert("识别失败，请重试");
    }
    document.getElementById("refPreview").innerHTML = "📸";
    return;
  }
  const data = await res.json();

  document.getElementById("refPreview").innerHTML = `<div style="font-size:12px;color:#16a34a;padding:4px">✅ 识别成功</div>`;
  document.getElementById("refText").value = data.text;
  document.getElementById("refText").value = data.text;
  document.getElementById("refTextArea").style.display = "block";
  confirmedContent = null;
}

async function previewContent() {
  const token = localStorage.getItem("user_token") || "";
  if (!token) { alert("请先填写 Token"); return; }
  const refText = document.getElementById("refText").value.trim();
  if (!refText) { alert("请先上传截图或填写对标文字"); return; }

  const btn = document.getElementById("previewBtn");
  btn.disabled = true; btn.textContent = "生成中...";

  const fd = new FormData();
  fd.append("reference_text", refText);
  fd.append("topic", document.getElementById("refTopic").value);
  fd.append("department", document.getElementById("department").value);
  fd.append("total_pages", selectedPages);

  const res = await fetch(`${BASE}/api/preview-content`, { method: "POST", body: fd, headers: { "Authorization": `Bearer ${token}` } });
  btn.disabled = false; btn.textContent = "✨ 生成文案预览";

  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    if (res.status === 401 || res.status === 403) {
      localStorage.removeItem("user_token");
      document.getElementById("tokenSection").style.display = "block";
      alert("登录已过期，请前往 pengip.com 重新登录后刷新此页面");
    } else if (res.status === 402) {
      alert("积分不足，请前往 pengip.com 充值");
    } else {
      alert(errData.detail || "生成失败，请重试");
    }
    return;
  }
  const data = await res.json();
  confirmedContent = data;

  const pagesHtml = data.pages.map(p => `
    <div style="margin-bottom:10px">
      <div style="font-weight:700;color:#166534">第${p.page_num}张：${p.chapter_title}</div>
      ${p.points.map(pt => `<div style="margin-left:12px;margin-top:4px">· <b>${pt.heading}</b> ${pt.body}</div>`).join("")}
    </div>`).join("");

  document.getElementById("contentPreviewArea").innerHTML = `
    <div class="content-preview">
      <h4>📋 ${data.series_title}</h4>
      ${pagesHtml}
      <div style="margin-top:12px;font-size:12px;color:#16a34a">✅ 文案已确认，点击下方按钮生成图文海报</div>
    </div>`;
}

async function startGenerate() {
  const token = localStorage.getItem("user_token") || "";
  if (!token) { alert("请先填写 Token"); return; }

  if (currentMode === "ref" && !confirmedContent) {
    alert("请先生成并确认文案预览"); return;
  }
  if (currentMode === "normal" && !document.getElementById("topic").value.trim()) {
    alert("请输入笔记主题"); return;
  }

  saveDoctorInfo();
  const btn = document.getElementById("genBtn");
  btn.disabled = true;
  showProgress("pending", 0);

  const fd = new FormData();
  fd.append("doctor_name", document.getElementById("doctorName").value);
  fd.append("hospital", document.getElementById("hospital").value);
  fd.append("department", document.getElementById("department").value);
  fd.append("photo_url", photoUrl);
  fd.append("sample_url", sampleUrl);
  fd.append("total_pages", selectedPages);
  fd.append("layout_id", selectedLayout);
  fd.append("illustration_style", selectedStyle);
  fd.append("title_color", selectedTitleColor);
  fd.append("body_color", selectedBodyColor);
  fd.append("font_size", selectedFontSize);

  if (currentMode === "ref" && confirmedContent) {
    fd.append("topic", confirmedContent.series_title);
    fd.append("confirmed_content", JSON.stringify(confirmedContent));
  } else {
    fd.append("topic", document.getElementById("topic").value.trim());
    fd.append("user_points", document.getElementById("userPoints").value);
  }

  const res = await fetch(`${BASE}/api/generate`, { method: "POST", body: fd, headers: { "Authorization": `Bearer ${token}` } });
  const data = await res.json();
  if (!res.ok) {
    if (res.status === 401 || res.status === 403) {
      localStorage.removeItem("user_token");
      document.getElementById("tokenSection").style.display = "block";
      alert("登录已过期，请前往 pengip.com 重新登录后刷新此页面");
    } else if (res.status === 402) {
      alert("积分不足，请前往 pengip.com 充值");
    } else {
      alert(data.detail || data.error || "请求失败");
    }
    btn.disabled = false;
    return;
  }
  pollResult(data.task_id, btn);
}

function showProgress(status, doneCount) {
  const steps = ["generating_points","generating_illustrations","generating_poster"];
  const labels = { generating_points:"① 生成要点", generating_illustrations:"② 生成插图", generating_poster:"③ 合成海报", done:"✅ 完成" };
  const currentIdx = steps.indexOf(status.startsWith("generating_poster") ? "generating_poster" : status);
  const stepsHtml = steps.map((s, i) => {
    const cls = i < currentIdx ? "step done" : i === currentIdx ? "step active" : "step";
    return `<span class="${cls}">${labels[s]}</span>`;
  }).join("") + (status === "done" ? `<span class="step done">${labels.done}</span>` : "");
  document.getElementById("resultArea").innerHTML = `
    <div class="progress-box">
      <div class="spinner"></div>
      <div style="font-size:14px;color:#475569">AI 正在生成，请稍候...</div>
      <div class="progress-steps">${stepsHtml}</div>
      ${doneCount > 0 ? `<div style="margin-top:12px;font-size:12px;color:#16a34a">已完成 ${doneCount} 张 ✓</div>` : ""}
    </div>`;
}

function pollResult(task_id, btn) {
  let lastDoneCount = 0;
  pollTimer = setInterval(async () => {
    const res = await fetch(`${BASE}/api/task/${task_id}`);
    const data = await res.json();
    const doneCount = (data.results || []).length;
    if (data.status !== "done" && data.status !== "error") {
      if (doneCount !== lastDoneCount) { lastDoneCount = doneCount; showPartialResults(data.results || []); }
      else showProgress(data.status, doneCount);
    }
    if (data.status === "done") {
      clearInterval(pollTimer); btn.disabled = false; showAllResults(data);
    } else if (data.status === "error") {
      clearInterval(pollTimer); btn.disabled = false;
      document.getElementById("resultArea").innerHTML = `<div class="result-box" style="color:#ef4444;text-align:center">❌ 生成失败：${data.error}</div>`;
    }
  }, 3000);
}

function showPartialResults(results) {
  document.getElementById("resultArea").innerHTML = `
    <div class="result-box">
      <div style="font-size:13px;color:#475569;margin-bottom:12px">已生成 ${results.length} / ${selectedPages} 张，继续生成中...</div>
      <div class="result-grid">${results.map(r => resultItemHtml(r)).join("")}</div>
    </div>`;
}

function showAllResults(data) {
  document.getElementById("resultArea").innerHTML = `
    <div class="result-box">
      <div style="font-size:15px;font-weight:700;margin-bottom:4px;color:#1e293b">✅ 全部生成完成！</div>
      <div style="font-size:13px;color:#64748b;margin-bottom:16px">${data.series_title || ""}</div>
      <div class="result-grid">${(data.results || []).map(r => resultItemHtml(r)).join("")}</div>
      <div style="margin-top:16px;text-align:center"><button class="btn-sm" onclick="location.reload()">🔄 重新生成</button></div>
    </div>`;
}

function resultItemHtml(r) {
  const rawUrl = `${BASE}${r.poster_url}`;
  // Use short-lived signed URL for <img src> (no Authorization headers)
  const imgId = `img_${r.page}_${Math.random().toString(16).slice(2)}`;
  setTimeout(() => attachSignedSrc(imgId, rawUrl), 0);

  return `<div class="result-item">
    <img id="${imgId}" src="" loading="lazy" style="background:#f1f5f9">
    <div class="result-item-footer">
      <span>第${r.page}张：${r.chapter_title}</span>
      <a href="${rawUrl}" download target="_blank"><button class="btn-sm">⬇️ 下载</button></a>
    </div>
  </div>`;
}

async function attachSignedSrc(imgId, rawUrl) {
  try {
    const token = localStorage.getItem('user_token') || '';
    if (!token) return;

    // rawUrl looks like /xhs-doctor/api/files/<fname> or /api/files/<fname>
    const u = new URL(rawUrl, window.location.origin);
    const filename = u.pathname.split('/').pop();
    if (!filename) return;

    const r = await fetch(`${BASE}/api/file-token?filename=${encodeURIComponent(filename)}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await r.json();
    if (!r.ok) return;

    const signed = `${BASE}/api/files/${encodeURIComponent(filename)}?exp=${data.exp}&sig=${data.sig}`;
    const el = document.getElementById(imgId);
    if (el) el.src = signed;
  } catch (e) {
    // ignore
  }
}
