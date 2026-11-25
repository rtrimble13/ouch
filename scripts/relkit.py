#!/usr/bin/env python3
"""relkit: versioning and release tool for the ouch package.

Subcommands:
  validate        check the version, pyproject wiring and CHANGELOG.md
  check-versions  require a version bump and changelog section when shipped files change
  package         build the sdist and wheel, with .sha256 files (default: dist/)
  release         publish a GitHub release for the current version if it has no tag yet
  notes           print the changelog section for a version

Run `python scripts/relkit.py <subcommand> --help` for options. It uses only
the standard library (plus `build` for `package`). The rules it enforces are
documented in docs/versioning-and-releases.md.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import os
import re
import shlex
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent

PACKAGE = "ouch"
VERSION_FILE = "ouch/__init__.py"
CHANGELOG = "CHANGELOG.md"
PYPROJECT = "pyproject.toml"
TAG_PREFIX = "v"

# Files that ship in the package. A change to any of them needs a version bump.
# pyproject.toml counts only through its [project] table (dependencies, entry
# points, metadata), less the version and the `dev` extra; tool configuration
# does not ship.
SHIPPED_PREFIXES = ("ouch/",)
IGNORED_PARTS = frozenset({"__pycache__"})
IGNORED_SUFFIXES = frozenset({".pyc", ".pyo"})

# A PEP 440 subset that is also unambiguous to read as SemVer:
# MAJOR.MINOR.PATCH with an optional aN / bN / rcN pre-release.
VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:(a|b|rc)(0|[1-9]\d*))?$")
VERSION_ASSIGN_RE = re.compile(r"""^__version__\s*=\s*["']([^"']*)["']\s*$""", re.MULTILINE)
CHANGELOG_HEADING_RE = re.compile(
    r"^## \[(?P<version>[^\]]+)\](?:[ \t]+-[ \t]+(?P<date>\d{4}-\d{2}-\d{2}))?[ \t]*$",
    re.MULTILINE,
)
REF_DEF_RE = re.compile(r"^ {0,3}\[[^\]]+\]:\s*<?([^\s>]+)>?")
PRE_ORDER = {"a": 0, "b": 1, "rc": 2}


# --------------------------------------------------------------------------- #
# Versions
# --------------------------------------------------------------------------- #


@functools.total_ordering
@dataclass(frozen=True)
class Version:
    """MAJOR.MINOR.PATCH with an optional PEP 440 pre-release (a, b, rc)."""

    major: int
    minor: int
    patch: int
    pre: tuple[str, int] | None = None

    @classmethod
    def parse(cls, text: str) -> Version:
        match = VERSION_RE.match(text or "")
        if not match:
            raise ValueError(
                f"not a valid version (MAJOR.MINOR.PATCH, optionally with aN, bN or rcN): {text!r}"
            )
        pre = (match.group(4), int(match.group(5))) if match.group(4) else None
        return cls(int(match.group(1)), int(match.group(2)), int(match.group(3)), pre)

    @property
    def is_prerelease(self) -> bool:
        return self.pre is not None

    def _key(self) -> tuple:
        # A final release sorts above its pre-releases: 1.0.0a1 < 1.0.0b1 < 1.0.0rc1 < 1.0.0.
        pre = (0, PRE_ORDER[self.pre[0]], self.pre[1]) if self.pre else (1, 0, 0)
        return (self.major, self.minor, self.patch, pre)

    def __lt__(self, other: Version) -> bool:
        return self._key() < other._key()

    def __str__(self) -> str:
        text = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre:
            text += f"{self.pre[0]}{self.pre[1]}"
        return text


# --------------------------------------------------------------------------- #
# Findings
# --------------------------------------------------------------------------- #


@dataclass
class Finding:
    level: str  # "error" or "warning"
    path: str
    message: str
    line: int | None = None


@dataclass
class Findings:
    items: list[Finding] = field(default_factory=list)

    def error(self, path: str, message: str, line: int | None = None) -> None:
        self.items.append(Finding("error", path, message, line))

    def warning(self, path: str, message: str, line: int | None = None) -> None:
        self.items.append(Finding("warning", path, message, line))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.items if f.level == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.items if f.level == "warning"]

    def emit(self, stream=None) -> None:
        stream = stream or sys.stdout
        github = os.environ.get("GITHUB_ACTIONS") == "true"
        for f in sorted(self.items, key=lambda f: (f.level != "error", f.path, f.line or 0)):
            if github:
                loc = f"file={f.path}" + (f",line={f.line}" if f.line else "")
                print(f"::{f.level} {loc}::{f.message}", file=stream)
            else:
                loc = f.path + (f":{f.line}" if f.line else "")
                print(f"{f.level.upper():<7} {loc}: {f.message}", file=stream)


# --------------------------------------------------------------------------- #
# Reading the version and changelog
# --------------------------------------------------------------------------- #


def read_version(text: str) -> str | None:
    match = VERSION_ASSIGN_RE.search(text)
    return match.group(1) if match else None


def changelog_headings(text: str) -> list[tuple[str, str | None, int]]:
    return [
        (m.group("version"), m.group("date"), text.count("\n", 0, m.start()) + 1)
        for m in CHANGELOG_HEADING_RE.finditer(text)
    ]


def changelog_section(text: str, version: str) -> str | None:
    """The body of the `## [version]` section, without trailing link definitions."""
    headings = list(CHANGELOG_HEADING_RE.finditer(text))
    for i, match in enumerate(headings):
        if match.group("version") != version:
            continue
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        lines = text[match.end() : end].strip("\n").split("\n")
        while lines and (not lines[-1].strip() or REF_DEF_RE.match(lines[-1])):
            lines.pop()
        return "\n".join(lines).strip()
    return None


def check_changelog(text: str, version: str | None, findings: Findings) -> None:
    seen_release = False
    released: list[tuple[Version, int]] = []
    for heading, date, line in changelog_headings(text):
        if heading.lower() == "unreleased":
            if seen_release:
                findings.error(CHANGELOG, "[Unreleased] must come before every version section", line)
            continue
        seen_release = True
        try:
            parsed = Version.parse(heading)
        except ValueError as exc:
            findings.error(CHANGELOG, str(exc), line)
            continue
        if not date:
            findings.error(CHANGELOG, f"section [{heading}] needs a date: '## [{heading}] - YYYY-MM-DD'", line)
        released.append((parsed, line))
    for (newer, _), (older, line) in zip(released, released[1:], strict=False):
        if not older < newer:
            findings.error(CHANGELOG, f"versions must be listed newest first ({older} after {newer})", line)
    if not released:
        findings.error(CHANGELOG, "no version sections; add '## [x.y.z] - YYYY-MM-DD'")
        return
    if version and VERSION_RE.match(version):
        latest = released[0][0]
        if latest != Version.parse(version):
            findings.error(
                CHANGELOG,
                f"latest section is [{latest}] but {VERSION_FILE} says {version}; "
                f"add '## [{version}] - YYYY-MM-DD' describing the change",
                released[0][1],
            )


def check_pyproject(data: dict, findings: Findings) -> None:
    project = data.get("project", {})
    if "version" in project:
        findings.error(
            PYPROJECT,
            f"[project] sets a static version; use dynamic = [\"version\"] so {VERSION_FILE} "
            "is the single source",
        )
    if "version" not in project.get("dynamic", []):
        findings.error(PYPROJECT, '[project] needs dynamic = ["version"]')
    attr = data.get("tool", {}).get("setuptools", {}).get("dynamic", {}).get("version", {}).get("attr")
    if attr != f"{PACKAGE}.__version__":
        findings.error(
            PYPROJECT,
            f'[tool.setuptools.dynamic] needs version = {{attr = "{PACKAGE}.__version__"}}',
        )


def validate(root: Path) -> tuple[str | None, Findings]:
    findings = Findings()
    version_path = root / VERSION_FILE
    version = read_version(version_path.read_text(encoding="utf-8")) if version_path.is_file() else None
    if version is None:
        findings.error(VERSION_FILE, '__version__ = "x.y.z" not found')
    else:
        try:
            Version.parse(version)
        except ValueError as exc:
            findings.error(VERSION_FILE, str(exc))
    pyproject = root / PYPROJECT
    if pyproject.is_file():
        check_pyproject(tomllib.loads(pyproject.read_text(encoding="utf-8")), findings)
    else:
        findings.error(PYPROJECT, "missing")
    log = root / CHANGELOG
    if log.is_file():
        check_changelog(log.read_text(encoding="utf-8"), version, findings)
    else:
        findings.error(CHANGELOG, "missing")
    return version, findings


# --------------------------------------------------------------------------- #
# Git and the version gate
# --------------------------------------------------------------------------- #


class GitError(RuntimeError):
    pass


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {result.stderr.strip() or 'failed'}")
    return result.stdout


def changed_files(root: Path, base: str) -> tuple[str, list[str]]:
    merge_base = git(root, "merge-base", base, "HEAD").strip()
    tracked = git(root, "diff", "--name-only", merge_base).split("\n")
    untracked = git(root, "ls-files", "--others", "--exclude-standard").split("\n")
    return merge_base, sorted({f for f in tracked + untracked if f})


def is_shipped(path: str) -> bool:
    parts = path.split("/")
    if IGNORED_PARTS.intersection(parts) or Path(path).suffix in IGNORED_SUFFIXES:
        return False
    return path.startswith(SHIPPED_PREFIXES)


def shipped_metadata(pyproject: dict) -> dict:
    """The [project] table as users see it: without the version (checked on
    its own) and without the contributors' `dev` extra."""
    project = {k: v for k, v in pyproject.get("project", {}).items() if k not in ("version", "dynamic")}
    extras = {k: v for k, v in project.get("optional-dependencies", {}).items() if k != "dev"}
    if extras:
        project["optional-dependencies"] = extras
    else:
        project.pop("optional-dependencies", None)
    return project


