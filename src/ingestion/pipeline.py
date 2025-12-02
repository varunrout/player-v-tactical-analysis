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
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

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
    DimCompetition,
    DimSeason,
    DimTeam,
)
from src.ingestion.statsbomb_client import StatsBombClient

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
                match_json = json.loads(raw['raw_json'])
                staged = self._parse_match(match_json, raw['source'])
                staged['source'] = raw['source']
                staged['source_match_id'] = raw['source_match_id']
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
        return {
            'home_team_source_id': str(match.get('home_team', {}).get('home_team_id')),
            'away_team_source_id': str(match.get('away_team', {}).get('away_team_id')),
            'competition_source_id': str(match.get('competition', {}).get('competition_id')),
            'season_name': match.get('season', {}).get('season_name'),
            'match_date': match.get('match_date'),
            'match_time': match.get('kick_off'),
            'home_score': match.get('home_score'),
            'away_score': match.get('away_score'),
            'status': 'finished' if match.get('match_status') == 'available' else 'scheduled',
            'stadium': match.get('stadium', {}).get('name'),
            'referee': match.get('referee', {}).get('name'),
            'attendance': match.get('attendance')
        }

    def _parse_wyscout_match(self, match: Dict) -> Dict[str, Any]:
        """Parse Wyscout match format."""
        return {
            'home_team_source_id': str(match.get('home_team_id')),
            'away_team_source_id': str(match.get('away_team_id')),
            'competition_source_id': str(match.get('competition_id')),
            'season_name': match.get('season'),
            'match_date': match.get('date'),
            'match_time': match.get('time'),
            'home_score': match.get('home_score'),
            'away_score': match.get('away_score'),
            'status': match.get('status', 'unknown'),
            'stadium': match.get('venue'),
            'referee': match.get('referee'),
            'attendance': match.get('attendance')
        }

    def _parse_generic_match(self, match: Dict) -> Dict[str, Any]:
        """Parse generic match format."""
        return {
            'home_team_source_id': str(match.get('home_team_id', '')),
            'away_team_source_id': str(match.get('away_team_id', '')),
            'competition_source_id': str(match.get('competition_id', '')),
            'season_name': match.get('season', ''),
            'match_date': match.get('date', match.get('match_date')),
            'match_time': match.get('time', match.get('kick_off')),
            'home_score': match.get('home_score'),
            'away_score': match.get('away_score'),
            'status': match.get('status', 'unknown'),
            'stadium': match.get('stadium', match.get('venue')),
            'referee': match.get('referee'),
            'attendance': match.get('attendance')
        }

    def load(self, data: List[Dict[str, Any]]) -> int:
        """Load staged matches and mark corresponding raw rows as processed.

        This method writes into ``stg_match`` and flips the ``processed`` flag
        on ``raw_match`` so that subsequent runs only operate on new data.
        """

        if not data:
            return 0

        with get_session() as session:
            loaded_count = 0
            for staged in data:
                # Insert into staging table
                stg = StgMatch(
                    source=staged["source"],
                    source_match_id=staged["source_match_id"],
                    home_team_source_id=staged["home_team_source_id"],
                    away_team_source_id=staged["away_team_source_id"],
                    competition_source_id=staged["competition_source_id"],
                    season_name=staged["season_name"],
                    match_date=staged["match_date"],
                    match_time=staged["match_time"],
                    home_score=staged["home_score"],
                    away_score=staged["away_score"],
                    status=staged["status"],
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


def _get_or_create_dim_team(session: Session, name: str, source: str, source_team_id: str) -> int:
    """Resolve or create a ``DimTeam`` record for a StatsBomb team.

    For now we maintain a single name + source_id mapping; later this can be
    expanded to use the full ``EntityMapper`` abstraction.
    """

    query = session.query(DimTeam)
    if source == "statsbomb":
        query = query.filter(DimTeam.statsbomb_id == source_team_id)
    else:
        query = query.filter(DimTeam.team_name == name)

    existing = query.one_or_none()
    if existing:
        return existing.team_id

    team = DimTeam(team_name=name)
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


def _get_or_create_dim_season(session: Session, season_name: str) -> int:
    """Resolve or create a ``DimSeason`` from a StatsBomb-like season string.

    StatsBomb typically uses labels like "2019/2020"; here we approximate
    ``start_date``/``end_date`` using the start and end years.
    """

    season = session.query(DimSeason).filter(DimSeason.season_name == season_name).one_or_none()
    if season:
        return season.season_id

    # Heuristic: split on '/' to infer start/end years, fall back to 1 July
    start_year = None
    end_year = None
    try:
        parts = season_name.split("/")
        if len(parts) == 2:
            start_year = int(parts[0])
            end_year = int(parts[1])
    except Exception:
        pass

    if start_year is None or end_year is None:
        # Fallback: use match date year span; here we just set something valid
        start_year = datetime.utcnow().year
        end_year = start_year

    start_date = datetime(start_year, 7, 1).date()
    end_date = datetime(end_year, 6, 30).date()

    season = DimSeason(season_name=season_name, start_date=start_date, end_date=end_date)
    session.add(season)
    session.flush()
    return season.season_id


def load_fact_matches_from_staging(session: Session, source: str) -> int:
    """Materialize ``FactMatch`` records from ``StgMatch`` rows for a source.

    This provides the ``StgMatch → FactMatch`` leg of the pipeline.
    """

    staged_matches: List[StgMatch] = session.query(StgMatch).filter(StgMatch.source == source).all()
    created = 0

    for stg in staged_matches:
        # Resolve dimensions
        home_team_id = _get_or_create_dim_team(
            session,
            name=stg.home_team_source_id,
            source=source,
            source_team_id=stg.home_team_source_id,
        )
        away_team_id = _get_or_create_dim_team(
            session,
            name=stg.away_team_source_id,
            source=source,
            source_team_id=stg.away_team_source_id,
        )

        competition_id = _get_or_create_dim_competition(
            session,
            name=stg.competition_source_id,
            source=source,
            source_id=stg.competition_source_id,
        )

        season_id = _get_or_create_dim_season(session, stg.season_name)

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
        # Wyscout mappings
        'pass': 'pass',
        'shot': 'shot',
        'duel': 'duel',
        'free_kick': 'free_kick',
        'interruption': 'interruption',
        'others_on_ball': 'other',
    }

    def __init__(self, config: PipelineConfig):
        super().__init__(config)

    def extract(self) -> List[Dict[str, Any]]:
        """Get unprocessed raw events for this source."""

        with get_session() as session:
            rows: List[RawEvent] = (
                session.query(RawEvent)
                .filter(RawEvent.processed.is_(False), RawEvent.source == self.config.source)
                .all()
            )

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
                event_json = json.loads(raw['raw_json'])
                staged = self._parse_event(event_json, raw['source'])
                staged['source'] = raw['source']
                staged['source_event_id'] = raw['source_event_id']
                staged['source_match_id'] = raw['source_match_id']
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
            'extra_data': json.dumps(self._get_extra_data_statsbomb(event))
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
            return event.get('pass', {}).get('technique', {}).get('name')
        if event_type == 'Shot':
            return event.get('shot', {}).get('technique', {}).get('name')
        if event_type == 'Duel':
            return event.get('duel', {}).get('type', {}).get('name')

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
            return event.get('duel', {}).get('outcome', {}).get('name') in ['Won', 'Success']

        return None

    def _get_extra_data_statsbomb(self, event: Dict) -> Dict[str, Any]:
        """Extract additional event-specific data."""
        extra = {}

        if 'pass' in event:
            pass_data = event['pass']
            extra['pass_length'] = pass_data.get('length')
            extra['pass_angle'] = pass_data.get('angle')
            extra['pass_height'] = pass_data.get('height', {}).get('name')
            extra['cross'] = pass_data.get('cross', False)
            extra['switch'] = pass_data.get('switch', False)
            extra['through_ball'] = pass_data.get('through_ball', False)

        if 'shot' in event:
            shot_data = event['shot']
            extra['xg'] = shot_data.get('statsbomb_xg')
            extra['body_part'] = shot_data.get('body_part', {}).get('name')
            extra['type'] = shot_data.get('type', {}).get('name')

        if 'carry' in event:
            carry_data = event['carry']
            end_loc = carry_data.get('end_location', [])
            start_loc = event.get('location', [])
            if end_loc and start_loc:
                extra['carry_distance'] = (
                    ((end_loc[0] - start_loc[0]) ** 2 +
                     (end_loc[1] - start_loc[1]) ** 2) ** 0.5
                )

        extra['under_pressure'] = event.get('under_pressure', False)

        return extra

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
            'extra_data': json.dumps({'tags': event.get('tags', [])})
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
            'extra_data': json.dumps(event.get('extra', {}))
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

                raw_id = staged.get("id")
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
            # Load teams
            for team in entities.get('teams', []):
                stg_team = StgTeam(
                    source=self.config.source,
                    source_team_id=str(team['id']),
                    name=team['name'],
                    short_name=team.get('short_name'),
                    country=team.get('country'),
                )
                session.add(stg_team)
                loaded_count += 1

            # Load players
            for player in entities.get('players', []):
                stg_player = StgPlayer(
                    source=self.config.source,
                    source_player_id=str(player['id']),
                    name=player['name'],
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
        self.add_job(JobStageMatches(self.config))
        self.add_job(JobStageEvents(self.config))
        self.add_job(JobStageEntities(self.config))

        return self.run()
