/* 格式转换工坊 · 前端逻辑（无框架、无构建） */
"use strict";

const $ = (id) => document.getElementById(id);

const STATUS_TEXT = { pending: "等待", queued: "排队中", running: "转换中", done: "成功", error: "失败" };

let targets = [];
let selectedKey = null;
let lastRunning = false;

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || r.statusText || "请求失败");
  return d;
}

function fmtSize(bytes) {
  if (bytes >= 1024 * 1024 * 1024) return (bytes / 1024 / 1024 / 1024).toFixed(2) + " GB";
  if (bytes >= 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + " MB";
  if (bytes >= 1024) return (bytes / 1024).toFixed(0) + " KB";
  return bytes + " B";
}

function toast(msg, isErr = false) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.toggle("err", isErr);
  t.hidden = false;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => { t.hidden = true; }, 2600);
}

/* ---------- 目标格式 ---------- */

function renderFormats() {
  const box = $("formatGroup");
  box.innerHTML = "";
  let lastCat = null;
  for (const t of targets) {
    if (t.category !== lastCat) {
      lastCat = t.category;
      const cat = document.createElement("div");
      cat.className = "format-cat";
      cat.textContent = t.category + "类";
      box.appendChild(cat);
    }
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "format-btn" + (t.available ? "" : " disabled");
    btn.dataset.key = t.key;
    btn.innerHTML = `
      <span class="fmt-icon">${t.ext.toUpperCase().slice(0, 4)}</span>
      <span class="fmt-body">
        <span class="fmt-label">${t.label}</span><br>
        <span class="fmt-note">${t.note}</span>
      </span>
      ${t.badge ? `<span class="fmt-badge ${t.available ? "" : "soon"}">${t.badge}</span>` : ""}`;
    if (t.available) {
      btn.addEventListener("click", () => selectTarget(t.key));
      if (t.key === selectedKey) btn.classList.add("active");
    } else {
      btn.disabled = true;
    }
    box.appendChild(btn);
  }
}

function selectTarget(key) {
  selectedKey = key;
  document.querySelectorAll(".format-btn").forEach(b =>
    b.classList.toggle("active", b.dataset.key === key && !b.disabled));
}

/* ---------- 文件列表 ---------- */