def project_table_changed(root: Path, merge_base: str) -> bool:
    try:
        before = tomllib.loads(git(root, "show", f"{merge_base}:{PYPROJECT}"))
    except (GitError, tomllib.TOMLDecodeError):
        return True
    after = tomllib.loads((root / PYPROJECT).read_text(encoding="utf-8"))
    return shipped_metadata(before) != shipped_metadata(after)


def check_versions(root: Path, base: str) -> tuple[list[str], Findings]:
    version, findings = validate(root)
    merge_base, changed = changed_files(root, base)
    shipped = [f for f in changed if is_shipped(f)]
    if PYPROJECT in changed and project_table_changed(root, merge_base):
        shipped.append(f"{PYPROJECT} [project]")
    if not shipped:
        return [], findings
    report: list[str] = []
    try:
        head = Version.parse(version or "")
    except ValueError:
        return [f"{len(shipped)} shipped file(s) changed; version unreadable"], findings
    try:
        previous_text = read_version(git(root, "show", f"{merge_base}:{VERSION_FILE}"))
        previous = Version.parse(previous_text or "")
    except (GitError, ValueError):
        findings.warning(VERSION_FILE, "could not read the base version; skipping the bump check")
        report.append(f"{PACKAGE}: ? -> {head}")
    else:
        if head > previous:
            report.append(f"{PACKAGE}: {previous} -> {head}")
        else:
            findings.error(
                VERSION_FILE,
                f"{len(shipped)} shipped file(s) changed but the version is still {head} "
                f"(base {previous}); bump it per docs/versioning-and-releases.md",
                1,
            )
            report.append(f"{PACKAGE}: {previous} -> {head} (needs a bump)")
    log = root / CHANGELOG
    if not log.is_file() or changelog_section(log.read_text(encoding="utf-8"), str(head)) is None:
        findings.error(CHANGELOG, f"add a '## [{head}] - YYYY-MM-DD' section for this change")
    report.extend(f"  changed: {f}" for f in shipped[:20])
    if len(shipped) > 20:
        report.append(f"  … and {len(shipped) - 20} more")
    return report, findings


