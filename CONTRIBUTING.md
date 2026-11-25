# Contributing

Thank you for helping improve ouch. This page covers the workflow. The details are in [docs/](docs/).

## Setup

```bash
git clone https://github.com/rtrimble13/ouch.git
```

```bash
cd ouch && python3 -m venv .venv && source .venv/bin/activate && make install
```

You need Python 3.11 or later. `make install` installs ouch in editable mode with the `dev` extra, and adds pre-commit and pre-push hooks that run the same version checks as CI.

## Workflow

1. Create a branch from `main`.
2. Make the change. For anything under `ouch/` (code, tax data, PDF maps) or the `[project]` table of `pyproject.toml`:
   - bump `__version__` in `ouch/__init__.py` according to [docs/versioning-and-releases.md](docs/versioning-and-releases.md);
   - add a section for the new version to [CHANGELOG.md](CHANGELOG.md).

   Tests, docs and CI changes need neither.
3. Run `make check`.
4. Open a pull request and fill in the template. CI must pass, and a code owner must approve.
5. After the merge, the release workflow tags and publishes the new version. You don't need to tag anything.

## Standards for tax content

ouch's failure mode is a plausible wrong number, so changes to law, data and calculations get the same scrutiny as code:

- Cite a primary source for every figure, threshold and rule: IRS form instructions, publications, Revenue Procedures, the statute, or the state's revenue department. Name it in the data file's `meta.source` and in the pull request.
- Don't take figures from memory or from secondary summaries. If something can't be confirmed, say so and leave it unconfirmed.
- Derive new test expectations by hand, and show the working in the test's docstring. A fixture produced by ouch is not a fixture (spec §19).
- Disclose anything not modelled with a warning and `fidelity: approximate`. Never let it silently compute as zero.
- A change that moves figures is MAJOR (MINOR before 1.0), even when it fixes a bug. Say in the changelog who will see their numbers change.

## Commits

Write commit messages in the imperative ("Add the senior deduction"), and explain why in the body. Keep unrelated changes in separate commits, so reviewers can tell a refactor from a change in the numbers.

## AI-assisted contributions

Contributions written with AI assistance are welcome, and held to the same standards. You are responsible for every line: read the diff, check figures against the cited sources, and run the tests.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