function renderStatus(d) {
  const files = d.files, counts = d.counts, job = d.job;
  const hasFiles = files.length > 0;
  $("listCard").hidden = !hasFiles;
  $("outCard").hidden = !hasFiles;
  $("actionBar").hidden = !hasFiles;

  /* 总进度 */
  const inJob = job && (job.running || job.finished_at);
  $("progressWrap").hidden = !inJob;
  if (inJob) {
    const doneN = (counts.done || 0) + (counts.error || 0);
    const pct = job.total ? Math.round((doneN / job.total) * 100) : 0;
    $("progressBar").style.width = pct + "%";
    $("progressText").textContent = `已完成 ${doneN} / ${job.total}` +
      (counts.error ? ` · 失败 ${counts.error}` : "");
  }

  /* 完成横幅：由"运行中"切换到"结束"时弹出 */
  if (lastRunning && job && !job.running) {
    const ok = counts.done || 0, bad = counts.error || 0;
    const b = $("banner");
    b.hidden = false;
    b.className = "banner" + (bad ? " has-err" : "");
    b.innerHTML = `${bad ? "转换结束，有部分失败" : "🎉 转换完成！"} 成功 ${ok} 个` +
      (bad ? `，失败 ${bad} 个（悬停红色标签可看原因，重新点“开始转换”可重试）` : "") +
      ` <button class="link-btn" onclick="openOutput()">打开输出文件夹</button>`;
    $("btnOpenOut").hidden = false;
    toast(bad ? `完成：成功 ${ok}，失败 ${bad}` : `全部完成，成功 ${ok} 个`, !!bad);
  }
  if (job && job.running) { $("banner").hidden = true; $("btnOpenOut").hidden = !(counts.done > 0); }
  lastRunning = !!(job && job.running);

  /* 行 */
  const ul = $("fileList");
  ul.innerHTML = "";
  for (const f of files) {
    const li = document.createElement("li");
    li.className = "file-row";
    const meta = `${fmtSize(f.size)} · ${f.animated ? `动图 ${f.frames} 帧` : "静态图"}` +
      (f.output ? ` · 已保存到 ${f.output}` : "");
    /* 目标格式：转换后显示实际使用的格式，未转换时显示当前所选格式 */
    const selLabel = (targets.find(t => t.key === selectedKey) || {}).label || "";
    const tgtLabel = (f.target_label || selLabel).split("（")[0].trim();
    li.innerHTML = `
      <span class="thumb"><img loading="lazy" src="/api/thumb/${f.id}" alt=""></span>
      <span class="f-info">
        <span class="f-name" title="${esc(f.name)}">${esc(f.name)}</span><br>
        <span class="f-meta" title="${esc(meta)}">${esc(meta)}</span>
      </span>
      ${tgtLabel ? `<span class="chip target" title="转换目标格式">→ ${esc(tgtLabel)}</span>` : ""}
      <span class="chip ${f.status}" title="${f.error ? esc(f.error) : STATUS_TEXT[f.status] || f.status}">
        ${STATUS_TEXT[f.status] || f.status}</span>`;
    if (f.status !== "running") {
      const rm = document.createElement("button");
      rm.className = "f-remove"; rm.type = "button"; rm.title = "移除"; rm.textContent = "✕";
      rm.addEventListener("click", () => removeFile(f.id));
      li.appendChild(rm);
    }
    ul.appendChild(li);
  }

  /* 底栏 */
  const total = files.length;
  const totalSize = files.reduce((s, f) => s + f.size, 0);
  $("abCount").textContent = `${total} 个文件`;
  $("abSize").textContent = fmtSize(totalSize);
  $("listCount").textContent = `（${total}）`;
  const running = !!(job && job.running);
  const convertible = (counts.pending || 0) + (counts.error || 0);
  const btn = $("btnConvert");
  btn.disabled = running || convertible === 0;
  btn.textContent = running ? "转换中…" : (convertible > 0 || !total ? "开始转换" : "全部已完成");
  $("btnClear").disabled = running;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function refresh() {
  try {
    renderStatus(await api("/api/status"));
  } catch (e) { /* 本地轮询失败静默 */ }
}

/* ---------- 添加文件 ---------- */

async function uploadFiles(fileList) {
  const files = [...fileList].filter(f => f.size > 0);
  if (!files.length) return;
  /* 分批上传：大批量文件单次请求容易超过服务端请求体上限（413），也便于展示进度。
     同时按个数（10 个）与字节（200MB）双限制分批，兼容超大文件。 */
  const MAX_FILES = 10;
  const MAX_BYTES = 200 * 1024 * 1024;
  let added = 0, sent = 0, lastErr = null;
  const sendPart = async (batch) => {
    toast(`正在添加 ${sent + batch.length} / ${files.length} 个文件…`);
    const fd = new FormData();
    batch.forEach(f => fd.append("files", f, f.name));
    try {
      const d = await api("/api/upload", { method: "POST", body: fd });
      added += d.added || 0;
      refresh(); /* 边传边刷新，大列表渐进出现 */
    } catch (e) {
      lastErr = e.message;
    }
    sent += batch.length;
  };
  let part = [], partBytes = 0;
  for (const f of files) {
    if (part.length && (part.length >= MAX_FILES || partBytes + f.size > MAX_BYTES)) {
      await sendPart(part);
      part = []; partBytes = 0;
    }
    part.push(f);
    partBytes += f.size;
  }
  if (part.length) await sendPart(part);
  if (added) {
    toast(`已添加 ${added} 个文件` + (lastErr ? `（部分批次失败：${lastErr}）` : ""));
  } else {
    toast(lastErr ? `添加失败：${lastErr}` : "没有可转换的文件（受支持：webp / png / jpg / bmp / tiff / gif）", true);
  }
  refresh();
}

async function addPath() {
  const val = $("pathInput").value.trim();
  if (!val) return;
  try {
    const d = await api("/api/add-paths", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paths: [val] }),
    });
    if (d.added) { toast(`已添加 ${d.added} 个文件` + (d.skipped ? `，跳过 ${d.skipped} 个` : "")); $("pathInput").value = ""; }
    else toast("没有找到可转换的文件（检查路径与格式）", true);
    refresh();
  } catch (e) { toast(e.message, true); }
}

async function removeFile(id) {
  await api(`/api/remove/${id}`, { method: "POST" });
  refresh();
}

/* ---------- 拖拽（含文件夹递归） ---------- */

