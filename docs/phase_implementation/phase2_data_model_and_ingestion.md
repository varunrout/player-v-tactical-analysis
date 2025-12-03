# Phase 2 – Data Model & Ingestion Pipeline

This document explains how Phase 2 is implemented: the objectives, design ideas, and the concrete code paths that now ingest StatsBomb Open data and populate the warehouse‑style schema.

---

## 1. Objectives

Phase 2 turns the Phase 1 concepts into a concrete data backbone. The main goals are:

1. **Define a relational data model** that can support all evolution metrics and features from Phase 1.
2. **Implement an ingestion pipeline** from StatsBomb Open data into this model.
3. **Separate concerns into layers**:
   - Raw JSON capture (source‑faithful).
   - Staging (normalized, source‑specific parsing handled).
   - Dimensions and facts (analysis‑friendly schema).
4. **Make the datastore pluggable** with SQLite as the default but no hard coupling.
5. **Provide at least one fully working path**: Matches & events from StatsBomb → Raw → Staging → Facts & Entities.

---

## 2. High-Level Architecture

Phase 2 centers around three modules:

- `src/ingestion/schemas.py` – ORM models for raw, staging, dimensions, facts, and history.
- `src/ingestion/db.py` – database bootstrap and session helper.
- `src/ingestion/pipeline.py` – ETL jobs (ingest, stage, entities, fact loaders, pipeline orchestrator).
- `src/ingestion/statsbomb_client.py` – thin HTTP client for StatsBomb Open (matches, events, and lineups).

### 2.1. Layered Schema Design

The schema is deliberately layered:

- **Raw layer** (`raw_*` tables):
  - `RawMatch`, `RawEvent`, `RawLineup`, `RawPlayer`, `RawTeam`.
  - Stores source JSON as‑is (plus metadata fields like `source`, `source_*_id`, `ingested_at`, `processed`).
- **Staging layer** (`stg_*` tables):
  - `StgMatch`, `StgEvent`, `StgPlayer`, `StgTeam`.
  - Stores normalized fields in a consistent, source‑agnostic format (IDs, dates, scores, locations, event types, etc.).
- **Dimension layer** (`dim_*` tables):
  - `DimTeam`, `DimPlayer`, `DimManager`, `DimSeason`, `DimCompetition`.
  - Assign stable surrogate keys and hold slowly changing attributes.
- **Fact layer** (`fact_*` tables):
  - `FactMatch`, `FactEvent`, `FactLineup`.
  - Designed for analysis and feature engineering, linking to dimensions via surrogate keys.
- **History tables**:
  - `TeamManagerHistory`, `PlayerTransferHistory` for natural experiments in Phase 1.

This structure is what lets us compute PPDA, xG/shot, build‑up metrics, and player/tactic features in later phases.

---

## 3. Database Bootstrap & Configuration

### 3.1. `src/ingestion/db.py`

Key components:

- `get_database_url()`:
  - Returns `DATABASE_URL` env var if set; otherwise falls back to:
    - `sqlite:///data/core/evolution.db`.
  - Ensures `data/core/` exists.
- `ENGINE`, `SessionLocal`:
  - Configured via SQLAlchemy using the URL above.
- `init_db()`:
  - Calls `Base.metadata.create_all(bind=ENGINE)` to create all tables from `schemas.py`.
- `get_session()`:
  - Context manager that yields a `Session` and handles commit/rollback/close.

**Design choice:**

- SQLite is the default for development and reproducibility.
- Production can swap in Postgres (or others) by setting `DATABASE_URL`, without changing ingestion code.

---

## 4. StatsBomb Open Client

### 4.1. `src/ingestion/statsbomb_client.py`

The client is intentionally tiny and aligned with the official open‑data GitHub repo:

- **Base URL:**
  - Default: `https://raw.githubusercontent.com/statsbomb/open-data/master/data/`.
  - Overridable with `STATSBOMB_BASE_URL`.
- **Matches endpoint:**
  - `get_matches(competition_id: int, season_id: int)`:
    - Requests `matches/{competition_id}/{season_id}.json` (relative to `data/`).
    - Path overridable via `STATSBOMB_MATCHES_PATH`.
    - Returns a list of match dicts.
