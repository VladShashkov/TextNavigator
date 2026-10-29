// TextNavigator — клиент. Вся логика извлечения на сервере; здесь только показ.
"use strict";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const ruDate = (iso) => iso ? iso.split("-").reverse().join(".") : "";
const FIELD = { amount: "Сумма", deadline: "Срок поставки", supplier: "Поставщик" };
const STATUS = { ok: "", no_data: "нет данных", needs_review: "требует проверки" };

const files = new Map();   // имя → File; повторная загрузка с тем же именем заменяет файл
let data = null;

// ---------- загрузка ----------
const drop = $("#drop");
$("#files").addEventListener("change", (e) => addFiles(e.target.files));
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); addFiles(e.dataTransfer.files); });
$("#checkDate").addEventListener("change", () => files.size && analyze());

function addFiles(list) {
  for (const f of list) files.set(f.name, f);
  $("#files").value = "";
  analyze();
}

async function analyze() {
  const fd = new FormData();
  for (const f of files.values()) fd.append("files", f, f.name);
  fd.append("check_date", $("#checkDate").value);
  showError("");
  try {
    const r = await fetch("/api/analyze", { method: "POST", body: fd });
    const j = await r.json();
    if (!r.ok) return showError(j.error || "Ошибка обработки");
    data = j;
    render();
  } catch (e) { showError("Сервер недоступен: " + e.message); }
}

function showError(msg) { $("#error").hidden = !msg; $("#error").textContent = msg; }

// ---------- таблица ----------
function render() {
  $("#loaded").innerHTML = `Загружено файлов: ${files.size} · <a href="#" id="clear">очистить</a>`;
  $("#clear").onclick = (e) => { e.preventDefault(); files.clear(); data = null; location.reload(); };
  ["#resultBlock", "#askBlock", "#docsBlock"].forEach((s) => ($(s).hidden = false));

  const tb = $("#table tbody");
  tb.innerHTML = "";
  data.contracts.forEach((c, i) => {
    const tr = document.createElement("tr");
    tr.dataset.number = c.number;
    const props = ["amount", "deadline"].flatMap((k) => c[k].proposals.map((p, j) =>
      `<span class="chip prop" data-c="${i}" data-f="${k}" data-p="${j}">${FIELD[k].toLowerCase()}: ${esc(p.display)}</span>`));
    const notes = [...c.issues, ...["supplier", "amount", "deadline"].flatMap((k) =>
      c[k].status === "needs_review" ? c[k].notes.map((n) => `${FIELD[k]}: ${n}`) : [])];
    tr.innerHTML = `
      <td><b>${esc(c.number)}</b></td>
      <td>${cell(c, i, "supplier")}</td>
      <td class="num">${cell(c, i, "amount")}</td>
      <td class="num">${cell(c, i, "deadline")}</td>
      <td>${props.join("") || '<span class="muted">—</span>'}</td>`;
    tr.firstElementChild.innerHTML += c.needs_review ? '<br><span class="chip needs_review">требует проверки</span>' : "";
    tb.appendChild(tr);
    if (c.needs_review) {
      const sub = document.createElement("tr");
      sub.className = "issue-row"; sub.dataset.number = c.number;
      sub.innerHTML = `<td></td><td colspan="4"><ul class="issues">${notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul></td>`;
      tb.appendChild(sub);
    }
  });
  tb.querySelectorAll(".val").forEach((el) => el.onclick = () => openField(+el.dataset.c, el.dataset.f));
  tb.querySelectorAll(".prop").forEach((el) => el.onclick = () => openProposal(+el.dataset.c, el.dataset.f, +el.dataset.p));

  $("#unassigned").innerHTML = data.unassigned.length
    ? `<div class="error">Не удалось связать с договором: ${data.unassigned.map((u) =>
        `<b>${esc(u.file)}</b> (${esc(u.problems.join("; "))})`).join(", ")}</div>` : "";

  const sel = $("#askContract");
  const prev = sel.value;
  sel.innerHTML = data.contracts.map((c) => `<option>${esc(c.number)}</option>`).join("");
  if (prev) sel.value = prev;

  const docRows = [];
  for (const c of data.contracts) for (const d of c.documents)
    docRows.push(`<tr><td><a href="#" data-file="${esc(d.file)}">${esc(d.file)}</a></td><td>${esc(d.title)}<br><span class="muted">${esc(d.status_text)}</span></td>
      <td>${esc(c.number)}</td><td>${d.applied ? "✓ " : "— "}${esc(d.role)}</td></tr>`);
  for (const u of data.unassigned)
    docRows.push(`<tr><td><a href="#" data-file="${esc(u.file)}">${esc(u.file)}</a></td><td>${esc(u.title || "?")}</td><td>—</td><td>${esc(u.problems.join("; "))}</td></tr>`);
  $(".docs tbody").innerHTML = docRows.join("");
  $(".docs tbody").querySelectorAll("a").forEach((a) => a.onclick = (e) => { e.preventDefault(); openDoc(a.dataset.file); });

  if (data.validation_errors.length) showError("Внутренняя проверка цитат: " + data.validation_errors.join("; "));
}

