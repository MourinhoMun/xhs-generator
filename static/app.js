// 自动检测 base path（兼容子路径部署如 /xhs/）
const BASE = window.location.pathname.replace(/\/[^/]*$/, '').replace(/\/$/, '');

let photoLocalPath = "";
let sampleLocalPath = "";
let selectedPages = 1;
let selectedLayout = "A";
let selectedStyle = "flat";
let pollTimer = null;

window.onload = async () => {
  const res = await fetch(`${BASE}/api/config`);
  const cfg = await res.json();

  // 版式
  document.getElementById("layoutGrid").innerHTML = cfg.layouts.map(l =>
    `<div class="option-card ${l.id==='A'?'active':''}" onclick="selectLayout(this,'${l.id}')">
      <div class="name">${l.name}</div>
      <div class="desc">${l.desc}</div>
    </div>`
  ).join("");

  // 插图风格
  document.getElementById("styleGrid").innerHTML = cfg.illustration_styles.map(s =>
    `<div class="option-card ${s.id==='flat'?'active':''}" onclick="selectStyle(this,'${s.id}')">
      <div class="icon">${s.emoji}</div>
      <div class="name">${s.name}</div>
      <div class="desc">${s.desc}</div>
    </div>`
  ).join("");

  // 恢复医生信息
  const saved = localStorage.getItem("doctor_info");
  if (saved) {
    const d = JSON.parse(saved);
    document.getElementById("doctorName").value = d.name || "";
    document.getElementById("hospital").value = d.hospital || "";
    document.getElementById("department").value = d.department || "";
    if (d.photo_url) {
      document.getElementById("photoPreview").innerHTML = `<img src="${d.photo_url}">`;
      photoLocalPath = d.photo_local_path || "";
    }
  }
};

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

async function uploadPhoto(input) {
  const file = input.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${BASE}/api/upload-photo`, { method: "POST", body: fd });
  const data = await res.json();
  document.getElementById("photoPreview").innerHTML = `<img src="${data.url}">`;
  photoLocalPath = data.local_path;
  saveDoctorInfo(data.url);
}

async function uploadSample(input) {
  const file = input.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${BASE}/api/upload-sample`, { method: "POST", body: fd });
  const data = await res.json();
  document.getElementById("samplePreview").innerHTML = `<img src="${data.url}">`;
  sampleLocalPath = data.local_path;
}

function saveDoctorInfo(photoUrl) {
  localStorage.setItem("doctor_info", JSON.stringify({
    name: document.getElementById("doctorName").value,
    hospital: document.getElementById("hospital").value,
    department: document.getElementById("department").value,
    photo_url: photoUrl || document.getElementById("photoPreview").querySelector("img")?.src || "",
    photo_local_path: photoLocalPath,
  }));
}

async function startGenerate() {
  const topic = document.getElementById("topic").value.trim();
  if (!topic) { alert("请输入笔记主题"); return; }
  saveDoctorInfo();

  const btn = document.getElementById("genBtn");
  btn.disabled = true;
  showProgress("pending", 0);

  const fd = new FormData();
  fd.append("topic", topic);
  fd.append("doctor_name", document.getElementById("doctorName").value);
  fd.append("hospital", document.getElementById("hospital").value);
  fd.append("department", document.getElementById("department").value);
  fd.append("photo_local_path", photoLocalPath);
  fd.append("sample_local_path", sampleLocalPath);
  fd.append("user_points", document.getElementById("userPoints").value);
  fd.append("total_pages", selectedPages);
  fd.append("layout_id", selectedLayout);
  fd.append("illustration_style", selectedStyle);

  const res = await fetch(`${BASE}/api/generate`, { method: "POST", body: fd });
  const { task_id } = await res.json();
  pollResult(task_id, btn);
}

function showProgress(status, doneCount) {
  const steps = ["generating_points","generating_illustrations","generating_poster"];
  const labels = { generating_points:"① 生成要点", generating_illustrations:"② 生成插图", generating_poster:"③ 合成海报", done:"✅ 完成" };
  const currentIdx = steps.indexOf(status.startsWith("generating_poster") ? "generating_poster" : status);
  const stepsHtml = steps.map((s, i) => {
    const cls = i < currentIdx ? "step done" : i === currentIdx ? "step active" : "step";
    return `<span class="${cls}">${labels[s]}</span>`;
  }).join("") + (status === "done" ? `<span class="step done">${labels.done}</span>` : "");

  const progressMsg = status.startsWith("generating_poster_")
    ? `正在合成第 ${status.split("_")[2]} / ${selectedPages} 张...`
    : "AI 正在生成，请稍候...";

  document.getElementById("resultArea").innerHTML = `
    <div class="progress-box">
      <div class="spinner"></div>
      <div style="font-size:14px;color:#475569">${progressMsg}</div>
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
      if (doneCount !== lastDoneCount) {
        lastDoneCount = doneCount;
        showPartialResults(data.results || []);
      } else {
        showProgress(data.status, doneCount);
      }
    }
    if (data.status === "done") {
      clearInterval(pollTimer);
      btn.disabled = false;
      showAllResults(data);
    } else if (data.status === "error") {
      clearInterval(pollTimer);
      btn.disabled = false;
      document.getElementById("resultArea").innerHTML =
        `<div class="result-box" style="color:#ef4444;text-align:center">❌ 生成失败：${data.error}</div>`;
    }
  }, 3000);
}

function showPartialResults(results) {
  const itemsHtml = results.map(r => resultItemHtml(r)).join("");
  document.getElementById("resultArea").innerHTML = `
    <div class="result-box">
      <div style="font-size:13px;color:#475569;margin-bottom:12px">已生成 ${results.length} / ${selectedPages} 张，继续生成中...</div>
      <div class="result-grid">${itemsHtml}</div>
    </div>`;
}

function showAllResults(data) {
  const itemsHtml = (data.results || []).map(r => resultItemHtml(r)).join("");
  document.getElementById("resultArea").innerHTML = `
    <div class="result-box">
      <div style="font-size:15px;font-weight:700;margin-bottom:4px;color:#1e293b">✅ 全部生成完成！</div>
      <div style="font-size:13px;color:#64748b;margin-bottom:16px">${data.series_title || ""}</div>
      <div class="result-grid">${itemsHtml}</div>
      <div style="margin-top:16px;text-align:center">
        <button class="btn-sm" onclick="location.reload()">🔄 重新生成</button>
      </div>
    </div>`;
}

function resultItemHtml(r) {
  const url = `${BASE}${r.poster_url}`;
  return `
    <div class="result-item">
      <img src="${url}" loading="lazy">
      <div class="result-item-footer">
        <span>第${r.page}张：${r.chapter_title}</span>
        <a href="${url}" download target="_blank"><button class="btn-sm">⬇️ 下载</button></a>
      </div>
    </div>`;
}
