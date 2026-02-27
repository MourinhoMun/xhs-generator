// 医生小红书图文生成器
const API = '.';
let photoUrl = '';
let pollTimer = null;

// 页面加载时恢复保存的医生信息
window.addEventListener('DOMContentLoaded', () => {
    const saved = localStorage.getItem('xhs_doctor_info');
    if (saved) {
        const d = JSON.parse(saved);
        document.getElementById('doctorName').value = d.name || '';
        document.getElementById('hospital').value = d.hospital || '';
        document.getElementById('department').value = d.department || '';
        document.getElementById('xhsId').value = d.xhs_id || '';
        if (d.photo_url) {
            photoUrl = d.photo_url;
            document.getElementById('photoPreview').innerHTML = `<img src="${photoUrl}">`;
        }
    }
});

function saveDoctorInfo() {
    const info = {
        name: document.getElementById('doctorName').value.trim(),
        hospital: document.getElementById('hospital').value.trim(),
        department: document.getElementById('department').value.trim(),
        xhs_id: document.getElementById('xhsId').value.trim(),
        photo_url: photoUrl,
    };
    localStorage.setItem('xhs_doctor_info', JSON.stringify(info));
}

async function uploadPhoto(input) {
    if (!input.files[0]) return;
    const fd = new FormData();
    fd.append('file', input.files[0]);
    try {
        const resp = await fetch(`${API}/api/upload-photo`, { method: 'POST', body: fd });
        const data = await resp.json();
        photoUrl = data.url;
        document.getElementById('photoPreview').innerHTML = `<img src="${photoUrl}">`;
        saveDoctorInfo();
    } catch(e) { alert('上传失败: ' + e.message); }
}

async function startGenerate() {
    const topic = document.getElementById('topic').value.trim();
    if (!topic) { alert('请输入笔记主题'); return; }
    saveDoctorInfo();
    const btn = document.getElementById('genBtn');
    btn.disabled = true;
    btn.textContent = '⏳ 生成中...';

    const fd = new FormData();
    fd.append('topic', topic);
    fd.append('doctor_name', document.getElementById('doctorName').value.trim());
    fd.append('hospital', document.getElementById('hospital').value.trim());
    fd.append('department', document.getElementById('department').value.trim());
    fd.append('xhs_id', document.getElementById('xhsId').value.trim());
    fd.append('photo_url', photoUrl);
    fd.append('extra', document.getElementById('extra').value.trim());

    try {
        const resp = await fetch(`${API}/api/generate`, { method: 'POST', body: fd });
        const data = await resp.json();
        showProgress();
        pollTask(data.task_id);
    } catch(e) {
        alert('请求失败: ' + e.message);
        btn.disabled = false;
        btn.textContent = '🚀 一键生成图文笔记';
    }
}

function showProgress() {
    const el = document.getElementById('resultArea');
    el.innerHTML = `
        <div class="progress-box" style="min-height:200px">
            <div class="spinner"></div>
            <div style="font-size:16px;font-weight:600;margin-bottom:8px">🤖 AI正在生成科普内容...</div>
            <div style="color:#64748b;font-size:14px">正在撰写文案并排版海报，大约需要30-60秒</div>
        </div>`;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function pollTask(taskId) {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
        try {
            const resp = await fetch(`${API}/api/task/${taskId}`);
            const t = await resp.json();
            if (t.status === 'done') {
                clearInterval(pollTimer);
                showResult(t);
            } else if (t.status === 'error') {
                clearInterval(pollTimer);
                showError(t.error);
            }
        } catch(e) { console.error(e); }
    }, 2000);
}

function showResult(t) {
    const btn = document.getElementById('genBtn');
    btn.disabled = false;
    btn.textContent = '🚀 一键生成图文笔记';
    const el = document.getElementById('resultArea');
    el.innerHTML = `
        <div class="result-box">
            <div style="font-size:36px;margin-bottom:10px">✅</div>
            <div style="font-size:18px;font-weight:700;margin-bottom:8px">图文笔记已生成！</div>
            <div style="color:#64748b;font-size:14px;margin-bottom:18px">打开海报页面后，可以截图保存发小红书</div>
            <div class="result-link" style="margin-bottom:14px">
                <a href=".${t.poster_url}" target="_blank">📄 查看海报 →</a>
            </div>
            <div style="color:#94a3b8;font-size:12px;margin-bottom:14px">提示：在海报页面按 Ctrl+P 可以打印/保存为PDF</div>
            <button class="btn-outline" onclick="document.getElementById('resultArea').innerHTML=''">关闭</button>
        </div>`;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function showError(msg) {
    const btn = document.getElementById('genBtn');
    btn.disabled = false;
    btn.textContent = '🚀 一键生成图文笔记';
    const el = document.getElementById('resultArea');
    el.innerHTML = `
        <div class="result-box" style="border:1px solid #fca5a5">
            <div style="color:#ef4444;margin-bottom:12px">❌ 生成失败：${msg}</div>
            <button class="btn-outline" onclick="document.getElementById('resultArea').innerHTML=''">关闭</button>
        </div>`;
}