function cell(c, i, k) {
  const f = c[k];
  const val = f.value !== null && f.value !== undefined;
  let html = val || f.evidence
    ? `<span class="val" data-c="${i}" data-f="${k}">${esc(f.display)}</span>`
    : `<span class="chip no_data">нет данных</span>`;
  if (val && f.status === "needs_review") html += ` <span class="chip needs_review">?</span>`;
  if (!val && f.evidence) html = `<span class="val chip no_data" data-c="${i}" data-f="${k}">нет данных</span>`;
  if (f.changed_by) html += `<span class="changed">изменено: ${esc(f.changed_by.split(" (")[0])}</span>`;
  return html;
}

// ---------- основание и исходный текст ----------
function evLink(ev) {
  return `<a data-ev='${esc(JSON.stringify(ev))}'>${esc(ev.file)}, ${esc(ev.para_label)}</a>`;
}

function openField(ci, k) {
  const c = data.contracts[ci], f = c[k];
  let html = `<p><b>${esc(c.number)} · ${FIELD[k]}: ${esc(f.display)}</b>
    ${f.status !== "ok" ? `<span class="chip ${f.status}">${STATUS[f.status]}</span>` : ""}</p>`;
  if (f.history.length > 1) {
    html += `<div class="muted small">История изменений:</div>` + f.history.map((h, n) =>
      `<div class="step">${n ? "→ " : ""}${esc(h.display)} — ${esc(h.doc.split(" (")[0])}, ${evLink(h.evidence)}</div>`).join("");
  }
  if (f.evidence) html += `<blockquote>${esc(f.evidence.quote)}</blockquote>`;
  html += f.notes.map((n) => `<div class="muted small">· ${esc(n)}</div>`).join("");
  if (f.proposals.length) html += `<div class="muted small" style="margin-top:6px">Не согласовано (не меняет условия):</div>` +
    f.proposals.map((p) => `<div class="step"><span class="chip prop">${esc(p.display)}</span> ${esc(p.doc_title)} — ${esc(p.reason)}, ${evLink(p.evidence)}</div>`).join("");
  showSource(f.evidence, html);
  markActive(ci, k);
}

function openProposal(ci, k, j) {
  const c = data.contracts[ci], p = c[k].proposals[j];
  showSource(p.evidence, `<p><b>${esc(c.number)} · предложение: ${FIELD[k].toLowerCase()} ${esc(p.display)}</b>
    <span class="chip prop">не согласовано</span></p><div>${esc(p.doc_title)}: ${esc(p.reason)}</div>
    <blockquote>${esc(p.evidence.quote)}</blockquote>
    <div class="muted small">Действует: ${esc(c[k].display)}</div>`);
}

function openDoc(file) {
  const d = data.documents.find((x) => x.filename === file);
  showSource(null, `<p><b>${esc(d.title || d.filename)}</b></p><div class="muted small">${esc(d.status_text || "")}</div>`, file);
}

function showSource(ev, basisHtml, file) {
  const fname = ev ? ev.file : file;
  const d = data.documents.find((x) => x.filename === fname);
  $("#source").hidden = false;
  document.body.classList.add("with-source");
  $("#sourceMeta").innerHTML = `<b>${esc(fname)}</b>${ev ? ` · ${esc(ev.para_label)}` : ""}`;
  $("#basis").innerHTML = basisHtml;
  $("#basis").querySelectorAll("a[data-ev]").forEach((a) => a.onclick = () => {
    const e = JSON.parse(a.dataset.ev);
    showSource(e, $("#basis").innerHTML);
  });
  $("#docText").innerHTML = d.paragraphs.map((p) => {
    let t = esc(d.text.slice(p.start, p.end));
    const hit = ev && p.id === ev.para_id;
    if (hit) {
      const a = ev.hl_start - p.start, b = ev.hl_end - p.start, raw = d.text.slice(p.start, p.end);
      t = esc(raw.slice(0, a)) + "<mark>" + esc(raw.slice(a, b)) + "</mark>" + esc(raw.slice(b));
    }
    return `<div class="para${hit ? " hl" : ""}" id="${p.id}"><span class="ln">${p.line}</span><span>${t}</span></div>`;
  }).join("");
  if (ev) document.getElementById(ev.para_id)?.scrollIntoView({ block: "center" });
}

function markActive(ci, k) {
  document.querySelectorAll(".val.active").forEach((e) => e.classList.remove("active"));
  document.querySelector(`.val[data-c="${ci}"][data-f="${k}"]`)?.classList.add("active");
}

$("#closeSource").onclick = () => { $("#source").hidden = true; document.body.classList.remove("with-source"); };