- **Events endpoint:**
  - `get_events(match_id: int)`:
    - Requests `events/{match_id}.json`.
    - Path overridable via `STATSBOMB_EVENTS_PATH`.
    - Returns a list of event dicts.
- **Lineups endpoint:**
  - `get_lineups(match_id: int)`:
    - Requests `lineups/{match_id}.json`.
    - Path overridable via `STATSBOMB_LINEUPS_PATH`.
    - Returns the per-team lineup payloads used downstream for player metadata and FactLineup creation.

**Testing:**

- `tests/unit/test_statsbomb_client.py` validates URL construction and clean handling of HTTP 404s for both matches and lineups without relying on any particular file being present.

---

## 5. Ingestion Jobs – Raw Layer

### 5.1. `JobIngestMatches`

Location: `src/ingestion/pipeline.py`.

**Purpose:** Pull match lists from StatsBomb Open and populate `RawMatch`.

- **Inputs:** `PipelineConfig(source="statsbomb")`, `start_date`, `end_date`, `competition_ids`.
- **Extract:**
  - Only supports `source == "statsbomb"` currently.
  - Infers a simple `season_year` from the year of `end_date`.
  - Calls `StatsBombClient.get_matches(competition_id, season_year)` for each competition.
- **Transform:**
  - For each match dict, constructs a record with:
    - `source`.
    - `source_match_id` from `id` / `match_id`.
    - `raw_json` as a string.
    - `ingested_at` timestamp.
    - `processed=False`.
- **Load:**
  - Uses `get_session()` and `RawMatch`.
  - Upsert semantics on `(source, source_match_id)`:
    - If row exists: update `raw_json`, reset `processed=False`, update `ingested_at`.
    - Else: insert new `RawMatch`.

### 5.2. `JobIngestEvents`

**Purpose:** Pull per‑match event streams from StatsBomb Open into `RawEvent`.

- **Inputs:** `PipelineConfig`, optional `match_ids`.
- **Extract:**
  - Only active for `source == "statsbomb"`.
  - Match IDs come from:
    - Explicit `match_ids`, or
    - `_get_unprocessed_match_ids()`, which queries `RawMatch` for the configured source and returns all `source_match_id`s.
  - For each match ID, calls `StatsBombClient.get_events(match_id)` and attaches an auxiliary `"_match_id"` field before aggregating.
- **Transform:**
  - Builds records with:
    - `source`.
    - `source_event_id` from `id` / `event_id`.
    - `source_match_id` from `"_match_id"` or `match_id`.
    - `raw_json` string, `ingested_at`, `processed=False`.
- **Load:**
  - Inserts into `RawEvent` only if no existing row with `(source, source_event_id, source_match_id)`.
  - Stores parsed JSON in `raw_json` and sets `processed=False`.

This completes the **Raw** part of the matches + events path.

### 5.3. `JobIngestLineups`

**Purpose:** Capture StatsBomb lineup payloads per match/team into `RawLineup` so downstream entity staging and FactLineup construction have the richer roster context.

- **Extract:**
  - Supports StatsBomb by default.
  - Pulls explicit `match_ids` if provided; otherwise inspects `RawMatch` and `RawLineup` to find matches missing one or both team lineup records.
  - Calls `StatsBombClient.get_lineups(match_id)` once per match.
- **Transform:**
  - Splits the lineup payload into one record per team, preserving `team_id`, `team_name`, and the full `lineup` array.
- **Load:**
  - Upserts into `RawLineup` keyed by `(source, source_match_id, source_team_id)` and resets `processed=False` so derived jobs can re-run if new data arrives.
  - Stores JSON columns as parsed dicts and timestamps `ingested_at`.

---

## 6. Staging Jobs – Normalization

### 6.1. `JobStageMatches`

**Purpose:** Normalize StatsBomb (or other) match JSON into `StgMatch`.

