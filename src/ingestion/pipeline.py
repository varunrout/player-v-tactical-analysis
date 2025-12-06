"""
ETL Pipeline for Football Data Ingestion

This module provides the core ETL jobs for:
- Fetching data from source APIs
- Flattening and loading raw JSON
- Staging layer transformations
- ID standardization and mapping
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.ingestion.db import get_session
from src.ingestion.schemas import (
    RawMatch,
    RawEvent,
    RawLineup,
    StgMatch,
    StgEvent,
    StgTeam,
    StgPlayer,
    FactMatch,
    FactEvent,
    FactLineup,
    DimCompetition,
    DimSeason,
    DimTeam,
    DimPlayer,
)
from src.ingestion.statsbomb_client import StatsBombClient
from src.utils import parse_extra_data

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for ETL pipeline."""
    source: str
    batch_size: int = 100
    retry_attempts: int = 3
    retry_delay_seconds: int = 5
    enable_validation: bool = True
    enable_deduplication: bool = True


@dataclass
class JobResult:
    """Result of an ETL job execution."""
    job_name: str
    status: str  # 'success', 'partial', 'failed'
    records_processed: int = 0
    records_failed: int = 0
    errors: List[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseETLJob(ABC):
    """Base class for all ETL jobs."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def extract(self) -> List[Dict[str, Any]]:
        """Extract data from source."""
        pass

    @abstractmethod
    def transform(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Transform extracted data."""
        pass

    @abstractmethod
    def load(self, data: List[Dict[str, Any]]) -> int:
        """Load transformed data to destination."""
        pass

    def run(self) -> JobResult:
        """Execute the ETL job."""
        result = JobResult(
            job_name=self.__class__.__name__,
            status='success',
            started_at=datetime.utcnow()
        )

        try:
            # Extract
            self.logger.info(f"Starting extraction for {self.config.source}")
            raw_data = self.extract()
            self.logger.info(f"Extracted {len(raw_data)} records")

            # Transform
            self.logger.info("Starting transformation")
            transformed_data = self.transform(raw_data)
            self.logger.info(f"Transformed {len(transformed_data)} records")

            # Load
            self.logger.info("Starting load")
            loaded_count = self.load(transformed_data)
            result.records_processed = loaded_count
            self.logger.info(f"Loaded {loaded_count} records")

        except Exception as e:
            result.status = 'failed'
            result.errors.append(str(e))
            self.logger.error(f"Job failed: {e}")

        result.completed_at = datetime.utcnow()
        return result


# ============================================================================
# INGESTION JOBS - Fetch and load raw data
# ============================================================================

class JobIngestMatches(BaseETLJob):
    """
    Job: job_ingest_matches

    Purpose: Fetch match data from source API and load to raw_match table.

    Steps:
    1. Query source API for matches in specified date range
    2. Deduplicate against existing raw records
    3. Store raw JSON with source metadata
    4. Mark records for processing
    """

    def __init__(self, config: PipelineConfig, start_date: str, end_date: str,
                 competition_ids: Optional[List[str]] = None):
        super().__init__(config)
        self.start_date = start_date
        self.end_date = end_date
        self.competition_ids = competition_ids or []

    def extract(self) -> List[Dict[str, Any]]:
        """Fetch matches from source API.

        For now we support StatsBomb Open via ``StatsBombClient`` using
        competition + season identifiers. Date filtering is not applied at
        the API level but can be added later using the match_date field.
        """

        if self.config.source != "statsbomb":
            self.logger.warning("JobIngestMatches currently only implements statsbomb source")
            return []

        if not self.competition_ids:
            self.logger.warning("No competition_ids provided; nothing to ingest")
            return []

        client = StatsBombClient()
        all_matches: List[Dict[str, Any]] = []

        try:
            for comp in self.competition_ids:
                # Here we treat end_date year as the season identifier for simplicity
                try:
                    season_year = int(self.end_date.split("-")[0])
                except Exception:
                    season_year = None

                if season_year is None:
                    self.logger.warning("Could not infer season_id from end_date; skipping")
                    continue

                self.logger.info(f"Requesting matches for competition={comp}, season={season_year}")
                matches = client.get_matches(int(comp), season_year)
                all_matches.extend(matches)
        finally:
            client.close()

        return all_matches

    def transform(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Prepare raw match data for loading.

        Adds source metadata and ingestion timestamp.
        """
        transformed = []
        for match in data:
            transformed.append({
                'source': self.config.source,
                'source_match_id': str(match.get('id', match.get('match_id'))),
                'raw_json': json.dumps(match),
                'ingested_at': datetime.utcnow().isoformat(),
                'processed': False
            })
        return transformed

    def load(self, data: List[Dict[str, Any]]) -> int:
        """
        Load raw matches to database.

        Uses upsert logic to handle late-arriving updates.
        """
        if not data:
            return 0

        loaded_count = 0

        with get_session() as session:
            for record in data:
                source_match_id = record["source_match_id"]

                existing = (
                    session.query(RawMatch)
                    .filter(
                        RawMatch.source == self.config.source,
                        RawMatch.source_match_id == source_match_id,
                    )
                    .one_or_none()
                )

                if existing:
                    # Late-arriving update: replace raw_json and reset processed flag
                    existing.raw_json = json.loads(record["raw_json"])
                    existing.ingested_at = datetime.utcnow()
                    existing.processed = False
                else:
                    session.add(
                        RawMatch(
                            source=self.config.source,
                            source_match_id=source_match_id,
                            raw_json=json.loads(record["raw_json"]),
                            ingested_at=datetime.utcnow(),
                            processed=False,
                        )
                    )

                loaded_count += 1

        return loaded_count


class JobIngestEvents(BaseETLJob):
    """
    Job: job_ingest_events

    Purpose: Fetch event data for matches and load to raw_event table.

    Steps:
    1. Get list of matches requiring event ingestion
    2. Fetch events for each match from source API
    3. Store raw JSON with match reference
    4. Handle pagination for large event sets
    """

    def __init__(self, config: PipelineConfig, match_ids: Optional[List[str]] = None):
        super().__init__(config)
        self.match_ids = match_ids

    def extract(self) -> List[Dict[str, Any]]:
        """Fetch events from source API.

        For StatsBomb Open we hit the GitHub ``events/{match_id}.json``
        endpoint via ``StatsBombClient.get_events``.
        """

        if self.config.source != "statsbomb":
            self.logger.warning("JobIngestEvents currently only implements statsbomb source")
            return []

        # If no specific matches provided, get unprocessed matches
        match_ids = self.match_ids or self._get_unprocessed_match_ids()
        if not match_ids:
            self.logger.info("No matches needing event ingestion")
            return []

        client = StatsBombClient()
        all_events: List[Dict[str, Any]] = []
        try:
            for match_id in match_ids:
                self.logger.info(f"Fetching events for match {match_id}")
                try:
                    match_events = client.get_events(int(match_id))
                except Exception as exc:
                    self.logger.error(f"Failed to fetch events for match {match_id}: {exc}")
                    continue

                for ev in match_events:
                    ev["_match_id"] = match_id
                all_events.extend(match_events)
        finally:
            client.close()

        return all_events

    def _get_unprocessed_match_ids(self) -> List[str]:
        """Get match IDs that need event ingestion.

        For now we simply return all raw_match IDs for the configured
        source. A more precise tracking of event ingestion can be added
        later.
        """

        with get_session() as session:
            rows: List[RawMatch] = (
                session.query(RawMatch)
                .filter(RawMatch.source == self.config.source)
                .all()
            )
            return [str(r.source_match_id) for r in rows]

    def transform(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Prepare raw event data for loading."""
        transformed = []
        for event in data:
            transformed.append({
                'source': self.config.source,
                'source_event_id': str(event.get('id', event.get('event_id'))),
                'source_match_id': str(event.get('_match_id', event.get('match_id'))),
                'raw_json': json.dumps(event),
                'ingested_at': datetime.utcnow().isoformat(),
                'processed': False
            })
        return transformed

    def load(self, data: List[Dict[str, Any]]) -> int:
        """Load raw events to database with basic de-duplication."""

        if not data:
            return 0

        loaded_count = 0
        with get_session() as session:
            for record in data:
                source_event_id = record["source_event_id"]
                source_match_id = record["source_match_id"]

                existing = (
                    session.query(RawEvent)
                    .filter(
                        RawEvent.source == self.config.source,
                        RawEvent.source_event_id == source_event_id,
                        RawEvent.source_match_id == source_match_id,
                    )
                    .one_or_none()
                )
                if existing:
                    continue

                session.add(
                    RawEvent(
                        source=self.config.source,
                        source_event_id=source_event_id,
                        source_match_id=source_match_id,
                        raw_json=json.loads(record["raw_json"]),
                        ingested_at=datetime.utcnow(),
                        processed=False,
                    )
                )
                loaded_count += 1

        return loaded_count


class JobIngestLineups(BaseETLJob):
    """Job: job_ingest_lineups

    Purpose: Fetch lineup data for matches and load to ``raw_lineup``.

    Steps:
    1. Determine matches needing lineup ingestion
    2. Fetch lineups for each match from source API
    3. Store per-team lineup payloads with metadata
    4. Reset ``processed`` flag for refreshed records
    """

    def __init__(self, config: PipelineConfig, match_ids: Optional[List[str]] = None):
        super().__init__(config)
        self.match_ids = match_ids

    def extract(self) -> List[Dict[str, Any]]:
        if self.config.source != "statsbomb":
            self.logger.warning("JobIngestLineups currently only implements statsbomb source")
            return []

        match_ids = self.match_ids or self._get_matches_missing_lineups()
        if not match_ids:
            self.logger.info("No matches needing lineup ingestion")
            return []

        client = StatsBombClient()
        payloads: List[Dict[str, Any]] = []
        try:
            for match_id in match_ids:
                self.logger.info(f"Fetching lineups for match {match_id}")
                try:
                    lineups = client.get_lineups(int(match_id))
                except Exception as exc:
                    self.logger.error(f"Failed to fetch lineups for match {match_id}: {exc}")
                    continue

                payloads.append({
                    "match_id": str(match_id),
                    "lineups": lineups,
                })
        finally:
            client.close()

        return payloads

    def _get_matches_missing_lineups(self) -> List[str]:
        with get_session() as session:
            matches: List[RawMatch] = (
                session.query(RawMatch)
                .filter(RawMatch.source == self.config.source)
                .all()
            )
            if not matches:
                return []

            existing_counts = {
                match_id: count
                for match_id, count in (
                    session.query(RawLineup.source_match_id, func.count(RawLineup.id))
                    .filter(RawLineup.source == self.config.source)
                    .group_by(RawLineup.source_match_id)
                    .all()
                )
            }

            pending: List[str] = []
            for match in matches:
                match_id = str(match.source_match_id)
                if existing_counts.get(match_id, 0) < 2:
                    pending.append(match_id)

            return pending

    def transform(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        transformed: List[Dict[str, Any]] = []
        for record in data:
            match_id = record["match_id"]
            for team_payload in record.get("lineups", []):
                team_id = team_payload.get("team_id")
                if team_id is None:
                    continue
                transformed.append({
                    "source": self.config.source,
                    "source_match_id": match_id,
                    "source_team_id": str(team_id),
                    "raw_json": json.dumps(team_payload),
                    "ingested_at": datetime.utcnow().isoformat(),
                    "processed": False,
                })

        return transformed

    def load(self, data: List[Dict[str, Any]]) -> int:
        if not data:
            return 0

        loaded_count = 0
        with get_session() as session:
            for record in data:
                match_id = record["source_match_id"]
                team_id = record["source_team_id"]
                payload = json.loads(record["raw_json"])

                existing = (
                    session.query(RawLineup)
                    .filter(
                        RawLineup.source == self.config.source,
                        RawLineup.source_match_id == match_id,
                        RawLineup.source_team_id == team_id,
                    )
                    .one_or_none()
                )

                if existing:
                    existing.raw_json = payload
                    existing.ingested_at = datetime.utcnow()
                    existing.processed = False
                else:
                    session.add(
                        RawLineup(
                            source=self.config.source,
                            source_match_id=match_id,
                            source_team_id=team_id,
                            raw_json=payload,
                            ingested_at=datetime.utcnow(),
                            processed=False,
                        )
                    )

                loaded_count += 1

        return loaded_count


# ============================================================================
# STAGING JOBS - Transform raw data to staging layer
# ============================================================================

class JobStageMatches(BaseETLJob):
    """
    Job: job_stage_matches

    Purpose: Transform raw match data to standardized staging format.

    Steps:
    1. Read unprocessed raw_match records
    2. Parse JSON and extract standardized fields
    3. Normalize data types and values
    4. Load to stg_match table
    5. Mark raw records as processed
    """

    def __init__(self, config: PipelineConfig, batch_size: int = 500):
        super().__init__(config)
        self.batch_size = batch_size

    def extract(self) -> List[Dict[str, Any]]:
        """Get unprocessed raw matches for this source.

        For now we pull all unprocessed rows for the configured source. In a
        production system you would likely batch by date or competition.
        """

        with get_session() as session:
            rows: List[RawMatch] = (
                session.query(RawMatch)
                .filter(RawMatch.processed.is_(False), RawMatch.source == self.config.source)
                .all()
            )

            return [
                {
                    "id": r.id,
                    "source": r.source,
                    "source_match_id": r.source_match_id,
                    "raw_json": r.raw_json,
                }
                for r in rows
            ]

    def transform(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Transform raw JSON to staging format.

        Handles source-specific parsing logic.
        """
        transformed = []

        for raw in data:
            try:
                # ``raw['raw_json']`` is already a dict from the JSON column
                match_json = raw['raw_json']
                staged = self._parse_match(match_json, raw['source'])
                staged['source'] = raw['source']
                staged['source_match_id'] = raw['source_match_id']
                staged['match_date'] = self._coerce_match_date(staged.get('match_date'))
                transformed.append(staged)
            except Exception as e:
                self.logger.error(f"Failed to parse match {raw['source_match_id']}: {e}")

        return transformed

    def _parse_match(self, match_json: Dict, source: str) -> Dict[str, Any]:
        """
        Parse match JSON based on source format.

        Each source has different field names and structures.
        """
        if source == 'statsbomb':
            return self._parse_statsbomb_match(match_json)
        elif source == 'wyscout':
            return self._parse_wyscout_match(match_json)
        else:
            return self._parse_generic_match(match_json)

    def _parse_statsbomb_match(self, match: Dict) -> Dict[str, Any]:
        """Parse StatsBomb match format."""
        home_team = match.get('home_team', {}) or {}
        away_team = match.get('away_team', {}) or {}
        competition = match.get('competition', {}) or {}
        competition_stage = match.get('competition_stage', {}) or {}
        stadium = match.get('stadium', {}) or {}
        referee = match.get('referee', {}) or {}

        return {
            'home_team_source_id': str(home_team.get('home_team_id')),
            'home_team_name': home_team.get('home_team_name'),
            'away_team_source_id': str(away_team.get('away_team_id')),
            'away_team_name': away_team.get('away_team_name'),
            'competition_source_id': str(competition.get('competition_id')),
            'competition_name': competition.get('competition_name'),
            'season_name': match.get('season', {}).get('season_name'),
            'match_date': match.get('match_date'),
            'match_time': match.get('kick_off'),
            'match_week': match.get('match_week'),
            'home_score': match.get('home_score'),
            'away_score': match.get('away_score'),
            'status': 'finished' if match.get('match_status') == 'available' else 'scheduled',
            'competition_stage': competition_stage.get('name'),
            'stadium': stadium.get('name'),
            'referee': referee.get('name'),
            'attendance': match.get('attendance')
        }

    def _parse_wyscout_match(self, match: Dict) -> Dict[str, Any]:
        """Parse Wyscout match format."""
        return {
            'home_team_source_id': str(match.get('home_team_id')),
            'home_team_name': match.get('home_team_name'),
            'away_team_source_id': str(match.get('away_team_id')),
            'away_team_name': match.get('away_team_name'),
            'competition_source_id': str(match.get('competition_id')),
            'competition_name': match.get('competition_name'),
            'season_name': match.get('season'),
            'match_date': match.get('date'),
            'match_time': match.get('time'),
            'match_week': match.get('match_week'),
            'home_score': match.get('home_score'),
            'away_score': match.get('away_score'),
            'status': match.get('status', 'unknown'),
            'competition_stage': match.get('competition_stage'),
            'stadium': match.get('venue'),
            'referee': match.get('referee'),
            'attendance': match.get('attendance')
        }

    def _parse_generic_match(self, match: Dict) -> Dict[str, Any]:
        """Parse generic match format."""
        return {
            'home_team_source_id': str(match.get('home_team_id', '')),
            'home_team_name': match.get('home_team_name'),
            'away_team_source_id': str(match.get('away_team_id', '')),
            'away_team_name': match.get('away_team_name'),
            'competition_source_id': str(match.get('competition_id', '')),
            'competition_name': match.get('competition_name'),
            'season_name': match.get('season', ''),
            'match_date': match.get('date', match.get('match_date')),
            'match_time': match.get('time', match.get('kick_off')),
            'match_week': match.get('match_week'),
            'home_score': match.get('home_score'),
            'away_score': match.get('away_score'),
            'status': match.get('status', 'unknown'),
            'competition_stage': match.get('competition_stage'),
            'stadium': match.get('stadium', match.get('venue')),
            'referee': match.get('referee'),
            'attendance': match.get('attendance')
        }

    def _coerce_match_date(self, value: Any) -> Optional[date]:
        """Convert assorted date inputs to ``date`` objects."""
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str) and value:
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    continue
        return None

    def load(self, data: List[Dict[str, Any]]) -> int:
        """Load staged matches and mark corresponding raw rows as processed.

        This method writes into ``stg_match`` and flips the ``processed`` flag
        on ``raw_match`` so that subsequent runs only operate on new data.
        """
        from src.utils import normalize_season_name

        if not data:
            return 0

        with get_session() as session:
            loaded_count = 0
            for staged in data:
                # Normalize season name using match date context
                normalized_season = normalize_season_name(
                    staged["season_name"], 
                    staged["match_date"]
                )
                
                # Insert into staging table
                stg = StgMatch(
                    source=staged["source"],
                    source_match_id=staged["source_match_id"],
                    home_team_source_id=staged["home_team_source_id"],
                     home_team_name=staged.get("home_team_name"),
                    away_team_source_id=staged["away_team_source_id"],
                     away_team_name=staged.get("away_team_name"),
                    competition_source_id=staged["competition_source_id"],
                     competition_name=staged.get("competition_name"),
                    season_name=normalized_season,
                    match_date=staged["match_date"],
                    match_time=staged["match_time"],
                     match_week=staged.get("match_week"),
                    home_score=staged["home_score"],
                    away_score=staged["away_score"],
                    status=staged["status"],
                     competition_stage=staged.get("competition_stage"),
                    stadium=staged["stadium"],
                    referee=staged["referee"],
                    attendance=staged["attendance"],
                )
                session.add(stg)

                # Mark raw row as processed using (source, source_match_id)
                session.query(RawMatch).filter(
                    RawMatch.source == staged["source"],
                    RawMatch.source_match_id == staged["source_match_id"],
                ).update({"processed": True})

                loaded_count += 1

            return loaded_count


def _get_or_create_dim_team(
    session: Session,
    source: str,
    source_team_id: str,
    team_name: Optional[str] = None,
    short_name: Optional[str] = None,
    country: Optional[str] = None,
) -> int:
    """Resolve or create a ``DimTeam`` record for a team."""

    query = session.query(DimTeam)
    if source == "statsbomb":
        query = query.filter(DimTeam.statsbomb_id == source_team_id)
    else:
        lookup_name = team_name or source_team_id
        query = query.filter(DimTeam.team_name == lookup_name)

    existing = query.one_or_none()
    if existing:
        return existing.team_id

    stg_team = (
        session.query(StgTeam)
        .filter(
            StgTeam.source == source,
            StgTeam.source_team_id == source_team_id,
        )
        .one_or_none()
    )

    resolved_name = team_name or (stg_team.name if stg_team else None) or source_team_id
    resolved_short = short_name or (stg_team.short_name if stg_team else None)
    resolved_country = country or (stg_team.country if stg_team else None)

    team = DimTeam(
        team_name=resolved_name,
        team_short_name=resolved_short,
        country=resolved_country,
    )
    if source == "statsbomb":
        team.statsbomb_id = source_team_id
    session.add(team)
    session.flush()
    return team.team_id


def _get_or_create_dim_competition(session: Session, name: str, source: str, source_id: str) -> int:
    """Resolve or create a ``DimCompetition`` record."""

    from src.ingestion.schemas import DimCompetition

    query = session.query(DimCompetition)
    if source == "statsbomb":
        query = query.filter(DimCompetition.statsbomb_id == source_id)
    else:
        query = query.filter(DimCompetition.competition_name == name)

    existing = query.one_or_none()
    if existing:
        return existing.competition_id

    comp = DimCompetition(competition_name=name)
    if source == "statsbomb":
        comp.statsbomb_id = source_id
    session.add(comp)
    session.flush()
    return comp.competition_id


def _get_or_create_dim_season(session: Session, season_name: str, match_date: Optional[date] = None) -> int:
    """Resolve or create a ``DimSeason`` from a season string.

    Normalizes season names to YYYY/YYYY format based on football season cycle (August-July).
    StatsBomb typically uses labels like "2019/2020".
    
    Args:
        session: Database session
        season_name: Season string (e.g., "2022/2023" or "2022")
        match_date: Optional match date to help normalize single-year seasons
    
    Returns:
        season_id for the normalized season
    """
    from src.utils import normalize_season_name
    
    # Normalize the season name using match date context if available
    normalized_season = normalize_season_name(season_name, match_date)

    season = session.query(DimSeason).filter(DimSeason.season_name == normalized_season).one_or_none()
    if season:
        return season.season_id

    # Parse years from normalized format
    try:
        parts = normalized_season.split("/")
        if len(parts) == 2:
            start_year = int(parts[0])
            end_year = int(parts[1])
        else:
            # Fallback if normalization failed
            start_year = datetime.utcnow().year
            end_year = start_year + 1
    except Exception:
        start_year = datetime.utcnow().year
        end_year = start_year + 1

    # Football season: Aug 1 to Jul 31 next year
    start_date = datetime(start_year, 8, 1).date()
    end_date = datetime(end_year, 7, 31).date()

    season = DimSeason(season_name=normalized_season, start_date=start_date, end_date=end_date)
    session.add(season)
    session.flush()
    return season.season_id


def _get_or_create_dim_player(
    session: Session,
    source: str,
    source_player_id: Optional[str],
    fallback_name: Optional[str] = None,
) -> Optional[int]:
    """Resolve or create ``DimPlayer`` records using staged metadata."""

    if not source_player_id:
        return None

    query = session.query(DimPlayer)
    if source == "statsbomb":
        query = query.filter(DimPlayer.statsbomb_id == source_player_id)
    else:
        lookup_name = fallback_name or source_player_id
        query = query.filter(DimPlayer.player_name == lookup_name)

    existing = query.one_or_none()
    if existing:
        return existing.player_id

    stg_player = (
        session.query(StgPlayer)
        .filter(
            StgPlayer.source == source,
            StgPlayer.source_player_id == source_player_id,
        )
        .one_or_none()
    )

    resolved_name = fallback_name or (stg_player.name if stg_player else None) or source_player_id

    player = DimPlayer(
        player_name=resolved_name,
        first_name=stg_player.first_name if stg_player else None,
        last_name=stg_player.last_name if stg_player else None,
        date_of_birth=stg_player.date_of_birth if stg_player else None,
        nationality=stg_player.nationality if stg_player else None,
        primary_position=stg_player.position if stg_player else None,
        height_cm=stg_player.height_cm if stg_player else None,
        weight_kg=stg_player.weight_kg if stg_player else None,
        preferred_foot=stg_player.preferred_foot if stg_player else None,
    )

    if source == "statsbomb":
        player.statsbomb_id = source_player_id

    session.add(player)
    session.flush()
    return player.player_id


def _safe_float(value: Any) -> Optional[float]:
    """Best-effort float conversion."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_fact_matches_from_staging(session: Session, source: str) -> int:
    """Materialize ``FactMatch`` records from ``StgMatch`` rows for a source.

    This provides the ``StgMatch → FactMatch`` leg of the pipeline.
    """

    staged_matches: List[StgMatch] = session.query(StgMatch).filter(StgMatch.source == source).all()
    created = 0

    for stg in staged_matches:
        if not stg.home_team_source_id or not stg.away_team_source_id:
            continue
        # Resolve dimensions
        home_team_id = _get_or_create_dim_team(
            session,
            source=source,
            source_team_id=stg.home_team_source_id,
            team_name=stg.home_team_name,
        )
        away_team_id = _get_or_create_dim_team(
            session,
            source=source,
            source_team_id=stg.away_team_source_id,
            team_name=stg.away_team_name,
        )

        competition_id = _get_or_create_dim_competition(
            session,
            name=stg.competition_name or stg.competition_source_id,
            source=source,
            source_id=stg.competition_source_id,
        )

        season_id = _get_or_create_dim_season(session, stg.season_name, stg.match_date)

        # Upsert-style behaviour based on (source, source_match_id)
        existing = (
            session.query(FactMatch)
            .filter(FactMatch.source == source, FactMatch.source_match_id == stg.source_match_id)
            .one_or_none()
        )
        if existing:
            continue

        fact = FactMatch(
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            competition_id=competition_id,
            season_id=season_id,
            home_score=stg.home_score,
            away_score=stg.away_score,
            match_date=stg.match_date,
            match_time=stg.match_time,
            matchweek=stg.match_week,
            status=stg.status or "finished",
            stadium=stg.stadium,
            attendance=stg.attendance,
            referee=stg.referee,
            source=source,
            source_match_id=stg.source_match_id,
        )
        session.add(fact)
        created += 1

    return created


def load_fact_events_from_staging(session: Session, source: str, limit: Optional[int] = None) -> int:
    """Materialize ``FactEvent`` rows from ``StgEvent`` for a source."""

    query = session.query(StgEvent).filter(StgEvent.source == source).order_by(StgEvent.id)
    staged_events: List[StgEvent] = query.limit(limit).all() if limit else query.all()
    if not staged_events:
        return 0

    existing_ids = {
        row[0]
        for row in session.query(FactEvent.source_event_id)
        .filter(FactEvent.source == source)
        .all()
    }

    match_map: Dict[str, FactMatch] = {
        match.source_match_id: match
        for match in session.query(FactMatch).filter(FactMatch.source == source)
    }

    stg_team_lookup: Dict[str, StgTeam] = {
        row.source_team_id: row
        for row in session.query(StgTeam).filter(StgTeam.source == source)
    }
    stg_player_lookup: Dict[str, StgPlayer] = {
        row.source_player_id: row
        for row in session.query(StgPlayer).filter(StgPlayer.source == source)
    }

    team_cache: Dict[str, int] = {}
    player_cache: Dict[str, Optional[int]] = {}

    created = 0

    for stg in staged_events:
        if not stg.source_event_id or stg.source_event_id in existing_ids:
            continue
        if not stg.source_match_id:
            continue
        match = match_map.get(stg.source_match_id)
        if not match:
            continue
        if not stg.team_source_id:
            continue

        team_id = team_cache.get(stg.team_source_id)
        if team_id is None:
            team_meta = stg_team_lookup.get(stg.team_source_id)
            team_id = _get_or_create_dim_team(
                session,
                source=source,
                source_team_id=stg.team_source_id,
                team_name=team_meta.name if team_meta else None,
                short_name=team_meta.short_name if team_meta else None,
                country=team_meta.country if team_meta else None,
            )
            team_cache[stg.team_source_id] = team_id

        player_id: Optional[int] = None
        player_source_id = stg.player_source_id or None
        if player_source_id:
            if player_source_id in player_cache:
                player_id = player_cache[player_source_id]
            else:
                player_meta = stg_player_lookup.get(player_source_id)
                fallback_name = player_meta.name if player_meta else None
                player_id = _get_or_create_dim_player(
                    session,
                    source=source,
                    source_player_id=player_source_id,
                    fallback_name=fallback_name,
                )
                player_cache[player_source_id] = player_id

        extra = parse_extra_data(stg.extra_data)
        progressive_flag = extra.get('progressive')
        under_pressure = extra.get('under_pressure')

        fact = FactEvent(
            match_id=match.match_id,
            team_id=team_id,
            player_id=player_id,
            event_type=stg.event_type,
            event_subtype=stg.event_subtype,
            minute=stg.minute,
            second=stg.second,
            period=stg.period,
            location_x=stg.location_x,
            location_y=stg.location_y,
            end_location_x=stg.end_location_x,
            end_location_y=stg.end_location_y,
            outcome=stg.outcome,
            is_successful=stg.is_successful,
            xg=_safe_float(extra.get('xg')),
            pass_length=_safe_float(extra.get('pass_length')),
            pass_angle=_safe_float(extra.get('pass_angle')),
            carry_distance=_safe_float(extra.get('carry_distance')),
            possession_sequence_id=extra.get('possession'),
            is_progressive=bool(progressive_flag) if progressive_flag is not None else None,
            is_under_pressure=bool(under_pressure) if under_pressure is not None else None,
            source=source,
            source_event_id=stg.source_event_id,
            extra_data=extra,
        )
        session.add(fact)
        existing_ids.add(stg.source_event_id)
        created += 1

    return created



class JobStageEvents(BaseETLJob):
    """
    Job: job_stage_events

    Purpose: Transform raw event data to standardized staging format.

    Steps:
    1. Read unprocessed raw_event records
    2. Parse JSON and standardize event types
    3. Normalize coordinate system (0-100 scale)
    4. Extract outcome and success flags
    5. Load to stg_event table
    """

    # Standard event type mapping
    EVENT_TYPE_MAPPING = {
        # StatsBomb mappings
        'Pass': 'pass',
        'Shot': 'shot',
        'Dribble': 'dribble',
        'Duel': 'duel',
        'Pressure': 'pressure',
        'Ball Receipt*': 'ball_receipt',
        'Carry': 'carry',
        'Interception': 'interception',
        'Clearance': 'clearance',
        'Foul Committed': 'foul',
        'Foul Won': 'foul_won',
        'Block': 'block',
        'Ball Recovery': 'ball_recovery',
        'Goal Keeper': 'goal_keeper',
        'Substitution': 'substitution',
        'Miscontrol': 'miscontrol',
        'Error': 'error',
        'Offside': 'offside',
        'Own Goal Against': 'own_goal_against',
        'Shield': 'shield',
        'Injury Stoppage': 'injury',
        'Half Start': 'half_start',
        'Half End': 'half_end',
        'Referee Ball-Drop': 'drop_ball',
        # Wyscout mappings
        'pass': 'pass',
        'shot': 'shot',
        'duel': 'duel',
        'free_kick': 'free_kick',
        'interruption': 'interruption',
        'others_on_ball': 'other',
    }

    def __init__(self, config: PipelineConfig, match_ids: Optional[List[str]] = None):
        super().__init__(config)
        self.match_ids = match_ids

    def extract(self) -> List[Dict[str, Any]]:
        """Get unprocessed raw events for this source."""

        with get_session() as session:
            query = (
                session.query(RawEvent)
                .filter(RawEvent.source == self.config.source)
            )

            if self.match_ids:
                query = query.filter(RawEvent.source_match_id.in_(self.match_ids))
            else:
                query = query.filter(RawEvent.processed.is_(False))

            rows: List[RawEvent] = query.all()

            return [
                {
                    "id": r.id,
                    "source": r.source,
                    "source_event_id": r.source_event_id,
                    "source_match_id": r.source_match_id,
                    "raw_json": r.raw_json,
                }
                for r in rows
            ]

    def transform(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Transform raw events to staging format."""
        transformed = []

        for raw in data:
            try:
                # ``raw['raw_json']`` is already a dict from the JSON column
                event_json = raw['raw_json']
                staged = self._parse_event(event_json, raw['source'])
                staged['source'] = raw['source']
                staged['source_event_id'] = raw['source_event_id']
                staged['source_match_id'] = raw['source_match_id']
                staged['raw_id'] = raw['id']
                transformed.append(staged)
            except Exception as e:
                self.logger.error(f"Failed to parse event {raw['source_event_id']}: {e}")

        return transformed

    def _parse_event(self, event: Dict, source: str) -> Dict[str, Any]:
        """Parse event based on source format."""
        if source == 'statsbomb':
            return self._parse_statsbomb_event(event)
        elif source == 'wyscout':
            return self._parse_wyscout_event(event)
        else:
            return self._parse_generic_event(event)

    def _parse_statsbomb_event(self, event: Dict) -> Dict[str, Any]:
        """
        Parse StatsBomb event format.

        StatsBomb uses 120x80 coordinate system.
        """
        location = event.get('location', [])
        end_location = self._get_end_location_statsbomb(event)

        # Normalize to 0-100 scale
        loc_x = (location[0] / 120 * 100) if len(location) > 0 else None
        loc_y = (location[1] / 80 * 100) if len(location) > 1 else None
        end_x = (end_location[0] / 120 * 100) if end_location and len(end_location) > 0 else None
        end_y = (end_location[1] / 80 * 100) if end_location and len(end_location) > 1 else None

        raw_type = event.get('type', {}).get('name', '')
        event_type = self.EVENT_TYPE_MAPPING.get(raw_type, raw_type.lower())
        extra_data = self._get_extra_data_statsbomb(event)

        return {
            'event_type': event_type,
            'event_subtype': self._get_subtype_statsbomb(event),
            'minute': event.get('minute', 0),
            'second': event.get('second', 0),
            'period': event.get('period', 1),
            'location_x': loc_x,
            'location_y': loc_y,
            'end_location_x': end_x,
            'end_location_y': end_y,
            'player_source_id': str(event.get('player', {}).get('id', '')),
            'team_source_id': str(event.get('team', {}).get('id', '')),
            'outcome': self._get_outcome_statsbomb(event),
            'is_successful': self._is_successful_statsbomb(event),
            'extra_data': extra_data,
        }

    def _get_end_location_statsbomb(self, event: Dict) -> Optional[List[float]]:
        """Extract end location from StatsBomb event."""
        if 'pass' in event:
            return event['pass'].get('end_location')
        if 'carry' in event:
            return event['carry'].get('end_location')
        if 'shot' in event:
            return event['shot'].get('end_location')
        return None

    def _get_subtype_statsbomb(self, event: Dict) -> Optional[str]:
        """Extract event subtype from StatsBomb event."""
        event_type = event.get('type', {}).get('name', '')

        if event_type == 'Pass':
            data = event.get('pass', {})
            return (
                data.get('type', {}).get('name')
                or data.get('technique', {}).get('name')
            )
        if event_type == 'Shot':
            data = event.get('shot', {})
            return (
                data.get('type', {}).get('name')
                or data.get('technique', {}).get('name')
            )
        if event_type == 'Duel':
            return event.get('duel', {}).get('type', {}).get('name')
        if event_type == 'Goal Keeper':
            return event.get('goalkeeper', {}).get('type', {}).get('name')
        if event_type == 'Foul Committed':
            return event.get('foul_committed', {}).get('type', {}).get('name')
        if event_type == 'Foul Won':
            return event.get('foul_won', {}).get('type', {}).get('name')
        if event_type == 'Miscontrol':
            return event.get('miscontrol', {}).get('type', {}).get('name')
        if event_type == 'Pressure':
            return event.get('pressure', {}).get('type', {}).get('name')

        return None

    def _get_outcome_statsbomb(self, event: Dict) -> Optional[str]:
        """Extract outcome from StatsBomb event."""
        event_type = event.get('type', {}).get('name', '')

        if event_type == 'Pass':
            return event.get('pass', {}).get('outcome', {}).get('name')
        if event_type == 'Shot':
            return event.get('shot', {}).get('outcome', {}).get('name')
        if event_type == 'Dribble':
            return event.get('dribble', {}).get('outcome', {}).get('name')
        if event_type == 'Duel':
            return event.get('duel', {}).get('outcome', {}).get('name')
        if event_type == 'Ball Receipt*':
            return event.get('ball_receipt', {}).get('outcome', {}).get('name')
        if event_type == 'Interception':
            return event.get('interception', {}).get('outcome', {}).get('name')
        if event_type == 'Goal Keeper':
            return event.get('goalkeeper', {}).get('outcome', {}).get('name')

        return None

    def _is_successful_statsbomb(self, event: Dict) -> Optional[bool]:
        """Determine if StatsBomb event was successful."""
        event_type = event.get('type', {}).get('name', '')
        outcome = self._get_outcome_statsbomb(event)

        if event_type == 'Pass':
            return outcome != 'Incomplete' and outcome != 'Out'
        if event_type == 'Shot':
            return outcome == 'Goal'
        if event_type == 'Dribble':
            return outcome == 'Complete'
        if event_type == 'Duel':
            duel_outcome = event.get('duel', {}).get('outcome', {}).get('name')
            return duel_outcome in ['Won', 'Success']
        if event_type == 'Ball Receipt*':
            return outcome == 'Complete'
        if event_type == 'Ball Recovery':
            return True
        if event_type == 'Interception':
            return outcome not in {'Lost', 'Incomplete', None}
        if event_type == 'Pressure':
            return bool(event.get('counterpress'))
        if event_type == 'Clearance':
            return True
        if event_type == 'Goal Keeper':
            gk_outcome = event.get('goalkeeper', {}).get('outcome', {}).get('name')
            if gk_outcome is None:
                return None
            return gk_outcome not in {'Failed'}
        if event_type == 'Foul Won':
            return True
        if event_type == 'Foul Committed':
            return False

        return None

    def _get_extra_data_statsbomb(self, event: Dict) -> Dict[str, Any]:
        """Extract additional event-specific data."""
        extra: Dict[str, Any] = {
            'play_pattern': event.get('play_pattern', {}).get('name'),
            'possession': event.get('possession'),
            'possession_team_id': event.get('possession_team', {}).get('id'),
            'duration': event.get('duration'),
            'counterpress': event.get('counterpress', False),
            'under_pressure': event.get('under_pressure', False),
        }

        start_loc = event.get('location')

        if 'pass' in event:
            pass_data = event['pass']
            end_loc = pass_data.get('end_location')
            extra.update({
                'pass_length': pass_data.get('length'),
                'pass_angle': pass_data.get('angle'),
                'pass_height': pass_data.get('height', {}).get('name'),
                'pass_body_part': pass_data.get('body_part', {}).get('name'),
                'pass_type': pass_data.get('type', {}).get('name'),
                'pass_technique': pass_data.get('technique', {}).get('name'),
                'pass_outcome': pass_data.get('outcome', {}).get('name'),
                'pass_recipient_id': pass_data.get('recipient', {}).get('id'),
                'cross': pass_data.get('cross', False),
                'switch': pass_data.get('switch', False),
                'through_ball': pass_data.get('through_ball', False),
                'cut_back': pass_data.get('cut_back', False),
                'shot_assist': pass_data.get('shot_assist', False),
                'goal_assist': pass_data.get('goal_assist', False),
                'progressive': self._is_progressive_event(start_loc, end_loc),
            })

        if 'shot' in event:
            shot_data = event['shot']
            extra.update({
                'xg': shot_data.get('statsbomb_xg'),
                'shot_body_part': shot_data.get('body_part', {}).get('name'),
                'shot_type': shot_data.get('type', {}).get('name'),
                'shot_technique': shot_data.get('technique', {}).get('name'),
                'shot_first_time': shot_data.get('first_time', False),
                'shot_one_on_one': shot_data.get('one_on_one', False),
                'shot_outcome': shot_data.get('outcome', {}).get('name'),
                'shot_key_pass_id': shot_data.get('key_pass_id'),
            })

        if 'carry' in event:
            carry_data = event['carry']
            end_loc = carry_data.get('end_location', [])
            if end_loc and start_loc:
                extra['carry_distance'] = (
                    ((end_loc[0] - start_loc[0]) ** 2 +
                     (end_loc[1] - start_loc[1]) ** 2) ** 0.5
                )
                extra['progressive'] = self._is_progressive_event(start_loc, end_loc)

        return {k: v for k, v in extra.items() if v not in (None, [], {})}

    @staticmethod
    def _is_progressive_event(start: Optional[List[float]], end: Optional[List[float]], threshold: float = 15.0) -> Optional[bool]:
        """Heuristic to flag progressive ball movement in StatsBomb units."""

        if not start or not end:
            return None
        if len(start) < 2 or len(end) < 2:
            return None
        return (end[0] - start[0]) >= threshold

    def _parse_wyscout_event(self, event: Dict) -> Dict[str, Any]:
        """Parse Wyscout event format."""
        # Wyscout uses percentage coordinates (0-100)
        return {
            'event_type': self.EVENT_TYPE_MAPPING.get(
                event.get('eventName', ''),
                event.get('eventName', '').lower()
            ),
            'event_subtype': event.get('subEventName'),
            'minute': event.get('matchPeriod', '1H').replace('H', ''),
            'second': event.get('eventSec', 0) % 60,
            'period': 1 if '1H' in event.get('matchPeriod', '1H') else 2,
            'location_x': event.get('positions', [{}])[0].get('x'),
            'location_y': event.get('positions', [{}])[0].get('y'),
            'end_location_x': event.get('positions', [{}])[-1].get('x') if len(event.get('positions', [])) > 1 else None,
            'end_location_y': event.get('positions', [{}])[-1].get('y') if len(event.get('positions', [])) > 1 else None,
            'player_source_id': str(event.get('playerId', '')),
            'team_source_id': str(event.get('teamId', '')),
            'outcome': None,
            'is_successful': 101 in event.get('tags', []),  # Wyscout success tag
            'extra_data': {'tags': event.get('tags', [])}
        }

    def _parse_generic_event(self, event: Dict) -> Dict[str, Any]:
        """Parse generic event format."""
        return {
            'event_type': event.get('type', 'unknown').lower(),
            'event_subtype': event.get('subtype'),
            'minute': event.get('minute', 0),
            'second': event.get('second', 0),
            'period': event.get('period', 1),
            'location_x': event.get('x', event.get('location_x')),
            'location_y': event.get('y', event.get('location_y')),
            'end_location_x': event.get('end_x', event.get('end_location_x')),
            'end_location_y': event.get('end_y', event.get('end_location_y')),
            'player_source_id': str(event.get('player_id', '')),
            'team_source_id': str(event.get('team_id', '')),
            'outcome': event.get('outcome'),
            'is_successful': event.get('success', event.get('is_successful')),
            'extra_data': event.get('extra', {})
        }

    def load(self, data: List[Dict[str, Any]]) -> int:
        """Load staged events and mark corresponding raw rows as processed."""

        if not data:
            return 0

        with get_session() as session:
            loaded_count = 0
            for staged in data:
                stg = StgEvent(
                    source=staged["source"],
                    source_event_id=staged["source_event_id"],
                    source_match_id=staged["source_match_id"],
                    event_type=staged["event_type"],
                    event_subtype=staged["event_subtype"],
                    minute=staged["minute"],
                    second=staged["second"],
                    period=staged["period"],
                    location_x=staged["location_x"],
                    location_y=staged["location_y"],
                    end_location_x=staged["end_location_x"],
                    end_location_y=staged["end_location_y"],
                    player_source_id=staged["player_source_id"],
                    team_source_id=staged["team_source_id"],
                    outcome=staged["outcome"],
                    is_successful=staged["is_successful"],
                    extra_data=staged["extra_data"],
                )
                session.add(stg)

                raw_id = staged.get("raw_id")
                if raw_id is not None:
                    session.query(RawEvent).filter(RawEvent.id == raw_id).update({"processed": True})

                loaded_count += 1

            return loaded_count


class JobStageEntities(BaseETLJob):
    """
    Job: job_stage_entities

    Purpose: Extract and stage entity data (teams, players) from raw records.

    Steps:
    1. Scan raw_match, raw_event, raw_lineup for entity references
    2. Deduplicate entities by source ID
    3. Parse entity attributes from JSON
    4. Load to stg_team, stg_player tables
    """

    def __init__(self, config: PipelineConfig):
        super().__init__(config)

    def extract(self) -> List[Dict[str, Any]]:
        """Extract entity references from raw tables.

        We scan ``raw_match``, ``raw_event`` and ``raw_lineup`` for
        distinct team and player objects.
        """

        teams: Dict[str, Dict[str, Any]] = {}
        players: Dict[str, Dict[str, Any]] = {}

        with get_session() as session:
            # From raw_match: home/away teams
            raw_matches: List[RawMatch] = (
                session.query(RawMatch)
                .filter(RawMatch.source == self.config.source)
                .all()
            )
            for r in raw_matches:
                data = r.raw_json if isinstance(r.raw_json, dict) else json.loads(r.raw_json)
                home = data.get('home_team') or {}
                away = data.get('away_team') or {}
                if home.get('home_team_id') is not None:
                    key = f"team:{home['home_team_id']}"
                    teams.setdefault(key, {
                        'id': home.get('home_team_id'),
                        'name': home.get('home_team_name'),
                        'short_name': home.get('home_team_name'),
                        'country': None,
                    })
                if away.get('away_team_id') is not None:
                    key = f"team:{away['away_team_id']}"
                    teams.setdefault(key, {
                        'id': away.get('away_team_id'),
                        'name': away.get('away_team_name'),
                        'short_name': away.get('away_team_name'),
                        'country': None,
                    })

            # From raw_event: players and teams
            raw_events: List[RawEvent] = (
                session.query(RawEvent)
                .filter(RawEvent.source == self.config.source)
                .all()
            )
            for r in raw_events:
                ev = r.raw_json if isinstance(r.raw_json, dict) else json.loads(r.raw_json)
                player = ev.get('player') or {}
                team = ev.get('team') or {}
                if player.get('id') is not None:
                    key = f"player:{player['id']}"
                    players.setdefault(key, {
                        'id': player.get('id'),
                        'name': player.get('name'),
                        'first_name': None,
                        'last_name': None,
                        'date_of_birth': None,
                        'nationality': None,
                        'position': None,
                        'height_cm': None,
                        'weight_kg': None,
                        'preferred_foot': None,
                    })
                if team.get('id') is not None:
                    key = f"team:{team['id']}"
                    teams.setdefault(key, {
                        'id': team.get('id'),
                        'name': team.get('name'),
                        'short_name': team.get('name'),
                        'country': None,
                    })

            # From raw_lineup: richer player metadata if available
            raw_lineups: List[RawLineup] = (
                session.query(RawLineup)
                .filter(RawLineup.source == self.config.source)
                .all()
            )
            for r in raw_lineups:
                lineup = r.raw_json if isinstance(r.raw_json, dict) else json.loads(r.raw_json)
                for player in lineup.get('lineup', []):
                    if player.get('player_id') is None:
                        continue
                    key = f"player:{player['player_id']}"
                    players[key] = {
                        'id': player.get('player_id'),
                        'name': player.get('player_name'),
                        'first_name': None,
                        'last_name': None,
                        'date_of_birth': player.get('birth_date'),
                        'nationality': player.get('country'),
                        'position': player.get('position'),
                        'height_cm': None,
                        'weight_kg': None,
                        'preferred_foot': None,
                    }

        return [{
            'teams': list(teams.values()),
            'players': list(players.values()),
        }]

    def transform(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Standardize entity data."""
        if not data:
            return []

        entities = data[0]
        transformed = {
            'teams': [],
            'players': []
        }

        for team in entities.get('teams', []):
            transformed['teams'].append({
                'source': self.config.source,
                'source_team_id': str(team.get('id')),
                'name': team.get('name', team.get('team_name')),
                'short_name': team.get('short_name'),
                'country': team.get('country', {}).get('name') if isinstance(team.get('country'), dict) else team.get('country')
            })

        for player in entities.get('players', []):
            transformed['players'].append({
                'source': self.config.source,
                'source_player_id': str(player.get('id')),
                'name': player.get('name', player.get('player_name')),
                'first_name': player.get('first_name'),
                'last_name': player.get('last_name'),
                'date_of_birth': player.get('date_of_birth', player.get('dob')),
                'nationality': player.get('nationality', {}).get('name') if isinstance(player.get('nationality'), dict) else player.get('nationality'),
                'position': player.get('position', {}).get('name') if isinstance(player.get('position'), dict) else player.get('position'),
                'height_cm': player.get('height_cm', player.get('height')),
                'weight_kg': player.get('weight_kg', player.get('weight')),
                'preferred_foot': player.get('preferred_foot', player.get('foot'))
            })

        return [transformed]

    def load(self, data: List[Dict[str, Any]]) -> int:
        """Load staged entities."""
        if not data:
            return 0

        entities = data[0]
        loaded_count = 0

        with get_session() as session:
            existing_teams = {
                str(row.source_team_id): row
                for row in session.query(StgTeam).filter(StgTeam.source == self.config.source)
            }
            existing_players = {
                str(row.source_player_id): row
                for row in session.query(StgPlayer).filter(StgPlayer.source == self.config.source)
            }

            # Load teams
            for team in entities.get('teams', []):
                source_team_id = team.get('source_team_id')
                if source_team_id is None:
                    continue
                source_team_id = str(source_team_id)
                existing = existing_teams.get(source_team_id)
                if existing:
                    existing.name = team.get('name') or existing.name
                    existing.short_name = team.get('short_name') or existing.short_name
                    existing.country = team.get('country') or existing.country
                else:
                    stg_team = StgTeam(
                        source=self.config.source,
                        source_team_id=source_team_id,
                        name=team.get('name'),
                        short_name=team.get('short_name'),
                        country=team.get('country'),
                    )
                    session.add(stg_team)
                    existing_teams[source_team_id] = stg_team
                loaded_count += 1

            # Load players
            for player in entities.get('players', []):
                source_player_id = player.get('source_player_id')
                if source_player_id is None:
                    continue
                source_player_id = str(source_player_id)
                existing = existing_players.get(source_player_id)
                if existing:
                    existing.name = player.get('name') or existing.name
                    existing.first_name = player.get('first_name') or existing.first_name
                    existing.last_name = player.get('last_name') or existing.last_name
                    existing.date_of_birth = player.get('date_of_birth') or existing.date_of_birth
                    existing.nationality = player.get('nationality') or existing.nationality
                    existing.position = player.get('position') or existing.position
                    existing.height_cm = player.get('height_cm') or existing.height_cm
                    existing.weight_kg = player.get('weight_kg') or existing.weight_kg
                    existing.preferred_foot = player.get('preferred_foot') or existing.preferred_foot
                else:
                    stg_player = StgPlayer(
                        source=self.config.source,
                        source_player_id=source_player_id,
                        name=player.get('name'),
                        first_name=player.get('first_name'),
                        last_name=player.get('last_name'),
                        date_of_birth=player.get('date_of_birth'),
                        nationality=player.get('nationality'),
                        position=player.get('position'),
                        height_cm=player.get('height_cm'),
                        weight_kg=player.get('weight_kg'),
                        preferred_foot=player.get('preferred_foot'),
                    )
                    session.add(stg_player)
                    existing_players[source_player_id] = stg_player
                loaded_count += 1

        return loaded_count


# ============================================================================
# ID MAPPING & STANDARDIZATION
# ============================================================================

class EntityMapper:
    """
    Maps source-specific IDs to internal dimension IDs.

    Handles:
    - Cross-source entity resolution
    - Fuzzy name matching for entities without clear mappings
    - Manual override support
    """

    def __init__(self, db_session):
        self.session = db_session
        self._team_cache = {}
        self._player_cache = {}
        self._competition_cache = {}

    def get_or_create_team(self, source: str, source_id: str,
                           team_data: Dict[str, Any]) -> int:
        """
        Get internal team_id, creating dimension record if needed.

        Args:
            source: Data source name
            source_id: Team ID in source system
            team_data: Team attributes from staging

        Returns:
            Internal team_id from dim_team
        """
        cache_key = f"{source}:{source_id}"
        if cache_key in self._team_cache:
            return self._team_cache[cache_key]

        # Check for existing mapping
        # SELECT team_id FROM dim_team WHERE {source}_id = source_id

        # If not found, try fuzzy match on name
        # If still not found, create new dim_team record

        # Cache and return
        team_id = 1  # Placeholder
        self._team_cache[cache_key] = team_id
        return team_id

    def get_or_create_player(self, source: str, source_id: str,
                             player_data: Dict[str, Any]) -> int:
        """Get internal player_id, creating dimension record if needed."""
        cache_key = f"{source}:{source_id}"
        if cache_key in self._player_cache:
            return self._player_cache[cache_key]

        player_id = 1  # Placeholder
        self._player_cache[cache_key] = player_id
        return player_id

    def refresh_caches(self):
        """Reload caches from database."""
        self._team_cache.clear()
        self._player_cache.clear()
        self._competition_cache.clear()


# ============================================================================
# PIPELINE ORCHESTRATOR
# ============================================================================

class Pipeline:
    """
    Orchestrates ETL job execution.

    Supports:
    - Job dependencies
    - Parallel execution where possible
    - Failure handling and retry logic
    - Progress tracking and logging
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.jobs: List[BaseETLJob] = []
        self.results: List[JobResult] = []

    def add_job(self, job: BaseETLJob):
        """Add job to pipeline."""
        self.jobs.append(job)

    def run(self) -> List[JobResult]:
        """Execute all jobs in sequence."""
        for job in self.jobs:
            result = job.run()
            self.results.append(result)

            if result.status == 'failed':
                logger.error(f"Pipeline stopped due to job failure: {result.job_name}")
                break

        return self.results

    def run_full_ingestion(self, start_date: str, end_date: str,
                           competition_ids: Optional[List[str]] = None):
        """
        Run complete ingestion pipeline.

        1. Ingest matches
        2. Ingest events
        3. Stage matches
        4. Stage events
        5. Stage entities
        """
        # Add jobs in order
        self.add_job(JobIngestMatches(self.config, start_date, end_date, competition_ids))
        self.add_job(JobIngestEvents(self.config))
        self.add_job(JobIngestLineups(self.config))
        self.add_job(JobStageMatches(self.config))
        self.add_job(JobStageEvents(self.config))
        self.add_job(JobStageEntities(self.config))

        return self.run()


def load_fact_lineups_from_raw(session: Session, source: str) -> int:
    """Materialize ``FactLineup`` rows from ``RawLineup`` payloads."""

    raw_lineups: List[RawLineup] = session.query(RawLineup).filter(RawLineup.source == source).all()
    created = 0

    for raw in raw_lineups:
        payload = raw.raw_json if isinstance(raw.raw_json, dict) else json.loads(raw.raw_json)
        if not payload:
            continue

        match = (
            session.query(FactMatch)
            .filter(FactMatch.source == source, FactMatch.source_match_id == raw.source_match_id)
            .one_or_none()
        )
        if not match:
            continue

        team_id = _get_or_create_dim_team(
            session,
            source=source,
            source_team_id=raw.source_team_id,
            team_name=payload.get('team_name'),
        )

        lineup_entries = payload.get('lineup', []) or []
        for entry in lineup_entries:
            player_source_id = entry.get('player_id')
            player_dim_id = _get_or_create_dim_player(
                session,
                source=source,
                source_player_id=str(player_source_id) if player_source_id is not None else None,
                fallback_name=entry.get('player_name'),
            )
            if not player_dim_id:
                continue

            positions = entry.get('positions', []) or []
            is_starter = _is_lineup_starter(positions)
            position_name = _determine_primary_position(positions)
            sub_on, sub_off = _extract_lineup_minutes(positions)

            minutes_played = None
            if sub_on is not None or sub_off is not None:
                start_val = sub_on if sub_on is not None else 0.0
                default_end = max(_DEFAULT_MATCH_MINUTES, start_val)
                end_val = sub_off if sub_off is not None else default_end
                minutes_played = max(0.0, end_val - start_val)

            existing = (
                session.query(FactLineup)
                .filter(
                    FactLineup.match_id == match.match_id,
                    FactLineup.player_id == player_dim_id,
                )
                .one_or_none()
            )

            payload_kwargs = {
                'team_id': team_id,
                'is_starter': is_starter,
                'position': position_name,
                'jersey_number': entry.get('jersey_number'),
                'captain': bool(entry.get('captain', False)),
                'minutes_played': int(round(minutes_played)) if minutes_played is not None else None,
                'sub_on_minute': int(round(sub_on)) if sub_on is not None else None,
                'sub_off_minute': int(round(sub_off)) if sub_off is not None else None,
            }

            if existing:
                for key, value in payload_kwargs.items():
                    setattr(existing, key, value)
            else:
                fact_lineup = FactLineup(
                    match_id=match.match_id,
                    player_id=player_dim_id,
                    **payload_kwargs,
                )
                session.add(fact_lineup)
                created += 1

        raw.processed = True

    return created


_DEFAULT_MATCH_MINUTES = 90.0


def _coerce_clock_to_minute(clock_value: Optional[str]) -> Optional[float]:
    if not clock_value:
        return None
    try:
        minutes_str, seconds_str = clock_value.split(":")
        minutes = int(minutes_str)
        seconds = int(seconds_str)
        return minutes + seconds / 60
    except Exception:
        return None


def _extract_lineup_minutes(positions: List[Dict[str, Any]]) -> Tuple[Optional[float], Optional[float]]:
    if not positions:
        return None, None

    start_minute: Optional[float] = None
    end_minute: Optional[float] = None

    for pos in positions:
        start_candidate = _coerce_clock_to_minute(pos.get('from'))
        if start_candidate is not None:
            start_minute = start_candidate if start_minute is None else min(start_minute, start_candidate)

        end_candidate = _coerce_clock_to_minute(pos.get('to'))
        if end_candidate is not None:
            end_minute = end_candidate if end_minute is None else max(end_minute, end_candidate)

    return start_minute, end_minute


def _determine_primary_position(positions: List[Dict[str, Any]]) -> Optional[str]:
    if not positions:
        return None
    return positions[0].get('position')


def _is_lineup_starter(positions: List[Dict[str, Any]]) -> bool:
    if not positions:
        return False
    return any(pos.get('start_reason') == 'Starting XI' for pos in positions)
