/* DOM interactions without a browser, network or filesystem writes by the page. */
const fs = require("node:fs"),
  vm = require("node:vm"),
  assert = require("node:assert/strict");
const { parseHTML } = require("linkedom");
const path = process.argv[2] || "runs/demo/report/review.html";
const { window } = parseHTML(fs.readFileSync(path, "utf8"));
const document = window.document;
// LinkeDOM does not implement the browser's select setter or dialog/print APIs.
Object.defineProperty(window.HTMLSelectElement.prototype, "value", {
  configurable: true,
  get() {
    const o = [...this.querySelectorAll("option")].find((o) => o.hasAttribute("selected"));
    return (o || this.querySelector("option"))?.getAttribute("value") || "";
  },
  set(value) {
    this.querySelectorAll("option").forEach((o) =>
      o.toggleAttribute("selected", o.getAttribute("value") === value),
    );
  },
});
const memory = new Map(),
  blobs = [],
  events = [];
const storage = { getItem: (k) => memory.get(k) || null, setItem: (k, v) => memory.set(k, v) };
window.print = () => events.push("print");
document.getElementById("export-dialog").showModal = function () {
  this.setAttribute("open", "");
};
const url = {
  createObjectURL: (b) => {
    blobs.push(b);
    return "blob:local-test";
  },
  revokeObjectURL: () => {},
};
const FakeURL = function (...args) {
  return new URL(...args);
};
Object.assign(FakeURL, url);
const context = vm.createContext({
  window,
  document,
  localStorage: storage,
  URL: FakeURL,
  Blob,
  console,
  setTimeout: () => 0,
  Date,
});
const js = [...document.querySelectorAll("script")]
  .filter((x) => x.type !== "application/json")
  .map((x) => x.textContent)
  .join("\n");
vm.runInContext(js, context, { filename: "review.js" });
const $ = (id) => document.getElementById(id);
const click = (e) => e.dispatchEvent(new window.Event("click", { bubbles: true, cancelable: true }));
const change = (id, v, type = "change") => {
  $(id).value = v;
  $(id).dispatchEvent(new window.Event(type, { bubbles: true }));
};
const initialData = JSON.parse($("report-data").textContent);
if (initialData.related_reports?.length) {
  assert.equal(
    document.querySelectorAll("#company-switch option").length,
    initialData.related_reports.length,
  );
  assert.equal($("company-switch-label").hidden, false);
  window.location = { href: "" };
  const destination =
    initialData.related_reports.find((r) => r.ticker !== initialData.company.id) ||
    initialData.related_reports[0];
  change("company-switch", destination.href);
  assert.equal(window.location.href, destination.href);
  assert.ok($("breadcrumbs").querySelector("a"), "company index is reachable");
}
assert.equal(
  document.querySelectorAll(".card").length,
  initialData.top_three.length,
  "queue shows prioritised cards",
);
assert.equal(document.querySelector(".detail").hidden, true);
assert.ok(document.querySelector(".method-details"), "method details use progressive disclosure");
assert.equal(document.querySelector(".sidebar"), null, "single-level navigation replaces the sidebar");
click(document.querySelector('[data-view="attention"]'));
assert.equal(
  document.querySelectorAll(".card").length,
  initialData.commitments.filter(
    (c) =>
      [
        "blocked",
        "below_range",
        "missed",
        "definition_changed",
        "basis_mismatch",
        "conditional",
        "unresolved",
        "needs_review",
      ].includes(c.status) || c.updates.length > 0,
  ).length,
);
click(document.querySelector('[data-view="queue"]'));
change("search", initialData.commitments[initialData.commitments.length - 1].title, "input");
assert.equal(
  document.querySelector('[data-view="all"]').getAttribute("aria-current"),
  "page",
  "search covers all commitments",
);
click($("clear-filters"));
assert.equal($("search").value, "");
click(document.querySelector('[data-view="all"]'));
const reportData = JSON.parse($("report-data").textContent);
const count = reportData.commitments.length;
assert.equal(document.querySelectorAll(".card").length, count);
const selectedStatus = reportData.commitments[0].status;
change("status-filter", selectedStatus);
assert.equal(
  document.querySelectorAll(".card").length,
  reportData.commitments.filter((c) => c.status === selectedStatus).length,
  "assessment filter narrows the list",
);
change("status-filter", "all");
if (reportData.commitments.some((c) => c.condition_assessment?.met === false)) {
  assert.ok(
    $("cards").textContent.includes("Condition not met"),
    "unmet conditions are distinguished from unknown ones",
  );
}
const chosenTopic = reportData.commitments[0].topic;
change("topic-filter", chosenTopic);
assert.equal(
  document.querySelectorAll(".card").length,
  reportData.commitments.filter((c) => c.topic === chosenTopic).length,
);
change("topic-filter", "all");
const chosenPeriod = reportData.commitments.find((c) => c.target)?.target.period.label;
change("period-filter", chosenPeriod);
assert.equal(
  document.querySelectorAll(".card").length,
  reportData.commitments.filter((c) => c.target?.period.label === chosenPeriod).length,
);
change("period-filter", "all");
change("sort", "title");
assert.deepEqual(
  [...document.querySelectorAll(".card h3")].map((e) => e.textContent),
  reportData.commitments.map((c) => c.title).sort((a, b) => a.localeCompare(b)),
);
change("sort", "priority");
change("search", "there-is-no-such-commitment", "input");
assert.equal(document.querySelectorAll(".card").length, 0);
assert.equal($("empty").hidden, false);
change("search", "", "input");
const card = document.querySelector(".card"),
  expand = card.querySelector(".expand"),
  detail = card.querySelector(".detail");
