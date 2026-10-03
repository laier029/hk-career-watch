(function () {
  "use strict";
  const core = window.JobCore, data = window.JOB_DATA;
  const key = "hk-career-watch:read:v1:" + location.pathname.replace(/index\.html$/, "");
  const sections = [["employer", "雇主清单"], ["external", "外部发现"], ["read", "已读岗位"]];
  const categories = [["daily", "日常实习"], ["summer", "暑期实习"], ["graduate", "毕业项目"]];
  let section = "employer", category = "daily", reads = {};
  const $ = id => document.getElementById(id);
  const today = () => new Intl.DateTimeFormat("en-CA", {timeZone: "Asia/Hong_Kong", year:"numeric", month:"2-digit", day:"2-digit"}).format(new Date());
  const node = (tag, text, className) => {
    const result = document.createElement(tag);
    if (text !== undefined) result.textContent = text;
    if (className) result.className = className;
    return result;
  };
  function error(message) { $("error").textContent = message; $("error").hidden = !message; }
  function loadReads() {
    try { const stored = localStorage.getItem(key); reads = stored ? core.parseReadState(JSON.parse(stored)) : {}; return true; }
    catch { error("无法读取已读记录。浏览器可能禁止本地存储，或记录已损坏；请使用备份文件恢复，不要清空原记录。"); return false; }
  }
  function saveReads(next) {
    try {
      localStorage.setItem(key, JSON.stringify({version:1, read:next}));
      reads = next;
      error("");
      return true;
    } catch { error("浏览器未能保存记录，本次操作未生效。请检查存储权限或空间。"); return false; }
  }
  function link(text, url) {
    const safe = core.safeUrl(url);
    if (!safe) return node("span", "链接无效");
    const a = node("a", text); a.href = safe; a.target = "_blank"; a.rel = "noopener noreferrer"; return a;
  }
  function tabs(target, choices, selected, change, count) {
    const fragment = document.createDocumentFragment();
    for (const [value, label] of choices) {
      const button = node("button", label);
      button.type = "button"; button.setAttribute("aria-pressed", String(value === selected));
      button.append(node("span", String(count(value)), "count"));
      button.addEventListener("click", () => change(value));
      fragment.append(button);
    }
    $(target).replaceChildren(fragment);
  }
  function render(message) {
    const date = today();
    const match = (job, source = section) => core.visible(job, source, reads, date);
    tabs("sections", sections, section, value => { section=value; render(); }, value => data.jobs.filter(j => match(j,value)).length);
    tabs("categories", categories, category, value => { category=value; render(); }, value => data.jobs.filter(j => match(j) && j.category === value).length);
    $("heading").textContent = sections.find(s => s[0] === section)[1];
    $("description").textContent = section === "employer" ? data.employer_count + " 家关注雇主 · 官方招聘页与公开接口" : section === "external" ? "Workopia 香港清单 · JobSpy（Indeed / LinkedIn）" : "已读记录保存在本浏览器；岗位更新不会重置。";
    const jobs = data.jobs.filter(j => match(j) && j.category === category).sort((a,b) => (b.posted || b.first_seen || "").localeCompare(a.posted || a.first_seen || "") || a.company.localeCompare(b.company));
    $("notice").textContent = message || jobs.length + " 个岗位" + (category === "graduate" ? " · 申请资格以各公司要求为准" : "");
    const fragment = document.createDocumentFragment();
    for (const job of jobs) {
      const tr = document.createElement("tr");
      tr.append(node("td", job.company, "company"));
      const title = node("td", undefined, "title");
      title.append(node("div", job.title, "job-title"), node("div", job.source, "meta"));
      if (job.note) title.append(node("div", job.note, "note"));
      if (job.last_seen && job.last_seen !== data.updated_at) title.append(node("div", "本轮未重新发现，申请前请确认开放状态", "note"));
      if (core.isExpired(job, date)) title.append(node("div", "已过截止日期", "note"));
      tr.append(title);
      for (const [field,label] of [["posted","发布"],["deadline","截止"]]) {
        const td = node("td", job[field] || "未注明", "date"); td.dataset.label=label; tr.append(td);
      }
      const urlCell = node("td"); urlCell.append(link("查看岗位 ↗",job.url)); tr.append(urlCell);
      const action = node("td"), isRead = Boolean(reads[job.id]);
      const button = node("button", isRead ? "恢复未读" : "✓ 已读", "read-button");
      button.setAttribute("aria-label", (isRead ? "恢复未读：" : "标为已读：") + job.title);
      button.addEventListener("click", () => {
        // Merge the latest other-tab state before changing this single record.
        if (!loadReads()) return;
        const next = {...reads};
        if (isRead) delete next[job.id]; else next[job.id] = new Date().toISOString();
        if (saveReads(next)) render(isRead ? "已恢复至原分类" : "已移入已读岗位");
      });
      action.append(button); tr.append(action); fragment.append(tr);
    }
    $("jobs").replaceChildren(fragment); $("empty").hidden = jobs.length > 0;
  }
  if (!data || !Array.isArray(data.jobs) || !core) { error("岗位文件未正确加载，请刷新；离线使用时请保留整个网页文件夹。"); return; }
  loadReads();
  $("stamp").textContent = "最近检查 " + new Date(data.updated_at).toLocaleString("zh-CN", {timeZone:"Asia/Hong_Kong", hour12:false});
  if (Date.now() - Date.parse(data.updated_at) > 9 * 86400000) error("超过 9 天未更新。请检查 GitHub Actions 是否失败或暂停；当前仍展示上次成功保存的数据。");
  const labels = {ok:"已检查", unchanged:"未变化", partial:"部分覆盖", error:"未能检查", blocked:"访问受限", empty:"本次无结果"};
  const issues = data.sources.filter(s => ["error","blocked","partial"].includes(s.status));
  $("source-summary").textContent = "筛选条件与更新记录 · " + issues.length + " 个来源需留意";
  for (const source of data.sources) {
    const row = node("div", undefined, "source");
    row.append(link(source.name, source.url), node("span", labels[source.status] || source.status, ["error","blocked"].includes(source.status) ? "failed" : ""), node("span", source.message));
    $("sources").append(row);
  }
  $("export").addEventListener("click", () => {
    if (!loadReads()) return;
    const blob = new Blob([JSON.stringify({version:1, read:reads},null,2)], {type:"application/json"});
    const url = URL.createObjectURL(blob), a = node("a"); a.href=url; a.download="hk-jobs-read-"+today()+".json";
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    $("notice").textContent = "已导出；此文件是私人已读记录，不要提交到公开仓库。";
  });
  $("import").addEventListener("click", () => $("import-file").click());
  $("import-file").addEventListener("change", async event => {
    const file = event.target.files[0]; if (!file) return;
    try {
      if (file.size > 5 * 1024 * 1024) throw new Error("文件超过 5 MB，请选择已读记录 JSON。");
      const incoming = core.parseReadState(JSON.parse(await file.text()));
      loadReads();
      if (saveReads({...reads,...incoming})) render("已合并导入 " + Object.keys(incoming).length + " 条已读记录");
    } catch (e) { error("未导入：" + e.message); }
    finally { event.target.value=""; }
  });
  window.addEventListener("storage", event => { if (event.key === key || event.key === null) { loadReads(); render(); } });
  render();
})();
