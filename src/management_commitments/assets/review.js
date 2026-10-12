"use strict";
const REPORT = JSON.parse(document.getElementById("report-data").textContent);
const LABELS = {
  within_range: "Within guidance",
  above_range: "Above guidance",
  below_range: "Below guidance",
  met: "Target met",
  missed: "Target missed",
  not_due: "Not due yet",
  unresolved: "Evidence missing",
  definition_changed: "Definition changed",
  basis_mismatch: "Basis mismatch",
  conditional: "Conditions unresolved",
  qualitative: "Qualitative review",
  needs_review: "Interpretation pending",
  blocked: "Comparison blocked",
};
const KEY = "management-commitments:" + REPORT.company.id + ":" + REPORT.analysis_sha256;
const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
let decisions = {},
  view = "queue";
try {
  const saved = JSON.parse(localStorage.getItem(KEY) || "{}");
  decisions = saved && typeof saved === "object" && !Array.isArray(saved) ? saved : {};
} catch (_) {}
const safeURL = (u) => {
  try {
    const x = new URL(u);
    return x.protocol === "https:" && !x.username && !x.password ? x.href : null;
  } catch (_) {
    return null;
  }
};
function link(url, label) {
  const u = safeURL(url);
  return u
    ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`
    : esc(label);
}
function tone(status) {
  return ["blocked", "missed"].includes(status)
    ? "red"
    : ["within_range", "met"].includes(status)
      ? "green"
      : "amber";
}
function number(value) {
  if (value === undefined || value === null) return "n/a";
  return String(value).replace(/(\.\d*?[1-9])0+$|\.0+$/, "$1");
}
function unit(t) {
  return t?.unit === "percent"
    ? "%"
    : t?.unit === "percentage_points"
      ? "pp"
      : ["USD", "EUR", "GBP"].includes(t?.unit)
        ? t.unit +
          (t.scale && t.scale !== "1"
            ? " " + ({ billion: "bn", million: "m", thousand: "k" }[t.scale] || t.scale)
            : "")
        : t?.unit || "";
}
function targetText(t) {
  if (!t) return "No numerical target";
  const end = unit(t);
  if (t.operator === "tolerance") {
    const tol = t.tolerance;
    const suffix =
      tol.type === "relative_percent"
        ? "%"
        : tol.type === "basis_points"
          ? " bp"
          : " " + unit({ ...t, scale: tol.scale || "1" });
    return `${number(t.center)} ${end} ± ${number(tol.value)}${suffix}`;
  }
  if (t.operator === "range") return `${number(t.low)} to ${number(t.high)}${end === "%" ? "%" : " " + end}`;
  return `${{ at_least: "≥ ", at_most: "≤ ", greater_than: "> ", less_than: "< " }[t.operator] || ""}${number(t.low ?? t.high)} ${end}`;
}
function evidence(refs) {
  if (!refs.length) return '<p class="method">No result evidence was linked to this assessment.</p>';
  return refs
    .map(
      (r) =>
        `<div class="evidence"><blockquote>“${esc(r.quote)}”</blockquote><div class="source-link">${link(r.url, r.title)}</div><div class="source-date">${r.role ? "Context · " : ""}${esc(r.published_at)}${r.publication_basis?.includes("unverified") ? " · Date proxy" : ""}</div><details><summary>Full context and source details</summary><div class="locator">${esc(r.source_id)} / ${esc(r.block_id)}</div><p class="context-text">${esc(r.text)}</p><p class="context-text">${esc(JSON.stringify(r.context))}</p><p class="context-text">Publication basis: ${esc(r.publication_basis || "unverified")}. Coverage: ${esc(r.completeness)}. ${esc(r.warnings.join("; "))}</p></details></div>`,
    )
    .join("");
}
function chosen(c) {
  const d = decisions[c.id];
  return d && ["pending", "accepted", "rejected", "correction_requested"].includes(d.decision)
    ? { decision: d.decision, note: typeof d.note === "string" ? d.note : "" }
    : { decision: c.analyst_decision || "pending", note: c.analyst_note || "" };
}
function store() {
  try {
    localStorage.setItem(KEY, JSON.stringify(decisions));
  } catch (_) {
    toast("Browser storage unavailable. Export your review to keep decisions.");
  }
}
function toast(s) {
  $("toast").textContent = s;
  $("toast").hidden = false;
  setTimeout(() => ($("toast").hidden = true), 4500);
}
function assessmentLabel(c) {
  return c.status === "conditional" && c.condition_assessment?.met === false
    ? "Condition not met"
    : LABELS[c.status] || c.status;
}
function needsAttention(c) {
  return (
    [
      "blocked",
      "below_range",
      "missed",
      "definition_changed",
      "basis_mismatch",
      "conditional",
      "unresolved",
      "needs_review",
    ].includes(c.status) || c.updates.length > 0
  );
}
function card(c, i) {
  const d = chosen(c),
    calc = c.calculation,
    t = c.target;
  const actual = calc
    ? number(calc.actual_in_target_scale) + " " + unit(t)
    : c.observation
      ? number(c.observation.value) + " " + unit(c.observation)
      : "n/a";
  const delta = calc?.gap_to_range ?? calc?.gap_to_bound;
  const gap =
    delta === undefined
      ? "n/a"
      : number(delta) + " " + (calc.gap_unit === "percentage_points" ? "pp" : unit(t));
  const issues = c.flags.filter(
    (f) => !f.includes("source coverage") && !f.startsWith("No numerical pass/fail"),
  );
  return `<article class="card" data-id="${esc(c.id)}"><div class="card-head"><div class="card-title-row"><div><h3>${esc(c.title)}</h3><div class="card-topic">${esc(c.topic)} · ${esc(t?.period?.label || "Qualitative statement")}${t?.basis ? " · " + esc(t.basis.replaceAll("_", " ")) : ""}</div></div><span class="pill ${tone(c.status)}">${esc(assessmentLabel(c))}</span></div><div class="row-bottom"><div class="comparison"><div><small>Earlier target</small><strong>${esc(targetText(t))}</strong></div><div><small>${calc ? "Comparable actual" : "Later disclosure"}</small><strong>${esc(actual)}</strong>${c.observation && !calc ? `<em>${c.status === "conditional" ? "Condition unverified" : "Not comparable"}</em>` : ""}</div>${calc ? `<div><small>${calc.gap_to_range !== undefined ? "Gap outside range" : "Gap to target"}</small><strong>${esc(gap)}</strong></div>` : ""}</div><button class="expand" aria-expanded="false" aria-controls="detail-${esc(c.id)}" aria-label="View evidence for ${esc(c.title)}">View evidence</button></div></div>
  <div class="detail" id="detail-${esc(c.id)}" hidden><p class="rationale">${esc(c.importance_rationale)}</p>${c.question ? `<div class="question"><b>Next question</b>${esc(c.question)}</div>` : ""}${issues.length ? `<ul class="flags">${issues.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : ""}<div class="detail-grid"><div><h4>Earlier statement</h4>${evidence(c.evidence)}</div><div><h4>Later disclosure</h4>${evidence(c.result_evidence)}</div></div>${c.updates.length ? `<div class="updates"><h4>Changes in wording</h4>${c.updates.map((u) => `<div class="update"><p>${esc(u.interpretation || u.type.replaceAll("_", " "))}</p>${evidence(u.evidence)}</div>`).join("")}</div>` : ""}${c.conditions.length ? `<p class="rationale">Conditions: ${esc(c.conditions.join("; "))}</p>` : ""}${c.condition_assessment ? `<div class="updates"><h4>Condition evidence</h4><p class="rationale">${esc(c.condition_assessment.notes || "Condition status is unknown.")}</p>${evidence(c.condition_assessment.evidence || [])}</div>` : ""}<details class="method-details"><summary>Definition, calculation and review notes</summary><p class="method">Definition: ${esc(t?.definition || "Qualitative statement")}<br>Basis: ${esc(t?.basis || "Not numerically tested")}<br>Interpretation by ${esc(c.semantic_review?.reviewer || "unreviewed")}: ${esc(c.semantic_review?.notes || "Meaning and mapping need review.")}<br>Materiality ${esc(c.materiality)}/5, assigned by the reviewer.</p>${calc ? `<div class="calculation">${esc(JSON.stringify(calc, null, 2))}</div>` : ""}${c.flags.length ? `<ul>${c.flags.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : ""}</details><div class="review-controls"><label class="review-label" for="decision-${esc(c.id)}">Your assessment</label><select class="review-select" id="decision-${esc(c.id)}"><option value="pending">Not reviewed</option><option value="accepted">Accept</option><option value="correction_requested">Request correction</option><option value="rejected">Reject</option></select></div><div class="review-note"><label for="note-${esc(c.id)}">Note: required for corrections or rejection</label><textarea id="note-${esc(c.id)}" maxlength="2000" placeholder="What needs checking?">${esc(d.note)}</textarea></div></div></article>`;
}
function filtered() {
  let rows = REPORT.commitments.slice();
  const q = $("search").value.trim().toLowerCase();
  if (view === "queue") rows = rows.filter((c) => REPORT.top_three.includes(c.id));
  if (view === "attention") rows = rows.filter(needsAttention);
  rows = rows.filter(
    (c) =>
      ($("status-filter").value === "all" || c.status === $("status-filter").value) &&
      ($("topic-filter").value === "all" || c.topic === $("topic-filter").value) &&
      ($("period-filter").value === "all" ||
        (c.target?.period?.label || "Qualitative") === $("period-filter").value) &&
      (!q ||
        [
          c.title,
          c.question,
          c.importance_rationale,
          ...c.evidence.map((r) => r.quote),
          ...c.result_evidence.map((r) => r.quote),
        ]
          .join(" ")
          .toLowerCase()
          .includes(q)),
  );
  if ($("sort").value === "title") rows.sort((a, b) => a.title.localeCompare(b.title));
  if ($("sort").value === "period")
    rows.sort((a, b) => (a.target?.period?.end || "9999").localeCompare(b.target?.period?.end || "9999"));
  return rows;
}
function draw() {
  const rows = filtered();
  $("cards").innerHTML = rows.map(card).join("");
  $("empty").hidden = rows.length !== 0;
  $("visible-count").textContent = `${rows.length} items`;
  $("view-all").hidden = view !== "queue";
  $("clear-filters").hidden =
    !$("search").value &&
    ["status-filter", "topic-filter", "period-filter"].every((id) => $(id).value === "all");
  document.querySelectorAll(".card").forEach((el) => {
    const id = el.dataset.id,
      c = REPORT.commitments.find((c) => c.id === id),
      select = el.querySelector("select"),
      details = el.querySelector(".detail"),
      expand = el.querySelector(".expand");
    select.value = chosen(c).decision;
    expand.addEventListener("click", () => {
      details.hidden = !details.hidden;
      expand.setAttribute("aria-expanded", String(!details.hidden));
      expand.textContent = details.hidden ? "View evidence" : "Hide evidence";
    });
    select.addEventListener("change", () => {
      decisions[id] = { decision: select.value, note: el.querySelector("textarea").value };
      store();
      if (["rejected", "correction_requested"].includes(select.value)) {
        details.hidden = false;
        expand.setAttribute("aria-expanded", "true");
        expand.textContent = "Hide evidence";
        el.querySelector("textarea").focus();
      }
    });
    el.querySelector("textarea").addEventListener("input", (e) => {
      decisions[id] = { decision: select.value, note: e.target.value };
      store();
    });
  });
}
function setView(next) {
  view = next;
  $("research-content").hidden = next === "sources";
  $("source-content").hidden = next !== "sources";
  document
    .querySelectorAll(".nav-button")
    .forEach((b) => b.classList.toggle("active", b.dataset.view === next));
  document
    .querySelectorAll(".nav-button")
    .forEach((b) => b.setAttribute("aria-current", b.dataset.view === next ? "page" : "false"));
  $("view-title").textContent =
    next === "queue" ? "Priority items" : next === "attention" ? "Needs review" : "All commitments";
  $("view-subtitle").textContent =
    next === "queue"
      ? "The most material items to inspect first."
      : next === "attention"
        ? "Changed expectations, mismatches and missing evidence."
        : "Every tracked statement, including open targets.";
  if (next !== "sources") draw();
}
function download(name, value, type = "application/json") {
  const content = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function exportReview() {
  const reviewer = $("reviewer").value.trim();
  if (!reviewer) {
    toast("Enter a reviewer name.");
    return false;
  }
  const ds = REPORT.commitments.map((c) => ({ id: c.id, ...chosen(c) }));
  if (ds.some((d) => ["rejected", "correction_requested"].includes(d.decision) && !d.note.trim())) {
    toast("Add a note to every rejection or correction before exporting.");
    return false;
  }
  download("review-decisions.json", {
    schema_version: 1,
    company: REPORT.company.id,
    analysis_sha256: REPORT.analysis_sha256,
    reviewer,
    exported_at: new Date().toISOString(),
    decisions: ds,
  });
  return true;
}
function init() {
  if (REPORT.mode === "synthetic_demo") document.body.classList.add("demo");
  $("company-chip").innerHTML = esc(REPORT.company.id) + `<small>${esc(REPORT.company.name)}</small>`;
  if (
    typeof REPORT.portfolio_href === "string" &&
    !REPORT.portfolio_href.includes(":") &&
    !REPORT.portfolio_href.startsWith("//") &&
    !REPORT.portfolio_href.includes("\\")
  )
    $("breadcrumbs").innerHTML = `<a href="${esc(REPORT.portfolio_href)}">All companies</a> / Company review`;
  else $("breadcrumbs").textContent = "Company review";
  $("mode-label").textContent =
    REPORT.mode === "synthetic_demo"
      ? "Synthetic demo"
      : REPORT.mode.includes("historical")
        ? "Historical review"
        : "Research";
  $("summary").textContent = REPORT.summary;
  $("as-of").textContent = "As of " + REPORT.as_of;
  $("review-state").textContent = "Source-linked · Python calculations";
  $("queue-count").textContent = REPORT.top_three.length;
  const attention = REPORT.commitments.filter(needsAttention).length;
  const compared = REPORT.commitments.filter((c) => c.calculation).length;
  const transcriptCount = REPORT.coverage.filter((c) => c.transcript === "captured").length;
  $("stats").innerHTML = [
    {
      label: "Commitments tracked",
      value: REPORT.commitments.length,
      note: "Includes qualitative ambitions",
    },
    {
      label: "Worth checking",
      value: attention,
      note: "Gaps, changes and target misses",
      class: "attention",
    },
    { label: "Numerical comparisons", value: compared, note: "Period + definition + basis aligned" },
    {
      label: "Call coverage",
      value: transcriptCount + " / " + REPORT.coverage.length,
      note: "Quarters with an acquired transcript",
    },
  ]
    .map(
      (s) =>
        `<div class="stat ${s.class || ""}"><strong>${esc(s.value)}</strong><label>${esc(s.label)}</label><small>${esc(s.note)}</small></div>`,
    )
    .join("");
  for (const key of Object.keys(REPORT.counts).filter((k) => REPORT.counts[k] > 0)) {
    const o = document.createElement("option");
    o.value = key;
    o.textContent = LABELS[key] || key;
    $("status-filter").append(o);
  }
  for (const [id, values] of [
    ["topic-filter", REPORT.commitments.map((c) => c.topic)],
    ["period-filter", REPORT.commitments.map((c) => c.target?.period?.label || "Qualitative")],
  ])
    for (const value of [...new Set(values)].sort()) {
      const o = document.createElement("option");
      o.value = value;
      o.textContent = value;
      $(id).append(o);
    }
  $("coverage").innerHTML = REPORT.coverage
    .map(
      (c) =>
        `<div class="coverage-card"><h3>${esc(c.period.label)}</h3><span class="pill ${c.transcript === "captured" ? "green" : "amber"}">${c.transcript === "captured" ? "Transcript acquired" : "Transcript not acquired"}</span><p>${esc(c.documents)} documents · ${esc(c.period.start)} to ${esc(c.period.end)}</p></div>`,
    )
    .join("");
  $("source-list").innerHTML = REPORT.documents
    .map(
      (d) =>
        `<div class="source-row"><div>${link(d.url, d.title)}<p>${esc(d.period.label)} · ${esc(d.kind)} · publication ${esc(d.published_at || "unverified")}<br>${esc(d.publication_basis || "Publication metadata supplied with fixture/upload")}</p><details><summary>Source record</summary><small>${esc(d.id)} · SHA256 ${esc(d.sha256)}</small></details></div><span class="pill">${esc(d.evidence_eligibility === "after_as_of" ? "After review date · excluded" : d.evidence_eligibility === "date_unverified" ? "Date unverified" : d.completeness)}</span></div>`,
    )
    .join("");
  $("acquisition-log").innerHTML = REPORT.acquisition
    .map(
      (a) =>
        `<div class="log-row"><b>${esc(a.status)}</b>${esc(a.url || "local synthetic fixture")}${a.message ? `<p>${esc(a.message)}</p>` : ""}</div>`,
    )
    .join("");
  $("limitations").innerHTML =
    `<ul>${REPORT.limitations.map((l) => `<li>${esc(l)}</li>`).join("")}</ul><p>${esc(REPORT.interpretation)}</p><p>${esc(REPORT.priority_method)}</p><p>Review decisions stay in this browser until exported. This page cannot change source documents or write a repository file.</p>`;
  document
    .querySelectorAll(".nav-button")
    .forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
  for (const id of ["search", "status-filter", "topic-filter", "period-filter", "sort"])
    $(id).addEventListener(id === "search" ? "input" : "change", () => {
      if (view === "queue") setView("all");
      else draw();
    });
  $("view-all").addEventListener("click", () => setView("all"));
  $("clear-filters").addEventListener("click", () => {
    $("search").value = "";
    for (const id of ["status-filter", "topic-filter", "period-filter"]) $(id).value = "all";
    draw();
  });
  if (REPORT.related_reports?.length) {
    $("company-switch-label").hidden = false;
    for (const r of REPORT.related_reports) {
      const o = document.createElement("option");
      o.value = r.href;
      o.textContent = r.ticker;
      $("company-switch").append(o);
      if (r.ticker === REPORT.company.id) $("company-switch").value = r.href;
    }
    $("company-switch").addEventListener("change", () => {
      const href = $("company-switch").value;
      if (
        REPORT.related_reports.some((r) => r.href === href) &&
        !href.includes(":") &&
        !href.startsWith("//") &&
        !href.includes("\\")
      )
        window.location.href = href;
    });
  }
  $("export-data").addEventListener("click", () => download("commitments-data.json", REPORT));
  $("print").addEventListener("click", () => window.print());
  $("export-decisions").addEventListener("click", () => $("export-dialog").showModal());
  $("download-review").addEventListener("click", (e) => {
    if (!exportReview()) e.preventDefault();
  });
  draw();
}
init();
