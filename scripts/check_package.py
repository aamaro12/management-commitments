#!/usr/bin/env python3
"""Check the portable plugin's identity and every published file; no installation or upload."""

import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
project = (ROOT / "pyproject.toml").read_text()
NAME = re.search(r'^name = "([^"]+)"', project, re.M)[1]
VERSION = re.search(r'^version = "([^"]+)"', project, re.M)[1]
IGNORED = {".git", ".venv", "build", "dist", "node_modules", "runs", "__pycache__"}
TEXT = {".py", ".md", ".json", ".html", ".js", ".cjs", ".css", ".yaml", ".yml", ".toml", ".txt", ""}
CREDENTIAL = re.compile(
    r"\b(?:sk|ghp|gho|ghu|ghs|ghr)[_-][A-Za-z0-9_-]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
)
HOME_PATH = re.compile(r"/(?:Users|home)/(?!Shared\b)[A-Za-z0-9._-]+/")


def published():
    try:
        names = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return [ROOT / n for n in names.splitlines()]
    except (OSError, subprocess.CalledProcessError):
        return [p for p in ROOT.rglob("*") if p.is_file() and not unpublished(p.relative_to(ROOT))]


def unpublished(relative):
    """Local caches and environments; .github and .codex-plugin are part of the package."""
    return any(
        part in IGNORED
        or part.endswith(".egg-info")
        or (part.startswith(".") and part not in {".github", ".codex-plugin"})
        for part in relative.parts[:-1]
    )


root = json.loads((ROOT / "plugin.json").read_text())
overlay = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())
assert root["name"] == overlay["name"] == NAME
assert root["version"] == overlay["version"] == VERSION
init = (ROOT / "src" / "management_commitments" / "__init__.py").read_text()
assert re.search(rf'^__version__ = "{re.escape(VERSION)}"$', init, re.M)
assert root["extensions"]["com.openai"]["interface"]["displayName"] == overlay["interface"]["displayName"]
assert len(root["extensions"]["com.openai"]["interface"]["shortDescription"]) <= 30
skill = ROOT / "skills" / "track-management-commitments" / "SKILL.md"
text = skill.read_text()
assert re.search(r"^name: track-management-commitments$", text, re.M)
assert "description:" in text
assert (skill.parent / "references" / "data-contract.md").exists()
assert (ROOT / "src" / "management_commitments" / "assets" / "review.html").exists()
assert not root.get("apps") and not root["extensions"]["com.openai"].get("apps")
files = published()
for p in files:
    assert not p.is_symlink(), f"Unexpected symlink: {p.relative_to(ROOT)}"
    if p.suffix in TEXT and p.exists():
        content = p.read_text(errors="replace")
        assert not CREDENTIAL.search(content), f"Credential-shaped literal: {p.relative_to(ROOT)}"
        assert not HOME_PATH.search(content), f"Personal home path: {p.relative_to(ROOT)}"
print(
    f"Package checks passed for {NAME} {VERSION}: matching manifests and skill references; "
    f"{len(files)} published files with no credential-shaped literals or personal paths."
)
