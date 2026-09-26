"""Static guards for the non-negotiable principles (brief §2).

These tests parse every Python file with `ast` and fail if:
- a vendor model SDK is imported outside core/models/providers (principle 9),
- an agent framework is imported anywhere (brief §3),
- any module other than core/action/executor.py imports the PII `restore` (principle 2),
- any module other than core/action/executor.py references an adapter `.write(` call or imports
  `WriteOp` construction helpers (principle 1),
- `eval(` / `exec(` appear in twin/ (spec 03).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

VENDOR_SDKS = {"anthropic", "openai", "google.genai", "google.generativeai", "ollama", "vllm"}
FRAMEWORKS = {"langchain", "langchain_core", "llama_index", "crewai", "autogen"}
PROVIDERS_DIR = Path("core/models/providers")
EXECUTOR = Path("core/action/executor.py")
SOURCE_DIRS = ("core", "adapters", "agents", "twin", "workflows", "api", "evals", "scripts")


def _python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for d in SOURCE_DIRS:
        base = root / d
        if base.exists():
            files.extend(p for p in base.rglob("*.py") if "fixtures" not in p.parts)
    return files


def _imports(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _matches(imported: str, banned: set[str]) -> bool:
    return any(imported == b or imported.startswith(b + ".") for b in banned)


def test_vendor_sdks_only_in_providers(repo_root: Path) -> None:
    offenders: list[str] = []
    for path in _python_files(repo_root):
        rel = path.relative_to(repo_root)
        if rel.is_relative_to(PROVIDERS_DIR):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bad = sorted(name for name in _imports(tree) if _matches(name, VENDOR_SDKS))
        if bad:
            offenders.append(f"{rel}: {bad}")
    assert not offenders, "vendor SDK imported outside core/models/providers:\n" + "\n".join(
        offenders
    )


def test_no_agent_frameworks(repo_root: Path) -> None:
    offenders: list[str] = []
    for path in _python_files(repo_root):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bad = sorted(name for name in _imports(tree) if _matches(name, FRAMEWORKS))
        if bad:
            offenders.append(f"{path.relative_to(repo_root)}: {bad}")
    assert not offenders, "agent framework imported:\n" + "\n".join(offenders)


def test_restore_only_in_executor(repo_root: Path) -> None:
    offenders: list[str] = []
    for path in _python_files(repo_root):
        rel = path.relative_to(repo_root)
        if rel == EXECUTOR or rel.is_relative_to(Path("core/pii")):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if "core.pii.boundary.restore" in _imports(tree):
            offenders.append(str(rel))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "restore"
                and isinstance(node.value, ast.Name)
                and node.value.id == "boundary"
            ):
                offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, "PII restore used outside executor:\n" + "\n".join(offenders)


def test_adapter_write_only_in_executor(repo_root: Path) -> None:
    """Only the executor may INVOKE a write.

    Two separate rules, because they mean different things:

    * Calling `<adapter>.write(op)` is the write itself. Only the executor may do it, and the
      check covers every module including the adapters, so one adapter cannot drive another.
    * Constructing a `WriteOp` is describing a write, not performing one. The executor builds
      them, and an adapter builds one to hand back as the reversal instruction for something it
      just did. Everywhere else it is a sign that a caller is assembling its own write path, so
      it stays banned outside `adapters/`.
    """
    call_offenders: list[str] = []
    build_offenders: list[str] = []
    for path in _python_files(repo_root):
        rel = path.relative_to(repo_root)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "WriteOp":
                in_adapters = rel.is_relative_to(Path("adapters"))
                if rel != EXECUTOR and not in_adapters:
                    build_offenders.append(f"{rel}:{node.lineno} constructs WriteOp")
            if isinstance(func, ast.Attribute) and func.attr == "write" and rel != EXECUTOR:
                receiver = func.value
                name = receiver.id if isinstance(receiver, ast.Name) else ""
                attr = receiver.attr if isinstance(receiver, ast.Attribute) else ""
                if "adapter" in (name + attr).lower():
                    call_offenders.append(f"{rel}:{node.lineno} calls adapter.write")
    assert not call_offenders, "adapter write invoked outside executor:\n" + "\n".join(
        call_offenders
    )
    assert not build_offenders, "WriteOp built outside executor/adapters:\n" + "\n".join(
        build_offenders
    )


def test_no_eval_or_exec_in_twin(repo_root: Path) -> None:
    offenders: list[str] = []
    twin = repo_root / "twin"
    for path in twin.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"eval", "exec"}
            ):
                offenders.append(f"{path.relative_to(repo_root)}:{node.lineno}")
    assert not offenders, "eval/exec in twin:\n" + "\n".join(offenders)


def test_executor_exists(repo_root: Path) -> None:
    assert (repo_root / EXECUTOR).exists(), "the single write path module must exist"
