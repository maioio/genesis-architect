# Genesis Architect Pro — clean-room E2E validation.
#
# Built via ./run.sh, which stages the build context (Docker cannot reach
# outside it). See README.md.
#
# The point of this image is that it has NOTHING pre-provisioned: no voice
# packages, no STT/TTS models, no ~/.genesis, and no TTY. Every developer
# machine here has the voice extra installed, which hides a whole class of
# bug — `genesis companion --ui` used to pip-install 9 packages and download
# ~1-2 GB of models before returning, and looked instant locally because
# there was nothing left to fetch. This is the only place that shows.
ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# git is a real runtime dependency: the history-intelligence engines shell out
# to it. Without it those engines degrade instead of being exercised.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Which genesis-architect core to test against. `pypi` installs the published
# dependency a real user would resolve; `local` uses a core checkout staged
# into the context by run.sh, for testing an unreleased core.
ARG CORE_SOURCE=pypi
ARG CORE_VERSION=

COPY core/ ./core/
RUN if [ "$CORE_SOURCE" = "local" ]; then \
        pip install --no-cache-dir -e ./core; \
    else \
        pip install --no-cache-dir "genesis-architect${CORE_VERSION:+==$CORE_VERSION}"; \
    fi

COPY pro/ ./pro/
RUN pip install --no-cache-dir -e "./pro[dev]"

COPY e2e.sh /usr/local/bin/e2e
COPY r1_r6_e2e.py /usr/local/bin/r1_r6_e2e.py
COPY symlink_containment.py /usr/local/bin/symlink_containment.py
RUN chmod +x /usr/local/bin/e2e

# Engines that read git history need a usable git identity.
RUN git config --global user.email "ci@genesis.local" \
    && git config --global user.name "Genesis CI" \
    && git config --global init.defaultBranch main

WORKDIR /app/pro
CMD ["e2e"]
