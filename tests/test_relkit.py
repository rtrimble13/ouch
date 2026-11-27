"""Tests for scripts/relkit.py (versioning and releases).

Most tests build a throwaway git repository in tmp_path, so they don't depend
on the real history. test_repository_is_valid checks this repository.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import relkit  # noqa: E402
from relkit import Version  # noqa: E402

PYPROJECT = """[project]
name = "ouch"
dynamic = ["version"]
dependencies = ["typer>=0.12"]

[project.optional-dependencies]
pdf = ["pypdf"]
dev = ["pytest>=8"]

[tool.setuptools.dynamic]
version = {{ attr = "ouch.__version__" }}

[tool.pytest.ini_options]
testpaths = ["tests"]
{extra}"""

CHANGELOG = """# Changelog

## [Unreleased]

{sections}"""


def section(version: str, date: str = "2026-01-01", body: str = "- Something.") -> str:
    return f"## [{version}] - {date}\n\n### Added\n\n{body}\n\n"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


def set_version(root: Path, version: str, sections: str | None = None) -> None:
    write(root / "ouch" / "__init__.py", f'"""ouch."""\n\n__version__ = "{version}"\n')
    write(root / "CHANGELOG.md", CHANGELOG.format(sections=sections or section(version)))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    set_version(root, "0.1.0")
    write(root / "ouch" / "engine.py", "X = 1\n")
    write(root / "pyproject.toml", PYPROJECT.format(extra=""))
    write(root / "docs" / "guide.md", "# Guide\n")
    write(root / ".gitignore", "__pycache__/\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "base")
    git(root, "checkout", "-q", "-b", "feature")
    return root


def commit(root: Path, message: str = "change") -> None:
    git(root, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", message)


def errors(findings) -> list[str]:
    return [f.message for f in findings.errors]


# ----- versions -------------------------------------------------------------


@pytest.mark.parametrize(
    "lower, higher",
    [
        ("0.1.0", "0.1.1"),
        ("0.1.9", "0.2.0"),
        ("0.9.0", "1.0.0"),
        ("1.0.0a1", "1.0.0a2"),
        ("1.0.0a9", "1.0.0b1"),
        ("1.0.0b1", "1.0.0rc1"),
        ("1.0.0rc1", "1.0.0"),
        ("1.0.0", "1.0.1a1"),
    ],
)
def test_version_ordering(lower, higher):
    assert Version.parse(lower) < Version.parse(higher)


@pytest.mark.parametrize("text", ["1.0", "v1.0.0", "01.0.0", "1.0.0-rc.1", "1.0.0.post1", "1.0.0rc", ""])
def test_version_rejects_outside_the_subset(text):
    with pytest.raises(ValueError):
        Version.parse(text)


def test_version_round_trips_and_flags_prereleases():
    assert str(Version.parse("2.3.4rc5")) == "2.3.4rc5"
    assert Version.parse("2.3.4rc5").is_prerelease
    assert not Version.parse("2.3.4").is_prerelease


# ----- validate -------------------------------------------------------------


def test_valid_repository_passes(repo):
    version, findings = relkit.validate(repo)
    assert version == "0.1.0"
    assert not findings.items


def test_changelog_must_match_the_version(repo):
    set_version(repo, "0.2.0", sections=section("0.1.0"))
    assert any("latest section is [0.1.0]" in m for m in errors(relkit.validate(repo)[1]))


def test_changelog_sections_need_dates_and_order(repo):
    write(
        repo / "CHANGELOG.md",
        "## [0.1.0] - 2026-01-01\n\n## [Unreleased]\n\n## [0.2.0]\n\n",
    )
    messages = errors(relkit.validate(repo)[1])
    assert any("[Unreleased] must come before" in m for m in messages)
    assert any("needs a date" in m for m in messages)
    assert any("newest first" in m for m in messages)


def test_static_version_in_pyproject_is_rejected(repo):
    text = (repo / "pyproject.toml").read_text().replace('dynamic = ["version"]', 'version = "0.1.0"')
    write(repo / "pyproject.toml", text)
    messages = errors(relkit.validate(repo)[1])
    assert any("static version" in m for m in messages)
    assert any('dynamic = ["version"]' in m for m in messages)


def test_bad_version_string_is_rejected(repo):
    set_version(repo, "0.1", sections=section("0.1.0"))
    assert any("not a valid version" in m for m in errors(relkit.validate(repo)[1]))


# ----- the version gate -----------------------------------------------------


def test_docs_and_tests_need_no_bump(repo):
    write(repo / "docs" / "guide.md", "# Guide, revised\n")
    write(repo / "tests" / "test_new.py", "def test(): pass\n")
    commit(repo)
    report, findings = relkit.check_versions(repo, "main")
    assert report == []
    assert not findings.errors


def test_shipped_change_without_bump_fails(repo):
    write(repo / "ouch" / "engine.py", "X = 2\n")
    commit(repo)
    report, findings = relkit.check_versions(repo, "main")
    assert any("still 0.1.0" in m for m in errors(findings))
    assert "ouch: 0.1.0 -> 0.1.0 (needs a bump)" in report


def test_bump_without_changelog_section_fails(repo):
    write(repo / "ouch" / "engine.py", "X = 2\n")
    write(repo / "ouch" / "__init__.py", '__version__ = "0.1.1"\n')
    commit(repo)
    messages = errors(relkit.check_versions(repo, "main")[1])
    assert any("add a '## [0.1.1]" in m for m in messages)


def test_bump_with_changelog_passes(repo):
    write(repo / "ouch" / "engine.py", "X = 2\n")
    set_version(repo, "0.1.1", sections=section("0.1.1") + section("0.1.0"))
    commit(repo)
    report, findings = relkit.check_versions(repo, "main")
    assert not findings.errors
    assert report[0] == "ouch: 0.1.0 -> 0.1.1"
    assert "  changed: ouch/engine.py" in report


def test_version_must_increase(repo):
    write(repo / "ouch" / "engine.py", "X = 2\n")
    set_version(repo, "0.1.0rc1", sections=section("0.1.0rc1"))
    commit(repo)
    assert any("still 0.1.0rc1" in m for m in errors(relkit.check_versions(repo, "main")[1]))


def test_untracked_and_tax_data_files_count(repo):
    write(repo / "ouch" / "taxdata" / "data" / "federal" / "2027.yaml", "meta: {}\n")
    report, findings = relkit.check_versions(repo, "main")
    assert errors(findings)
    assert "  changed: ouch/taxdata/data/federal/2027.yaml" in report


def test_bytecode_is_ignored(repo):
    write(repo / "ouch" / "__pycache__" / "engine.cpython-313.pyc", "x")
    git(repo, "add", "-f", "ouch/__pycache__/engine.cpython-313.pyc")
    commit(repo)
    assert relkit.check_versions(repo, "main") == ([], relkit.Findings())


def test_dependency_change_needs_a_bump(repo):
    text = (repo / "pyproject.toml").read_text().replace("typer>=0.12", "typer>=0.13")
    write(repo / "pyproject.toml", text)
    commit(repo)
    report, findings = relkit.check_versions(repo, "main")
    assert errors(findings)
    assert "  changed: pyproject.toml [project]" in report


@pytest.mark.parametrize(
    "old, new",
    [
        ('testpaths = ["tests"]', 'testpaths = ["tests", "more"]'),  # tool config
        ('dev = ["pytest>=8"]', 'dev = ["pytest>=9", "build"]'),  # contributors' extra
    ],
)
def test_non_shipping_pyproject_changes_need_no_bump(repo, old, new):
    write(repo / "pyproject.toml", (repo / "pyproject.toml").read_text().replace(old, new))
    commit(repo)
    assert relkit.check_versions(repo, "main") == ([], relkit.Findings())


# ----- notes and release planning ------------------------------------------


def test_changelog_section_extraction():
    text = CHANGELOG.format(sections=section("0.2.0", body="- New.") + section("0.1.0", body="- Old."))
    text += "[0.2.0]: https://example.invalid/compare\n"
    assert relkit.changelog_section(text, "0.2.0") == "### Added\n\n- New."
    assert relkit.changelog_section(text, "0.1.0") == "### Added\n\n- Old."
    assert relkit.changelog_section(text, "9.9.9") is None


def test_release_dry_run_plans_an_untagged_version(repo, capsys):
    assert relkit.main(["--root", str(repo), "release", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "would release v0.1.0" in out
    assert "--prerelease" not in out
    assert "- Something." in out


def test_release_skips_a_tagged_version(repo, capsys):
    git(repo, "tag", "v0.1.0")
    assert relkit.main(["--root", str(repo), "release", "--dry-run"]) == 0
    assert "already released" in capsys.readouterr().out


def test_prerelease_is_flagged(repo, capsys):
    set_version(repo, "0.2.0rc1", sections=section("0.2.0rc1") + section("0.1.0"))
    assert relkit.main(["--root", str(repo), "release", "--dry-run"]) == 0
    assert "--prerelease" in capsys.readouterr().out


def test_release_refuses_an_invalid_repository(repo, capsys):
    set_version(repo, "0.2.0", sections=section("0.1.0"))
    assert relkit.main(["--root", str(repo), "release", "--dry-run"]) == 1
    assert "refusing to release" in capsys.readouterr().out


def _release_on_main(repo: Path, version: str, sections: str) -> str:
    git(repo, "checkout", "-q", "main")
    set_version(repo, version, sections=sections)
    commit(repo, f"release {version}")
    return git(repo, "rev-parse", "HEAD").strip()


def test_release_catches_up_a_version_that_was_never_released(repo, capsys):
    """A cancelled release run leaves 0.2.0 on main without a tag: the next
    run releases it from its own commit, not marked latest."""
    git(repo, "tag", "v0.1.0")
    sha = _release_on_main(repo, "0.2.0", section("0.2.0", body="- Two.") + section("0.1.0"))
    _release_on_main(repo, "0.3.0", section("0.3.0") + section("0.2.0", body="- Two.")
                     + section("0.1.0"))
    assert relkit.main(["--root", str(repo), "release", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert f"v0.2.0 reached main at {sha[:12]}" in out
    assert f"--target {sha} --latest=false" in out
    assert "- Two." in out
    assert "would release v0.3.0" in out
    assert out.index("v0.2.0") < out.index("would release v0.3.0")
    assert git(repo, "worktree", "list").count("\n") == 1   # temporary tree removed


def test_a_failed_catch_up_does_not_block_the_current_release(repo, capsys, monkeypatch):
    git(repo, "tag", "v0.1.0")
    _release_on_main(repo, "0.2.0", section("0.2.0") + section("0.1.0"))
    _release_on_main(repo, "0.3.0", section("0.3.0") + section("0.2.0") + section("0.1.0"))

    def refuse(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["gh", "release", "create"])
    monkeypatch.setattr(relkit, "publish_missed", refuse)
    assert relkit.main(["--root", str(repo), "release", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "::warning::v0.2.0 could not be released" in out
    assert "would release v0.3.0" in out


def test_catch_up_runs_even_when_the_current_version_is_tagged(repo, capsys):
    git(repo, "tag", "v0.1.0")
    _release_on_main(repo, "0.2.0", section("0.2.0") + section("0.1.0"))
    _release_on_main(repo, "0.3.0", section("0.3.0") + section("0.2.0") + section("0.1.0"))
    git(repo, "tag", "v0.3.0")
    assert relkit.main(["--root", str(repo), "release", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "would release v0.2.0" in out
    assert "v0.3.0 is already released" in out


def test_no_catch_up_before_the_first_release(repo, capsys):
    """Without tags, only the current version is released: history from
    before the release model isn't backfilled."""
    _release_on_main(repo, "0.2.0", section("0.2.0") + section("0.1.0"))
    assert relkit.main(["--root", str(repo), "release", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "catching up" not in out
    assert "would release v0.2.0" in out


def test_versions_only_on_a_merged_branch_are_not_caught_up(repo, capsys):
    """0.2.0 lived only on a feature branch (a stacked PR merged into
    another branch); main went from 0.1.0 straight to 0.3.0."""
    git(repo, "tag", "v0.1.0")
    set_version(repo, "0.2.0", sections=section("0.2.0") + section("0.1.0"))
    commit(repo, "0.2.0 on feature")
    set_version(repo, "0.3.0", sections=section("0.3.0") + section("0.2.0") + section("0.1.0"))
    commit(repo, "0.3.0 on feature")
    git(repo, "checkout", "-q", "main")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid",
        "merge", "-q", "--no-ff", "-m", "merge feature", "feature")
    assert [v for v, _ in relkit.versions_on_main(repo)] == ["0.1.0", "0.3.0"]
    assert relkit.main(["--root", str(repo), "release", "--dry-run"]) == 0
    assert "catching up" not in capsys.readouterr().out


def test_notes_command(repo, capsys):
    assert relkit.main(["--root", str(repo), "notes"]) == 0
    assert "- Something." in capsys.readouterr().out
    assert relkit.main(["--root", str(repo), "notes", "--version", "9.9.9"]) == 1


# ----- this repository -----------------------------------------------------


def test_repository_is_valid():
    version, findings = relkit.validate(REPO)
    assert not findings.errors, [f.message for f in findings.errors]
    import ouch

    assert version == ouch.__version__
