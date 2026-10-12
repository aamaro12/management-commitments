/* Static DOM checks; no browser, network or page filesystem access. */
const fs = require("node:fs"),
  vm = require("node:vm"),
  assert = require("node:assert/strict");
const { parseHTML } = require("linkedom");
const path = process.argv[2];
const { window } = parseHTML(fs.readFileSync(path, "utf8")),
  document = window.document;
Object.defineProperty(window.HTMLSelectElement.prototype, "value", {
  configurable: true,
  get() {
    return (
      (
        [...this.querySelectorAll("option")].find((o) => o.hasAttribute("selected")) ||
        this.querySelector("option")
      )?.getAttribute("value") || ""
    );
  },
  set(v) {
    this.querySelectorAll("option").forEach((o) =>
      o.toggleAttribute("selected", o.getAttribute("value") === v),
    );
  },
});
const data = JSON.parse(document.getElementById("portfolio-data").textContent);
const script = [...document.querySelectorAll("script")]
  .filter((s) => s.type !== "application/json")
  .map((s) => s.textContent)
  .join("\n");
const context = vm.createContext({ window, document });
vm.runInContext(script, context);
const rows = () => [...document.querySelectorAll("tbody tr")];
const change = (id, value, type = "change") => {
  document.getElementById(id).value = value;
  document.getElementById(id).dispatchEvent(new window.Event(type, { bubbles: true }));
};
assert.equal(rows().length, data.reports.length);
assert.equal(document.querySelectorAll(".company-link").length, data.reports.length);
assert.ok(document.querySelectorAll(".company-link")[0].getAttribute("href").endsWith("review.html"));
change("search", data.reports[0].company.id, "input");
assert.equal(rows().length, 1);
change("search", "no-matching-company-exists", "input");
assert.equal(rows().length, 0);
assert.equal(document.getElementById("empty").hidden, false);
document.getElementById("clear").dispatchEvent(new window.Event("click"));
assert.equal(rows().length, data.reports.length);
change("coverage-filter", "calls");
assert.equal(rows().length, data.reports.filter((r) => r.transcripts > 0).length);
change("coverage-filter", "release");
assert.equal(rows().length, data.reports.filter((r) => r.transcripts === 0).length);
change("coverage-filter", "all");
change("sort", "attention");
assert.deepEqual(
  rows().map((r) => r.dataset.ticker),
  data.reports
    .slice()
    .sort((a, b) => b.attention - a.attention || a.company.name.localeCompare(b.company.name))
    .map((r) => r.company.id),
);
assert.equal(vm.runInContext('safePath("javascript:evil()")', context), null);
assert.equal(vm.runInContext('safePath("//evil.example")', context), null);
assert.equal(
  vm.runInContext('safePath("../../other/report/review.html")', context),
  "../../other/report/review.html",
);
console.log(
  "Portfolio DOM checks passed:",
  data.reports.length === 1 ? "1 company;" : data.reports.length + " companies;",
  "search, coverage, sort, empty state and safe paths.",
);
