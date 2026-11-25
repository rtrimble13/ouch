# Versioning and releases

ouch is versioned with [Semantic Versioning](https://semver.org/), and each new version is released automatically when it reaches `main`.

## Contents

- [What is versioned](#what-is-versioned)
- [What MAJOR, MINOR and PATCH mean for ouch](#what-major-minor-and-patch-mean-for-ouch)
- [Changelog](#changelog)
- [The version gate in CI](#the-version-gate-in-ci)
- [How a release happens](#how-a-release-happens)
- [Pre-releases](#pre-releases)
- [Fixing a bad release](#fixing-a-bad-release)
- [Tooling](#tooling)
- [Recommended repository settings](#recommended-repository-settings)

## What is versioned

| Thing | Version lives in | Example | Changed when |
|---|---|---|---|
| The package | `__version__` in `ouch/__init__.py` (the single source; `pyproject.toml` reads it) | `"0.1.0"` | Any change to a shipped file: anything under `ouch/`, including the tax data and PDF maps, or the `[project]` table of `pyproject.toml` |
| Profile format | `PROFILE_SCHEMA_VERSION` in `ouch/config/profile.py` | `2` | A profile written for this version would be misread by an older ouch |
| Tax-data format | `meta.schema_version` in each data file, and `SUPPORTED_SCHEMA_VERSIONS` in `ouch/taxdata/schema.py` | `3` | The data-file schema changes incompatibly |
| JSON output | `JSON_SCHEMA_VERSION` in `ouch/render/json_out.py` | `1` | `--format json` changes incompatibly (an added field doesn't count) |
| The repository (tests, CI, docs) | Not versioned | | Logged only if it matters to users |

The schema versions are separate contracts with their own readers: a profile, a user's tax-data override, a script that parses JSON. Bumping one of them is itself at least a MINOR change to the package, and usually MAJOR.

Tax data also has a provenance flag, `meta.verified`, which isn't a version. It flips per file under the spec's appendix D checklist. Flipping it, or citing a new source, is a package change like any other.

## What MAJOR, MINOR and PATCH mean for ouch

ouch is a contract between the project and the people who plan around its numbers. Bump for the strongest effect the change has on that contract.

| Bump | Meaning | Examples |
|---|---|---|
| **MAJOR** (`2.0.0`) | A figure changes for an existing profile and tax year, or an interface breaks. Estimates made before and after aren't comparable, or something downstream stops working. | Correcting a calculation, even a plain bug. Correcting shipped tax data. A new provision applied to years that already have data, such as the 2025 senior deduction. A profile, scenario or config change that old files no longer satisfy. Removing or renaming a command, option or JSON field. Changing what an exit code means. Dropping a tax year, a jurisdiction or a supported data `schema_version`. Raising the minimum Python. |
| **MINOR** (`1.1.0`) | New capability that leaves every existing figure unchanged | A new command or option. A new optional profile field. A new tax year (for example `federal/2027.yaml`) or a new state. An additive JSON field. A new optional data-schema section that no shipped file uses yet. A new optional extra. |
| **PATCH** (`1.0.1`) | No intended change to any figure or interface | Wording of messages, help text or warnings. A crash fixed where ouch used to fail loudly. Performance. Refactoring. A packaging fix. |

A fix that moves numbers is MAJOR. It's a fix, but people comparing this year's estimate with last month's need to know their numbers changed. Say so plainly in the changelog: who is affected, in which direction, and roughly by how much.

**Before 1.0.0** ouch is in development, and the bumps shift down one place: a change that would be MAJOR bumps MINOR (`0.1.0` → `0.2.0`), and everything else bumps PATCH (`0.1.0` → `0.1.1`). The changelog rule doesn't shift: number-moving changes are still called out.

## Changelog

[CHANGELOG.md](../CHANGELOG.md) is in [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format:

```markdown
## [Unreleased]

## [0.2.0] - 2026-12-15

### Added

- The 2025–2028 enhanced deduction for seniors (Schedule 1-A Part V).

### Changed

- Filers aged 65 or older in 2025 and 2026 see a lower federal tax: up to
  $6,000 less taxable income per person, phasing out above $75,000 MAGI.
```

`relkit validate` enforces these rules:

- An optional `## [Unreleased]` section comes first. Use it to collect notes while a change is in progress.
- Every version has a section `## [x.y.z] - YYYY-MM-DD`, listed newest first.
- The newest version section matches `__version__`.

Use the standard categories: **Added**, **Changed**, **Deprecated**, **Removed**, **Fixed**, **Security**. Write for users: say what ouch now computes or does differently, and cite the form, publication or section of the manual it affects. A version's section becomes the text of its GitHub release.

## The version gate in CI

On every pull request, `relkit check-versions` compares the branch with its base:

1. It lists the files the pull request changes, including uncommitted and untracked ones when run locally.
2. If any shipped file changed, it requires two things:
   - `__version__` is greater than the version on the base branch;
   - `CHANGELOG.md` has a section for the new version.
3. Changes only to tests, docs, CI, `scripts/`, tool configuration in `pyproject.toml` or the `dev` extra need no bump.

Run it locally before pushing. The pre-push hook also runs it:

```bash
make versions
```

## How a release happens

```text
PR with version bump ──► CI passes ──► merge to main ──► release workflow
                                                          1. runs the tests and validates the tax data
                                                          2. checks whether tag v<version> exists
                                                          3. builds the sdist and wheel, with .sha256 files
                                                          4. creates the tag and GitHub release, with the
                                                             changelog section as release notes
```

- **Tag:** `v<version>`, for example `v0.2.0`, at the merge commit.
- **Assets:** `ouch-0.2.0.tar.gz`, `ouch-0.2.0-py3-none-any.whl`, and a `.sha256` file for each.
- **Idempotent:** a version that already has a tag is skipped. Re-running the workflow, or merging a docs-only change, releases nothing.
- **Reproducible timestamps:** packages are built with `SOURCE_DATE_EPOCH` set to the commit time.

To preview what the next merge would release:

```bash
make release-plan
```

The workflow can also be started by hand from the Actions tab (`workflow_dispatch`), for example after a transient failure.

ouch isn't published to PyPI. Install a release from its wheel:

```bash
pip install ouch-0.2.0-py3-none-any.whl
```

## Pre-releases

Versions use the [PEP 440](https://peps.python.org/pep-0440/) pre-release forms `aN`, `bN` and `rcN`, for example `0.2.0rc1`, so the version, the wheel name and the tag all agree. `relkit` accepts exactly `MAJOR.MINOR.PATCH` with an optional one of those suffixes.

A pre-release is published as a GitHub **pre-release**. `0.2.0a1 < 0.2.0b1 < 0.2.0rc1 < 0.2.0`, and the version gate respects that order. Use one to let people try a candidate, such as a tax-data update, before it is final.

## Fixing a bad release

Releases are immutable: don't delete or move tags, because people and scripts may have pinned them.

1. Fix forward. Open a pull request with the fix and a new version, and merge it. It's MAJOR (MINOR before 1.0) if the fix moves numbers, PATCH otherwise. The release workflow publishes it.
2. Mark the bad release on GitHub. Edit its notes to point to the fixed version. If its numbers are wrong, tick "Set as a pre-release" so that it no longer shows as the latest.
3. Explain what was wrong in the new version's changelog section, under **Fixed**, including who was affected.

## Tooling

`scripts/relkit.py` is a single-file command-line tool that uses only the standard library (plus `build` for packaging). `--root` points it at another checkout. By default it works on the repository it lives in.

| Command | Purpose | Notable options |
|---|---|---|
| `validate` | Check `__version__`, the pyproject wiring and `CHANGELOG.md`. Exit 1 on any error. | `--strict` also fails on warnings |
| `check-versions` | The version gate, against the merge base | `--base origin/main` |
| `package` | Build the sdist and wheel, with a `.sha256` for each | `--out DIR` (default `dist/`) |
| `release` | If `v<version>` has no tag, package and create the GitHub release with `gh`. Needs `GH_TOKEN`. | `--dry-run` |
| `notes` | Print a version's changelog section | `--version X.Y.Z` |

Inside GitHub Actions, findings print as `::error` and `::warning` annotations on the affected file and line.

| `make` target | Does |
|---|---|
| `make install` | Installs ouch with the dev extra, and the pre-commit and pre-push hooks |
| `make check` | Everything CI runs on a pull request: validate, versions, test, data |
| `make test` / `make data` | pytest / `ouch data validate` |
| `make validate` / `make versions` | `relkit validate` / the version gate against `BASE` (default `origin/main`) |
| `make package` | Builds into `dist/` |
| `make release-plan` | What the next merge to `main` would release |
| `make notes` | The current version's changelog section |
| `make clean` | Removes `dist/`, build output and caches |

The hooks in `.pre-commit-config.yaml` run `relkit validate` when the version, pyproject or changelog changes (pre-commit), and the version gate (pre-push).

CI (`.github/workflows/ci.yml`) runs on every pull request and every push to `main`:

| Job | Runs |
|---|---|
| *Tests (Python 3.11 / 3.12 / 3.13)* | pytest, including the golden fixtures; `ouch data validate` |
| *Version and package* | `relkit validate`; the version gate (pull requests only); `relkit package`; uploads `dist/` as the `ouch-dist` artifact for 14 days |

The release workflow (`.github/workflows/release.yml`) runs on pushes to `main` that touch `ouch/`, `pyproject.toml` or `CHANGELOG.md`, and on demand. Dependabot keeps the pinned actions current.

## Recommended repository settings

These are set in GitHub, not in files:

- **Branch protection on `main`:** require a pull request, at least one approving review (CODEOWNERS), and the status checks *Tests (Python 3.11)*, *Tests (Python 3.12)*, *Tests (Python 3.13)* and *Version and package* to pass. Disallow force pushes.
- **Actions → Workflow permissions:** "Read repository contents" is enough. The release job asks for `contents: write` itself.