- **Extract:**
  - Reads all unprocessed `RawMatch` rows for the current source.
  - Returns dicts with `id`, `source`, `source_match_id`, `raw_json`.
- **Transform:**
  - Parses `raw_json` and routes to `_parse_match(match_json, source)`:
    - `statsbomb` → `_parse_statsbomb_match`.
    - `wyscout` → `_parse_wyscout_match`.
    - fallback → `_parse_generic_match`.
  - StatsBomb parser now extracts an expanded set of metadata:
    - Team IDs and display names for both sides.
    - Competition IDs plus human-readable names and stages.
    - `season_name`, `match_date`, `kick_off`, and `match_week` when present.
    - Scores, normalized status, stadium, referee, attendance.
  - *Migration note:* If you populated the database before this enhancement, re-running `init_db()` (or issuing an `ALTER TABLE stg_match` with the new columns) is required so the additional attributes persist.
  - Adds `source` and `source_match_id` to the staged record.
- **Load:**
  - Inserts `StgMatch` rows with all normalized fields.
  - Marks corresponding `RawMatch` rows as processed using:
    - `RawMatch.source == staged["source"]` and `RawMatch.source_match_id == staged["source_match_id"]`.

### 6.2. `JobStageEvents`

**Purpose:** Normalize event JSON into `StgEvent`.

- **Extract:**
  - Reads all unprocessed `RawEvent` rows for the current source.
- **Transform:**
  - For each raw record, parses `raw_json` and routes to `_parse_event(event, source)`:
    - `statsbomb` → `_parse_statsbomb_event`.
      - Normalizes 120×80 coordinates to 0–100 scale.
      - Maps raw types via `EVENT_TYPE_MAPPING`.
      - Derives subtype (technique), outcome, extended success heuristics, xG, pass/shot metadata, progressive flags, possession IDs, and carry distance.
    - `wyscout` and generic branches preserved for future sources.
  - Adds `source`, `source_event_id`, `source_match_id`.
- **Load:**
  - Inserts into `StgEvent` with:
    - Event type/subtype, minute/second/period.
    - Start/end locations.
    - Player/team IDs.
    - Outcome, `is_successful`, and `extra_data` JSON.
  - Marks corresponding `RawEvent` rows as processed by `id`.

### 6.3. `JobStageEntities`

**Purpose:** Build staging tables for teams and players (`StgTeam`, `StgPlayer`).

- **Extract:**
  - Scans across raw tables for entities:
    - `RawMatch`: home/away team objects → team IDs and names.
    - `RawEvent`: `player` and `team` objects → IDs and names.
    - `RawLineup`: `lineup` arrays → richer per‑player metadata (names, birth_date, country, position) if present.
  - Deduplicates by internal keys (e.g., `"team:{id}"`, `"player:{id}"`) and returns a combined structure of `teams` and `players`.
- **Transform:**
  - Standardizes:
    - Teams: `source_team_id`, `name`, `short_name`, `country`.
    - Players: `source_player_id`, `name`, name components, DOB, nationality, position, physicals, preferred foot.
- **Load:**
  - Inserts into `StgTeam` and `StgPlayer`:
    - All rows tagged with `source` from `PipelineConfig`.

This gives us a clean staging layer for entity dimensions.

---

## 7. Dimension & Fact Construction

### 7.1. Dim Helpers

Defined in `pipeline.py`:

- `_get_or_create_dim_team(session, source, source_team_id, team_name=None, ...)`:
  - Uses StatsBomb IDs when present and falls back to staged team metadata so we always capture names/countries.
- `_get_or_create_dim_competition(session, name, source, source_id)`:
  - Uses `DimCompetition.statsbomb_id` for StatsBomb; `competition_name` otherwise.
- `_get_or_create_dim_season(session, season_name)`:
  - Looks up by `season_name`; if missing, parses a `"YYYY/YYYY"` string to approximate `start_date` and `end_date`.
- `_get_or_create_dim_player(session, source, source_player_id, fallback_name=None)`:
  - Builds `DimPlayer` rows on demand using the richer details captured in `StgPlayer`/lineup payloads.

### 7.2. `load_fact_matches_from_staging`

