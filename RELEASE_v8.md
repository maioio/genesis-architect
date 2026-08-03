# Release runbook: v8.0.0

Everything is committed on `release/v8.0.0-open-source` and pushed. Nothing is
live yet. This is the order to ship it in.

---

## Order matters

The website says `pip install genesis-architect` and "free, AGPL-3.0". Until
PyPI actually has 8.0.0, anyone following that gets **5.4.1**, which is the old
MIT open-core build that still expects a Pro licence for the advanced engines.

**So: PyPI first, site second.** The site ships from `main:docs/`, so merging
this branch into `main` publishes the new site. Do not merge until the package
is up.

---

## 1. Open the PR and let CI run

```bash
gh pr create \
  --repo maioio/genesis-architect \
  --base main \
  --head release/v8.0.0-open-source \
  --title "v8.0.0 - Genesis Architect is now fully free and open source" \
  --body-file CHANGELOG.md
```

Wait for green. The workflow now runs a Python 3.11/3.12/3.13 matrix, a
packaged-install job in Docker, and a build job that checks the wheel actually
contains its data files.

## 2. Build and publish to PyPI

Do this **before** merging, so the install command on the site is true the
moment the site goes live.

```bash
# from a clean checkout of the branch
python -m pip install -U build twine
rm -rf dist/ build/
python -m build
twine check dist/*

# dry run against TestPyPI first if you want a rehearsal
twine upload --repository testpypi dist/*

# the real thing
twine upload dist/*
```

Then verify in a throwaway container, not on your own machine:

```bash
docker run --rm python:3.11-slim sh -c '
  pip install -q genesis-architect &&
  genesis --help >/dev/null &&
  genesis license &&
  python -c "import genesis_architect, genesis_architect.pro; print(genesis_architect.__version__)"
'
```

That must print `8.0.0` and say the tool is free. If `genesis init` errors on a
missing `folder-structures.toml`, the package data did not ship: stop and fix
before going further. (That exact bug is why the CI wheel check exists.)

## 3. Merge, tag, release

```bash
gh pr merge --squash --repo maioio/genesis-architect   # or merge in the UI

git checkout main && git pull
git tag -a v8.0.0 -m "v8.0.0 - fully free and open source"
git push origin v8.0.0

gh release create v8.0.0 \
  --title "v8.0.0 - Genesis Architect is now fully free and open source" \
  --notes-file RELEASE_NOTES_v8.md \
  dist/*
```

Merging to `main` also publishes the new site. Give Pages a couple of minutes,
then hard-refresh <https://maioio.github.io/genesis-architect/>.

## 4. Retire the paid funnel

- Unpublish or redirect the two Gumroad products (`dduhm`, `kzbpct`). Anyone
  landing there should be pointed at the GitHub repo, not a dead checkout.
- Archive `maioio/genesis-architect-pro` with a README pointing here. Do not
  delete it; the commit history is part of the project's story.
- Delete `~/.claude/skills/genesis-architect-pro-keys/` only once you are sure
  no old signed licence needs verifying. Nothing in the codebase reads it now.
- `.github/FUNDING.yml` still points at GitHub Sponsors and Buy Me a Coffee.
  Those stay: donations are the honest revenue path for a free tool.

---

## Post-release checks

```bash
# the site is not advertising a version that does not exist
curl -s https://pypi.org/pypi/genesis-architect/json | python -c "import sys,json; print(json.load(sys.stdin)['info']['version'])"

# GitHub shows the licence correctly (should say AGPL-3.0)
gh api repos/maioio/genesis-architect --jq .license.spdx_id
```

---

## Then: the launch post

The strongest thing about this project is not the feature list, it is the
concrete result: it reads real GitHub issues and turns them into mitigations
before you write code. Lead with that, and with the relicensing decision, which
is genuinely interesting to developers.

**Do not** post the feature matrix. It reads as marketing and gets downvoted.

### Hacker News (Show HN)

Post Tuesday to Thursday, roughly 09:00 to 11:00 ET. Title:

> Show HN: Genesis Architect - mines GitHub issues to find bugs before you write code

First comment, from you, in plain prose:

> I built this over the past months. It scans repos solving the problem you
> described, mines their closed issues for failures that keep recurring, and
> generates a scaffold with those mitigations already in place. Afterwards it
> sticks around to diagnose drift, score architecture and flag modules that are
> too fragile to touch.
>
> It used to be open-core with a $9/mo Pro tier. I never got it in front of
> enough people for that to mean anything, and the licence check was mostly
> creating work for me. As of v8.0.0 everything is free under AGPL-3.0. The
> decision engine, knowledge graph, threat modelling and the rest are all in the
> one package.
>
> Two bugs I found while preparing the release are worth mentioning because
> they only appear once you test the packaged install rather than the repo: the
> scaffolder read a data file by walking up to the repo root, so `pip install`
> shipped a version where `genesis init` could not even import; and the test
> suite was quietly running `pip install` mid-run, which mutated its own
> environment and made results depend on execution order.
>
> Happy to answer anything.

Then stay in the thread for several hours and answer every comment. That
matters more than the post.

### Reddit

`r/Python` (Saturday "Showcase" thread is safest), then `r/programming` and
`r/opensource`. Rewrite for each, never cross-post the same text. Reddit
punishes anything that reads like an ad; the honest "I tried charging for this
and it did not work, here is everything for free" angle is the part people
respond to.

### The one thing worth being careful about

AGPL-3.0 does what you asked for: it stops someone wrapping this as a paid SaaS
without publishing their changes. The tradeoff is that many companies have a
blanket ban on AGPL dependencies, so some developers will not adopt it at work.
For a CLI that runs locally the network clause almost never triggers in
practice, so it behaves like GPL for normal users.

If adoption matters more to you than that protection, Apache-2.0 is the usual
choice and you can still relicense later, since you hold the copyright. If the
protection matters more, keep AGPL. Both are defensible; you already chose, and
this is only here so the tradeoff is written down.