# --------------------------------------------------------------------------- #
# Packaging and releases
# --------------------------------------------------------------------------- #


def tag_for(version: str) -> str:
    return f"{TAG_PREFIX}{version}"


def write_checksum(path: Path) -> Path:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    out = path.with_name(path.name + ".sha256")
    out.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return out


def package(root: Path, version: str, out_dir: Path) -> list[Path]:
    """Build the sdist and wheel into out_dir and write a .sha256 for each.

    SOURCE_DATE_EPOCH is pinned to the HEAD commit time, so rebuilding the
    same commit gives the same archive timestamps.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob(f"{PACKAGE}-*"):
        stale.unlink()
    env = dict(os.environ)
    try:
        env.setdefault("SOURCE_DATE_EPOCH", git(root, "log", "-1", "--format=%ct").strip())
    except GitError:
        pass
    subprocess.run(
        [sys.executable, "-m", "build", "--sdist", "--wheel", "--outdir", str(out_dir), str(root)],
        check=True,
        env=env,
    )
    artifacts = sorted(
        p for p in out_dir.iterdir() if p.name.startswith(f"{PACKAGE}-{version}") and p.suffix != ".sha256"
    )
    if len(artifacts) != 2:
        raise RuntimeError(f"expected an sdist and a wheel for {version}, found {[p.name for p in artifacts]}")
    return artifacts + [write_checksum(p) for p in artifacts]


def is_released(root: Path, version: str) -> bool:
    return tag_for(version) in set(git(root, "tag", "--list").split())


def release_notes(root: Path, version: str) -> str:
    notes = changelog_section((root / CHANGELOG).read_text(encoding="utf-8"), version) or "See CHANGELOG.md."
    return notes + (
        "\n\n---\n\nInstall from the attached wheel: "
        f"`pip install {PACKAGE}-{version}-py3-none-any.whl` "
        "(add extras such as `[pdf]` or `[ai]` as described in the README). "
        "Check the download against its `.sha256` file. "
        "Estimates only: ouch is not tax advice."
    )


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def cmd_validate(args) -> int:
    version, findings = validate(args.root)
    findings.emit()
    print(f"{PACKAGE} {version}: {len(findings.errors)} error(s), {len(findings.warnings)} warning(s)")
    if findings.errors or (args.strict and findings.warnings):
        return 1
    return 0


def cmd_check_versions(args) -> int:
    try:
        report, findings = check_versions(args.root, args.base)
    except GitError as exc:
        print(f"error: {exc}\nFetch the base branch with full history (actions/checkout fetch-depth: 0).")
        return 1
    for line in report or ["no shipped files changed; no version bump needed"]:
        print(line)
    findings.emit()
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and report:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("### Package version\n\n" + "\n".join(f"- {line.strip()}" for line in report) + "\n")
    return 1 if findings.errors else 0


def cmd_package(args) -> int:
    version, findings = validate(args.root)
    if findings.errors or version is None:
        findings.emit()
        print("fix the errors above before packaging")
        return 1
    for path in package(args.root, version, args.out):
        print(path.relative_to(args.root) if path.is_relative_to(args.root) else path)
    return 0


def cmd_release(args) -> int:
    version, findings = validate(args.root)
    if findings.errors or version is None:
        findings.emit()
        print("refusing to release with validation errors")
        return 1
    tag = tag_for(version)
    if is_released(args.root, version):
        print(f"{tag} is already released; nothing to do")
        return 0
    target = os.environ.get("GITHUB_SHA") or git(args.root, "rev-parse", "HEAD").strip()
    notes = release_notes(args.root, version)
    command = ["gh", "release", "create", tag, "--title", f"{PACKAGE} {version}", "--target", target]
    if Version.parse(version).is_prerelease:
        command.append("--prerelease")
    if args.dry_run:
        print(f"would release {tag} from {target[:12]}:\n  {shlex.join(command)} <sdist, wheel, .sha256>")
        print("  notes:\n    " + notes.replace("\n", "\n    "))
        return 0
    assets = [str(p) for p in package(args.root, version, args.out)]
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(notes)
    try:
        subprocess.run([*command, *assets, "--notes-file", fh.name], check=True)
    finally:
        os.unlink(fh.name)
    print(f"released {tag}")
    return 0


def cmd_notes(args) -> int:
    version = args.version or validate(args.root)[0]
    section = changelog_section((args.root / CHANGELOG).read_text(encoding="utf-8"), version or "")
    if section is None:
        print(f"no changelog section for {version}", file=sys.stderr)
        return 1
    print(section)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="relkit", description=__doc__.split("\n")[0])
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="repository root")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="check the version, pyproject wiring and CHANGELOG.md")
    p.add_argument("--strict", action="store_true", help="treat warnings as errors")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("check-versions", help="require a version bump when shipped files change")
    p.add_argument("--base", default="origin/main", help="git ref to compare with (default origin/main)")
    p.set_defaults(func=cmd_check_versions)

    p = sub.add_parser("package", help="build the sdist and wheel")
    p.add_argument("--out", type=Path, help="output directory (default: <root>/dist)")
    p.set_defaults(func=cmd_package)

    p = sub.add_parser("release", help="publish a GitHub release for the current version if untagged")
    p.add_argument("--dry-run", action="store_true", help="print the plan without building or publishing")
    p.add_argument("--out", type=Path, help="output directory (default: <root>/dist)")
    p.set_defaults(func=cmd_release)

    p = sub.add_parser("notes", help="print a version's changelog section")
    p.add_argument("--version", help="defaults to the current version")
    p.set_defaults(func=cmd_notes)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.root = args.root.resolve()
    if hasattr(args, "out"):
        args.out = args.out.resolve() if args.out else args.root / "dist"
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
