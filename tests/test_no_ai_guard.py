"""Check 2: the no-AI guard catches blocklisted packages, imports and hosts."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _guard() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_no_ai", ROOT / "ci" / "check_no_ai.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_no_ai"] = mod  # dataclasses need the module registered
    spec.loader.exec_module(mod)
    return mod


G = _guard()
BL = G.load_blocklist()


@pytest.mark.parametrize(
    "pkg",
    ["openai", "Anthropic", "langchain_openai", "langchain-core", "sentence_transformers",
     "torch", "scikit-learn", "dedupe", "splink", "llama-index-core", "anticaptchaofficial",
     "2captcha-python"],
)  # fmt: skip
def test_blocked_packages(pkg: str) -> None:
    assert G.blocked_package(pkg, BL)


@pytest.mark.parametrize("pkg", ["duckdb", "rapidfuzz", "pyyaml", "hypothesis", "pytz"])
def test_allowed_packages(pkg: str) -> None:
    assert G.blocked_package(pkg, BL) is None


@pytest.mark.parametrize(
    ("source", "blocked"),
    [
        ("import openai", True),
        ("from anthropic import Anthropic", True),
        ("from langchain_community.llms import X", True),
        ("import sklearn.cluster", True),
        ("from google import genai\nimport google.genai", True),
        ("importlib.import_module('transformers')", True),
        ("__import__('torch')", True),
        ("from twocaptcha import TwoCaptcha", True),
        ("import duckdb\nfrom rapidfuzz import fuzz", False),
        ("from . import openai_like", False),
    ],
)
def test_imports(source: str, blocked: bool) -> None:
    hits = [m for m in G.imports_in(source) if G.blocked_module(m, BL)]
    assert bool(hits) is blocked


def test_hosts() -> None:
    assert G.hosts_in('URL = "https://API.OpenAI.com/v1/chat"', BL) == ["api.openai.com"]
    assert G.hosts_in('URL = "https://services3.arcgis.com/x"', BL) == []


def test_lock_and_pyproject_parsing() -> None:
    lock = '[[package]]\nname = "duckdb"\n[[package]]\nname = "litellm"\n'
    assert [p for p in G.lock_packages(lock) if G.blocked_package(p, BL)] == ["litellm"]
    pyproject = (
        '[project]\ndependencies = ["duckdb>=1", "openai[x]>=1; python_version>\'3\'"]\n'
        '[dependency-groups]\ndev = ["pytest", {include-group = "x"}]\n'
    )
    assert G.pyproject_requirements(pyproject) == ["duckdb", "openai", "pytest"]


def test_scan_flags_a_planted_import(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)  # noqa: S603, S607
    (tmp_path / "uv.lock").write_text('[[package]]\nname = "torch"\n')
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["openai"]\n')
    (tmp_path / "bad.py").write_text("import anthropic\nX = 'api.groq.com'\n")
    problems = G.scan(tmp_path, BL)
    assert any("uv.lock" in p and "torch" in p for p in problems)
    assert any("pyproject.toml" in p and "openai" in p for p in problems)
    assert any("bad.py" in p and "anthropic" in p for p in problems)
    assert any("api.groq.com" in p for p in problems)


def test_scan_requires_lockfile(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)  # noqa: S603, S607
    (tmp_path / "pyproject.toml").write_text("[project]\ndependencies = []\n")
    assert any("uv.lock is missing" in p for p in G.scan(tmp_path, BL))


def test_this_repository_is_clean() -> None:
    assert G.scan() == []
