"""The repo layout in the brief (§4) is a contract: every spec file and package must exist."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

SPECS = [
    "00-glossary.md",
    "01-ingestion-and-graph.md",
    "02-process-discovery.md",
    "03-digital-twin.md",
    "04-autonomy-ledger.md",
    "05-actor-verifier.md",
    "06-pii-boundary.md",
    "07-immune-system.md",
    "08-adapter-generator.md",
    "09-model-router.md",
    "10-dashboard.md",
    "11-security-and-tenancy.md",
]
REQUIRED_SECTIONS = [
    "## Purpose",
    "## Inputs",
    "## Outputs",
    "## Data model",
    "## Interfaces",
    "## Failure modes",
    "## Acceptance tests",
    "## Open questions",
]
PACKAGES = [
    "core/graph",
    "core/documents",
    "core/pii",
    "core/models",
    "core/ledger",
    "core/action",
    "core/events",
    "core/tenancy",
    "adapters/_contract",
    "adapters/gmail",
    "adapters/clickup",
    "adapters/gdrive",
    "adapters/slack",
    "adapters/postgres_generic",
    "adapters/generator",
    "agents/extract",
    "agents/discover",
    "agents/plan",
    "agents/verify",
    "agents/explain",
    "agents/immune",
    "twin",
    "workflows",
    "api",
    "evals",
]


@pytest.mark.parametrize("spec", SPECS)
def test_spec_exists_with_required_sections(repo_root: Path, spec: str) -> None:
    path = repo_root / "specs" / spec
    assert path.exists(), f"missing spec {spec}"
    text = path.read_text(encoding="utf-8")
    # The glossary is the one spec whose shape is a term table, not a pillar.
    if spec.startswith("00-"):
        assert "## Open questions" in text
        return
    missing = [s for s in REQUIRED_SECTIONS if s not in text]
    assert not missing, f"{spec} missing sections: {missing}"


@pytest.mark.parametrize("package", PACKAGES)
def test_package_exists(repo_root: Path, package: str) -> None:
    assert (repo_root / package / "__init__.py").exists(), f"missing package {package}"


def test_docs_exist(repo_root: Path) -> None:
    for name in ["STATUS.md", "QUESTIONS.md", "architecture.md", "compliance.md"]:
        assert (repo_root / "docs" / name).exists(), f"missing docs/{name}"
    assert any((repo_root / "docs" / "adr").glob("*.md")), "at least one ADR expected"


def test_engineering_rules_are_written_down(repo_root: Path) -> None:
    text = (repo_root / "ENGINEERING.md").read_text(encoding="utf-8")
    assert "Only core/action/executor.py may call adapter write methods." in text
    assert "core/models/router.py" in text