- Reads `StgMatch` for a given source.
- For each staged match:
  - Resolves dimension keys using helpers:
    - `DimTeam` (home/away).
    - `DimCompetition`.
    - `DimSeason`.
  - Checks for an existing `FactMatch` with `(source, source_match_id)`.
  - If not present, inserts a new `FactMatch` row with:
    - Dimension IDs.
    - Scores, date, time, matchweek, stadium, attendance, referee.
    - `source` and `source_match_id`.

This provides a full **Raw → Staging → Fact** path for matches, with dimensions (and now richer match metadata) attached.

### 7.3. `load_fact_events_from_staging`

- Reads `StgEvent` rows for a source.
- Resolves `FactMatch`, `DimTeam`, and `DimPlayer` IDs before inserting into `FactEvent`.
- Copies normalized coordinates plus enriched metadata such as xG, pass length/angle, carry distance, progressive flags, and under-pressure signals.
- Persists the original `extra_data` JSON for downstream feature builders.

### 7.4. `load_fact_lineups_from_raw`

- Scans `RawLineup` payloads and resolves the associated `FactMatch`/`DimTeam` rows.
- Builds/updates `FactLineup` entries for every player in the lineup, inferring starter flags, jersey numbers, positions, substitution times, and minutes played from StatsBomb's positional timelines.
- Marks processed lineup payloads so late re-ingests can be detected.

---

## 8. Pipeline Orchestration

### 8.1. `Pipeline` class

- Maintains a `PipelineConfig`, a list of jobs, and their `JobResult`s.
- `run()` executes jobs in sequence, halting on first failure.
- `run_full_ingestion(start_date, end_date, competition_ids)` sets up the Phase 2 pipeline:
  1. `JobIngestMatches` – StatsBomb matches → `RawMatch`.
  2. `JobIngestEvents` – StatsBomb events → `RawEvent`.
  3. `JobIngestLineups` – StatsBomb lineups → `RawLineup`.
  4. `JobStageMatches` – `RawMatch` → `StgMatch` + mark processed.
  5. `JobStageEvents` – `RawEvent` → `StgEvent` + mark processed.
  6. `JobStageEntities` – raw tables → `StgTeam` / `StgPlayer`.

You can also run jobs individually for more controlled ETL workflows.

---

## 9. Testing & Validation

Phase 2 implementation is backed by tests:

- **Unit tests:**
  - `tests/unit/test_statsbomb_client.py` – verifies the client hits both match and lineup endpoints and surfaces `httpx.HTTPStatusError` cleanly.
  - `tests/unit/test_pipeline_helpers.py` – covers lineup timing helpers so FactLineup minutes stay accurate.
  - Existing unit tests (`test_api.py`, `test_features.py`, `test_matchup.py`) remain green, ensuring Phase 2 changes don’t break downstream consumers.
- **Integration test (optional, HTTP):**
  - `tests/integration/test_ingestion_matches_statsbomb.py`:
    - Uses a temporary SQLite DB via `DATABASE_URL`.
    - Runs `JobIngestMatches`, `JobStageMatches`, and `load_fact_matches_from_staging` end‑to‑end.
    - Marked with a skip condition on `SKIP_STATSBOMB_HTTP` so CI doesn’t depend on live GitHub responses.

---

## 10. How Phase 2 Supports Later Phases

With Phase 2 complete, later phases can rely on:

- A **stable schema** matching the research needs from Phase 1.
- A **replayable ingestion pipeline** from StatsBomb Open to SQLite (or another DB).
- A **normalized staging layer** ready for feature engineering (Phase 3):
  - `StgMatch` and `StgEvent` provide clean inputs for computing PPDA, xG/shot, build‑up metrics, pressing metrics, and per‑player skill features.
- **Entity staging** for building robust dimensions and enabling longitudinal analyses (e.g., manager and player movement across teams/eras).

From here, Phase 3 will primarily focus on `src/features/engineering.py`, using the facts and staging tables from Phase 2 to compute the rich player‑skill and tactical features specified in `docs/research_framework.md`.