// ---------- вопросы ----------
$("#askField").onsubmit = (e) => { e.preventDefault(); answerField($("#askContract").value, $("#askWhat").value); };
$("#askBefore").onsubmit = (e) => { e.preventDefault(); answerBefore($("#beforeDate").value); };

document.querySelectorAll(".quick button").forEach((b) => b.onclick = () => {
  const q = { 1: ["STN-101", "deadline"], 2: ["STN-102", "amount"], 3: ["STN-103", "amount"] }[b.dataset.q];
  if (q) { $("#askContract").value = q[0]; $("#askWhat").value = q[1]; answerField(...q); }
  else { $("#beforeDate").value = "2026-04-01"; answerBefore("2026-04-01"); }
});

function answer(html) { $("#answer").hidden = false; $("#answer").innerHTML = html; bindAnswerLinks(); }

function bindAnswerLinks() {
  $("#answer").querySelectorAll("a[data-open]").forEach((a) => a.onclick = () => {
    const [ci, k, j] = a.dataset.open.split(":");
    j === undefined ? openField(+ci, k) : openProposal(+ci, k, +j);
  });
}

function answerField(number, k) {
  focusRows([number]);
  const ci = data.contracts.findIndex((c) => c.number === number);
  const head = `<p class="q">${FIELD[k]} по договору ${esc(number)} на ${ruDate(data.check_date)}</p>`;
  if (ci < 0) return answer(head + `<p><b>Нет данных:</b> договор ${esc(number)} не найден среди загруженных документов.</p>`);
  const c = data.contracts[ci], f = c[k];
  let html = head;
  if (f.status === "ok") html += `<p><b>${esc(f.display)}</b></p>`;
  else if (f.status === "no_data") html += `<p><b>Нет данных.</b> ${esc(f.notes.join(" "))}</p>`;
  else html += `<p><b>Требует проверки.</b> ${f.value != null ? `Найденное значение: ${esc(f.display)}. ` : ""}${esc([...f.notes, ...c.issues].join(" "))}</p>`;
  if (f.evidence) html += `<p>Основание: <a data-open="${ci}:${k}">${esc(f.evidence.file)}, ${esc(f.evidence.para_label)}</a></p><blockquote>${esc(f.evidence.quote)}</blockquote>`;
  if (f.changed_by && f.base) html += `<p>Изменено: ${esc(f.changed_by)}. По договору было ${esc(f.base.display)} (${esc(f.base.evidence.file)}, ${esc(f.base.evidence.para_label)}).</p>`;
  if (f.proposals.length) html += `<p>Не согласовано, условия не меняет:</p>` + f.proposals.map((p, j) =>
    `<p>· <a data-open="${ci}:${k}:${j}">${esc(p.display)}</a> — ${esc(p.doc_title)} (${esc(p.doc)}): ${esc(p.reason)}</p>`).join("");
  else if (k !== "supplier") html += `<p class="muted">Несогласованных изменений нет.</p>`;
  answer(html);
}

function answerBefore(iso) {
  const hits = [], unknown = [], otherProps = [];
  data.contracts.forEach((c, ci) => {
    const d = c.deadline;
    if (d.value == null) unknown.push(c);
    else if (d.value < iso) hits.push([c, ci]);
    else if (d.proposals.length) otherProps.push([c, ci]);
  });
  focusRows(hits.map(([c]) => c.number));
  let html = `<p class="q">Поставка раньше ${ruDate(iso)} (по действующим условиям на ${ruDate(data.check_date)})</p>`;
  if (!hits.length) html += `<p><b>Таких договоров нет.</b></p>`;
  hits.forEach(([c, ci]) => {
    const d = c.deadline;
    html += `<p><b>${esc(c.number)}</b> — срок <a data-open="${ci}:deadline">${esc(d.display)}</a>${d.status === "needs_review" ? " (требует проверки)" : ""}. `;
    html += d.proposals.length
      ? `Есть несогласованное изменение срока: ${d.proposals.map((p, j) => `<a data-open="${ci}:deadline:${j}">${esc(p.display)}</a> — ${esc(p.doc_title)} (${esc(p.reason)})`).join("; ")}.</p>`
      : `Несогласованных изменений срока нет.</p>`;
  });
  if (otherProps.length) html += `<p class="muted">Несогласованные изменения срока есть и вне выборки: ${otherProps.map(([c, ci]) =>
    `${esc(c.number)} (действует ${esc(c.deadline.display)}, предложено ${c.deadline.proposals.map((p) => esc(p.display)).join(", ")})`).join("; ")}.</p>`;
  if (unknown.length) html += `<p class="muted">Срок не определён: ${unknown.map((c) => esc(c.number)).join(", ")} — проверить вручную.</p>`;
  answer(html);
}

function focusRows(numbers) {
  document.querySelectorAll("#table tbody tr").forEach((tr) => {
    tr.classList.toggle("focus", numbers.includes(tr.dataset.number));
  });
}
