import os

import httpx

from src.ingestion.statsbomb_client import StatsBombClient


def test_get_matches_builds_expected_url_and_handles_404(monkeypatch):
    """Ensure ``get_matches`` hits the expected relative path.

    We don't rely on specific open-data files existing; instead we point
    at a clearly non-existent competition/season and assert that a clean
    HTTP 404 is surfaced from httpx.
    """

    # Force a deterministic base URL so we know what will be requested
    monkeypatch.setenv(
        "STATSBOMB_BASE_URL",
        "https://raw.githubusercontent.com/statsbomb/open-data/master/data/",
    )

    client = StatsBombClient()
    try:
        # Use obviously invalid IDs to avoid depending on repo contents
        try:
            client.get_matches(9999, 9999)
            # If no error is raised, something is off with URL handling
            assert False, "Expected HTTPStatusError for non-existent file"
        except httpx.HTTPStatusError as exc:
            # Confirm we requested the matches/{competition}/{season}.json path
            url = str(exc.response.request.url)
            assert "matches/9999/9999.json" in url
    finally:
        client.close()


def test_get_lineups_builds_expected_url_and_handles_404(monkeypatch):
    """Ensure ``get_lineups`` requests the lineups path and bubbles HTTP errors."""

    monkeypatch.setenv(
        "STATSBOMB_BASE_URL",
        "https://raw.githubusercontent.com/statsbomb/open-data/master/data/",
    )

    client = StatsBombClient()
    try:
        try:
            client.get_lineups(9999)
            assert False, "Expected HTTPStatusError for non-existent lineup file"
        except httpx.HTTPStatusError as exc:
            url = str(exc.response.request.url)
            assert "lineups/9999.json" in url
    finally:
        client.close()
