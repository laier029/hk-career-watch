(function (root) {
  "use strict";
  function parseReadState(value) {
    if (!value || value.version !== 1 || !value.read || typeof value.read !== "object" || Array.isArray(value.read)) throw new Error("不是有效的已读记录文件");
    const entries = Object.entries(value.read);
    if (entries.length > 100000) throw new Error("已读记录过大");
    const result = {};
    for (const [id, date] of entries) {
      if (!/^[a-f0-9]{24}$/.test(id) || typeof date !== "string" || !/^\d{4}-\d{2}-\d{2}T/.test(date) || !Number.isFinite(Date.parse(date))) throw new Error("已读记录格式不正确");
      result[id] = date;
    }
    return result;
  }
  function isExpired(job, today) { return job.state === "expired" || Boolean(job.deadline && job.deadline < today); }
  function visible(job, section, reads, today) {
    return section === "read" ? Boolean(reads[job.id]) : !reads[job.id] && job.origin === section && !isExpired(job, today);
  }
  function safeUrl(value) {
    try { const url = new URL(value); return ["https:", "http:"].includes(url.protocol) ? url.href : null; } catch { return null; }
  }
  const api = {parseReadState, isExpired, visible, safeUrl};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.JobCore = api;
})(typeof window === "undefined" ? globalThis : window);
