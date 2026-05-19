"""Orchestrates: fetch feed -> filter new episodes -> download -> update state."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from podcast_dl.core.downloader import download_episode
from podcast_dl.core.fetcher import fetch_feed
from podcast_dl.core.tracker import (
    is_downloaded, load_state, mark_downloaded, save_state,
)

log = logging.getLogger(__name__)


def sync_feed(
    feed_url: str,
    output_dir: Path,
    state_path: Path,
    max_workers: int = 3,
    limit: int | None = None,
) -> list[Path]:
    """Download all new episodes from feed_url. Returns list of new file paths."""
    feed = fetch_feed(feed_url)
    state = load_state(state_path)

    entries = feed.entries
    if limit:
        entries = entries[:limit]

    new_entries = [
        e for e in entries
        if e.get("enclosures")
        and not is_downloaded(e.enclosures[0].get("href", ""), state)
    ]

    log.info("%d new episodes to download (of %d total)", len(new_entries), len(entries))

    downloaded: list[Path] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                download_episode,
                e.enclosures[0]["href"],
                e.get("title", "episode"),
                output_dir,
            ): e
            for e in new_entries
        }
        for future in as_completed(futures):
            entry = futures[future]
            url = entry.enclosures[0]["href"]
            try:
                path = future.result()
                mark_downloaded(url, state)
                downloaded.append(path)
            except Exception as exc:
                log.error("Failed to download %r: %s", url, exc)

    if downloaded:
        save_state(state_path, state)

    return downloaded
