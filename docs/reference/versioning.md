# Versioning and support policy

This page states how releases are numbered and what support to expect. It makes no promise
beyond what a single maintainer can keep. The current version is in
[`data/public-product-facts.json`](../../data/public-product-facts.json).

## Version numbers

Genesis follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

| Change | Bump |
|---|---|
| Wording, docs, template corrections | Patch |
| New feature, new language template, new MCP strategy | Minor |
| Breaking CLI or import surface change, or a change to the analysis rules that moves the numbers Genesis reports | Major |
| Change to the structure of the SKILL.md phases (0-7) | Major |

The 9.0.0 release is the worked example of the last row: the interface did not break, but the
scoring rules changed, so the major number moved. See [CHANGELOG.md](../../CHANGELOG.md).

## Stable line and branches

- `main` is the stable line. Every change to it arrives through a reviewed pull request.
- Feature work happens on short-lived branches. A branch is not a release.
- Pre-releases, if any, use a PEP 440 suffix such as `10.0.0rc1` and are not recommended for
  production use.

## PRE-v10 and v10

- **PRE-v10** is the name for preparation work toward the next major version. It lives outside
  `main`, is unreleased, and may change or be dropped.
- **v10** does not exist as a release. Nothing in this repository describes v10 behavior as
  current, and no document here is a commitment to ship it.

## Breaking changes and deprecation

- A breaking change goes in a major release and is listed under its own heading in the changelog.
- Where practical, a feature is marked deprecated in a release before it is removed. This is a
  best-effort practice, not a guarantee.

## Python support

Supported Python versions are those in `requires-python` in [pyproject.toml](../../pyproject.toml)
and exercised by the CI matrix in `.github/workflows/ci.yml`. A Python version is dropped in a
minor or major release, with a changelog note.

## Security support

Which versions receive security fixes, and how to report a vulnerability, is defined once in
[SECURITY.md](../../SECURITY.md). It is not repeated here, so it cannot drift.

## What is not promised

No release schedule, no long-term support branches, and no response-time guarantee beyond the
reporting window in SECURITY.md.