click(expand);
assert.equal(detail.hidden, false);
assert.equal(expand.getAttribute("aria-expanded"), "true");
click(expand);
assert.equal(detail.hidden, true);
const sel = card.querySelector("select");
sel.value = "correction_requested";
sel.dispatchEvent(new window.Event("change"));
assert.equal(detail.hidden, false, "correction opens evidence/note area");
const note = card.querySelector("textarea");
note.value = "Check the definition and source period.";
note.dispatchEvent(new window.Event("input"));
assert.equal(memory.size, 1, "review is scoped to this analysis hash");
click($("export-decisions"));
assert.equal($("export-dialog").hasAttribute("open"), true);
$("reviewer").value = "UI test analyst";
click($("download-review"));
assert.equal(blobs.length, 1);
click($("export-data"));
assert.equal(blobs.length, 2);
click($("print"));
assert.deepEqual(events, ["print"]);
click(document.querySelector('[data-view="sources"]'));
assert.equal($("source-content").hidden, false);
assert.equal($("research-content").hidden, true);
assert.ok(document.querySelectorAll(".coverage-card").length > 0);
assert.ok($("source-list").textContent.includes("SHA256"));
if (reportData.documents.some((d) => d.evidence_eligibility === "after_as_of")) {
  assert.ok($("source-list").textContent.includes("After review date · excluded"));
}
assert.equal(vm.runInContext('safeURL("javascript:alert(1)")', context), null);
assert.equal(vm.runInContext('safeURL("https://user:password@example.com")', context), null);
assert.equal(vm.runInContext('esc("<img onerror=steal()>")', context), "&lt;img onerror=steal()&gt;");
Promise.all(blobs.map((b) => b.text()))
  .then((texts) => {
    const exported = JSON.parse(texts[0]);
    assert.equal(exported.reviewer, "UI test analyst");
    assert.equal(exported.decisions.find((d) => d.id === card.dataset.id).decision, "correction_requested");
    assert.equal(
      exported.decisions.find((d) => d.id === card.dataset.id).note,
      "Check the definition and source period.",
    );
    console.log(
      "UI checks passed: views, filters, empty state, evidence, decisions, storage, downloads, print, coverage and escaping.",
    );
    console.log("DOM tests only; no browser layout or visual rendering was verified.");
  })
  .catch((e) => {
    console.error(e);
    process.exitCode = 1;
  });
