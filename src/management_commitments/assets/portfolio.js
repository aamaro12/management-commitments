"use strict";
const DATA = JSON.parse(document.getElementById("portfolio-data").textContent);
const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
function safePath(p) {
  return typeof p === "string" && p.length > 0 && !p.includes(":") && !p.startsWith("//") && !p.includes("\\")
    ? p
    : null;
}
function draw() {
  const query = $("search").value.trim().toLowerCase(),
    coverage = $("coverage-filter").value;
  const rows = DATA.reports.filter(
    (r) =>
      (r.company.name + " " + r.company.id + " " + r.summary).toLowerCase().includes(query) &&
      (coverage === "all" || (coverage === "calls" ? r.transcripts > 0 : r.transcripts === 0)),
  );
  rows.sort(
    $("sort").value === "attention"
      ? (a, b) => b.attention - a.attention || a.company.name.localeCompare(b.company.name)
      : (a, b) => a.company.name.localeCompare(b.company.name),
  );
  $("companies").innerHTML = rows
    .map(
      (r) =>
        `<tr data-ticker="${esc(r.company.id)}"><td><a class="company-link" href="${esc(safePath(r.href) || "#")}">${esc(r.company.name)}</a><span class="ticker">${esc(r.company.id)}</span><p class="finding">${esc(r.summary)}</p>${r.blocked ? '<span class="blocked-label">Blocked checks need correction</span>' : ""}</td><td class="number-cell">${esc(r.tracked)}</td><td class="number-cell">${esc(r.compared)}</td><td class="number-cell">${esc(r.attention)}</td><td><span class="coverage-label">${r.transcripts ? esc(r.transcripts) + " / " + esc(r.quarters) + " quarters" : "Release only"}</span></td></tr>`,
    )
    .join("");
  $("visible-count").textContent = rows.length + " companies";
  $("empty").hidden = rows.length > 0;
  $("clear").hidden = !query && coverage === "all";
}
$("stats").innerHTML = [
  { value: DATA.totals.companies, label: "Companies" },
  { value: DATA.totals.tracked, label: "Statements tracked" },
  { value: DATA.totals.compared, label: "Numerical comparisons" },
  { value: DATA.totals.transcripts, label: "Quarterly transcripts" },
]
  .map((s) => `<div class="stat"><strong>${esc(s.value)}</strong><label>${esc(s.label)}</label></div>`)
  .join("");
$("dates").textContent = "Historical review dates: " + DATA.review_dates.join(" · ");
$("search").addEventListener("input", draw);
$("coverage-filter").addEventListener("change", draw);
$("sort").addEventListener("change", draw);
$("clear").addEventListener("click", () => {
  $("search").value = "";
  $("coverage-filter").value = "all";
  draw();
});
draw();