async function walkEntry(entry) {
  if (entry.isFile) return [await new Promise(res => entry.file(res, () => res(null)))].filter(Boolean);
  const reader = entry.createReader();
  const out = [];
  for (;;) {
    const batch = await new Promise(res => reader.readEntries(res, () => res([])));
    if (!batch.length) break;
    for (const e of batch) out.push(...await walkEntry(e));
  }
  return out;
}

async function filesFromDrop(dt) {
  const items = dt.items ? [...dt.items] : [];
  if (items.length && typeof items[0].webkitGetAsEntry === "function") {
    const entries = items.map(i => i.webkitGetAsEntry()).filter(Boolean);
    /* 某些拖拽来源（合成事件、部分应用）拿不到 entry，需回退到 files */
    if (entries.length) {
      const lists = await Promise.all(entries.map(walkEntry));
      return lists.flat();
    }
  }
  return [...dt.files];
}

/* ---------- 转换 ---------- */

async function startConvert() {
  const mode = document.querySelector('input[name="outmode"]:checked').value;
  const outDir = mode === "custom" ? $("outDir").value.trim() : "";
  if (mode === "custom" && !outDir) { toast("请填写统一的输出目录", true); return; }
  try {
    const d = await api("/api/convert", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: selectedKey, outputMode: mode, outputDir: outDir }),
    });
    toast(`开始转换，共 ${d.total} 个文件`);
    refresh();
  } catch (e) { toast(e.message, true); }
}

async function openOutput() {
  try { await api("/api/open-output", { method: "POST" }); }
  catch (e) { toast(e.message, true); }
}

async function clearAll() {
  try {
    await api("/api/clear", { method: "POST" });
    $("banner").hidden = true;
    refresh();
  } catch (e) { toast(e.message, true); }
}

async function pickFolder() {
  try {
    const d = await api("/api/pick-folder", { method: "POST" });
    if (d.folder) $("outDir").value = d.folder;
  } catch (e) { toast(e.message, true); }
}

/* ---------- 初始化 ---------- */

async function init() {
  const d = await api("/api/formats");
  targets = d.targets;
  const first = targets.find(t => t.available);
  selectedKey = first ? first.key : null;
  renderFormats();

  const st = await api("/api/status");
  $("fileInput").accept = (st.supportedExts || []).join(",");
  renderStatus(st);

  /* 事件绑定 */
  $("btnPick").addEventListener("click", () => $("fileInput").click());
  $("fileInput").addEventListener("change", e => { uploadFiles(e.target.files); e.target.value = ""; });
  $("btnPath").addEventListener("click", () => { $("pathRow").hidden = false; $("pathInput").focus(); });
  $("btnPathGo").addEventListener("click", addPath);
  $("pathInput").addEventListener("keydown", e => { if (e.key === "Enter") addPath(); });

  const dz = $("dropzone");
  dz.addEventListener("click", e => { if (e.target === dz || e.target.classList.contains("dz-icon") || e.target.classList.contains("dz-main") || e.target.classList.contains("dz-sub")) $("fileInput").click(); });
  ["dragenter", "dragover"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add("dragover"); }));
  ["dragleave", "drop"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove("dragover"); }));
  dz.addEventListener("drop", async e => { uploadFiles(await filesFromDrop(e.dataTransfer)); });

  /* 整页防止浏览器直接打开文件 */
  window.addEventListener("dragover", e => e.preventDefault());
  window.addEventListener("drop", e => e.preventDefault());

  $("btnConvert").addEventListener("click", startConvert);
  $("btnClear").addEventListener("click", clearAll);
  $("btnOpenOut").addEventListener("click", openOutput);
  $("btnBrowse").addEventListener("click", pickFolder);

  document.querySelectorAll('input[name="outmode"]').forEach(r =>
    r.addEventListener("change", () => {
      const custom = document.querySelector('input[name="outmode"]:checked').value === "custom";
      $("outDir").disabled = !custom;
      $("btnBrowse").disabled = !custom;
    }));

  setInterval(refresh, 800);

  /* 心跳：所有页面关闭后，服务检测不到心跳会自动退出 */
  const beat = () => fetch("/api/heartbeat", { method: "POST" }).catch(() => {});
  beat();
  setInterval(beat, 2000);
}

init().catch(e => toast("初始化失败：" + e.message, true));
