"""Lightweight client for the StatsBomb Open Data HTTP API.

This client is intentionally minimal and focuses on the subset we need for
the ingestion pipeline:

- List matches for a given competition + season

Authentication:
StatsBomb Open data currently does not require auth tokens, but we
nevertheless read ``STATSBOMB_BASE_URL`` from the environment so the
endpoint can be overridden if needed.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx


# Default to official StatsBomb Open Data GitHub raw URLs.
# Docs: https://github.com/statsbomb/open-data
DEFAULT_BASE_URL = (
    "https://raw.githubusercontent.com/statsbomb/open-data/master/data/"
)


class StatsBombClient:
    """HTTP client wrapper for StatsBomb Open GitHub data.

    This uses the public open-data repository layout, e.g.::

        data/matches/{competition_id}/{season_id}.json

    ``STATSBOMB_BASE_URL`` can be overridden to point at a mirror or
    local cache if desired.
    """

    def __init__(self, base_url: str | None = None, timeout: float = 10.0):
        self.base_url = base_url or os.getenv("STATSBOMB_BASE_URL", DEFAULT_BASE_URL)
        if not self.base_url.endswith("/"):
            self.base_url += "/"
        self.timeout = timeout
        self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def close(self) -> None:
        self._client.close()

    def get_matches(self, competition_id: int, season_id: int) -> List[Dict[str, Any]]:
        """Return match list for a competition + season from GitHub.

        StatsBomb Open stores match lists at::

            data/matches/{competition_id}/{season_id}.json

        We keep the relative path configurable via ``STATSBOMB_MATCHES_PATH``
        for flexibility, but default to the official layout.
        """

        path_template = os.getenv(
            "STATSBOMB_MATCHES_PATH",
            "matches/{competition_id}/{season_id}.json",
        )
        # ``base_url`` already ends with ``data/``; we just append the
        # relative ``matches/...`` component.
        path = path_template.format(competition_id=competition_id, season_id=season_id)

        resp = self._client.get(path)
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, list):
            raise ValueError("Expected list of matches from StatsBomb Open data")

        return data

    def get_competitions(self) -> List[Dict[str, Any]]:
        """Return all available competitions from StatsBomb Open Data.

        StatsBomb Open stores competitions at::

            data/competitions.json

        The relative path may be overridden with ``STATSBOMB_COMPETITIONS_PATH``.
        """

        path_template = os.getenv(
            "STATSBOMB_COMPETITIONS_PATH",
            "competitions.json",
        )
        path = path_template

        resp = self._client.get(path)
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, list):
            raise ValueError("Expected list of competitions from StatsBomb Open data")

        return data

    def get_competition_seasons(self, competition_id: int) -> List[Dict[str, Any]]:
        """Return seasons for a given competition from competitions listing."""

        competitions = self.get_competitions()
        return [c for c in competitions if c.get("competition_id") == competition_id]

    def get_events(self, match_id: int) -> List[Dict[str, Any]]:
        """Return event list for a given match from GitHub.

        StatsBomb Open stores event files at::

            data/events/{match_id}.json

        The relative path may be overridden with ``STATSBOMB_EVENTS_PATH``.
        """

        path_template = os.getenv(
            "STATSBOMB_EVENTS_PATH",
            "events/{match_id}.json",
        )
        path = path_template.format(match_id=match_id)

        resp = self._client.get(path)
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, list):
            raise ValueError("Expected list of events from StatsBomb Open data")

        return data

    def get_lineups(self, match_id: int) -> List[Dict[str, Any]]:
        """Return lineup payload for a given match from GitHub.

        StatsBomb Open stores lineup files at::

            data/lineups/{match_id}.json

        The relative path may be overridden with ``STATSBOMB_LINEUPS_PATH``.
        """

        path_template = os.getenv(
            "STATSBOMB_LINEUPS_PATH",
            "lineups/{match_id}.json",
        )
        path = path_template.format(match_id=match_id)

        resp = self._client.get(path)
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, list):
            raise ValueError("Expected list of lineups from StatsBomb Open data")

        return data

