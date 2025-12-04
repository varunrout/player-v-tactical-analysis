#!/usr/bin/env python3
"""
Script to ingest international tournament data from StatsBomb Open Data.

Supports:
- Champions League (finals only)
- UEFA Euro
- Copa America  
- Africa Cup of Nations
- FIFA World Cup (already ingested)
"""

import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple

from src.ingestion.db import get_session
from src.ingestion.schemas import RawMatch, RawEvent, RawLineup
from src.ingestion.statsbomb_client import StatsBombClient
from src.ingestion.pipeline import (
    PipelineConfig,
    JobStageMatches,
    JobStageEvents,
    JobStageEntities,
    load_fact_matches_from_staging,
    load_fact_events_from_staging,
    load_fact_lineups_from_raw,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Competition configurations: {competition_id: {season_id: season_name}}
COMPETITIONS = {
    # UEFA Euro
    55: {
        43: "Euro 2020",
        282: "Euro 2024",
    },
    # Copa America
    223: {
        282: "Copa America 2024",
    },
    # Africa Cup of Nations
    1267: {
        107: "AFCON 2023",
    },
}


def ingest_matches_for_season(client: StatsBombClient, competition_id: int, season_id: int, season_name: str) -> List[Dict[str, Any]]:
    """Fetch and store matches for a specific season."""
    logger.info(f"Fetching matches for {season_name} (season_id={season_id})")
    
    try:
        matches = client.get_matches(competition_id, season_id)
        logger.info(f"  Found {len(matches)} matches")
    except Exception as e:
        logger.error(f"  Failed to fetch matches: {e}")
        return []
    
    # Store to raw_matches
    with get_session() as session:
        stored = 0
        for match in matches:
            source_match_id = str(match.get('match_id'))
            
            # Check if already exists
            existing = session.query(RawMatch).filter(
                RawMatch.source == 'statsbomb',
                RawMatch.source_match_id == source_match_id
            ).first()
            
            if existing:
                continue
            
            raw_match = RawMatch(
                source='statsbomb',
                source_match_id=source_match_id,
                raw_json=match,
                ingested_at=datetime.now(timezone.utc),
                processed=False
            )
            session.add(raw_match)
            stored += 1
        
        session.commit()
        logger.info(f"  Stored {stored} new matches")
    
    return matches


def ingest_events_for_matches(client: StatsBombClient, matches: List[Dict[str, Any]]) -> int:
    """Fetch and store events for all matches."""
    total_stored = 0
    
    with get_session() as session:
        for i, match in enumerate(matches):
            match_id = match.get('match_id')
            if not match_id:
                continue
            
            # Check if events already exist
            existing = session.query(RawEvent).filter(
                RawEvent.source == 'statsbomb',
                RawEvent.source_match_id == str(match_id)
            ).first()
            
            if existing:
                continue
            
            try:
                events = client.get_events(match_id)
            except Exception as e:
                logger.warning(f"  Failed to fetch events for match {match_id}: {e}")
                continue
            
            for event in events:
                event_id = str(event.get('id'))
                raw_event = RawEvent(
                    source='statsbomb',
                    source_match_id=str(match_id),
                    source_event_id=event_id,
                    raw_json=event,
                    ingested_at=datetime.now(timezone.utc),
                    processed=False
                )
                session.add(raw_event)
                total_stored += 1
            
            if (i + 1) % 10 == 0:
                session.commit()
                logger.info(f"    Processed {i + 1}/{len(matches)} matches...")
        
        session.commit()
    
    return total_stored


def ingest_lineups_for_matches(client: StatsBombClient, matches: List[Dict[str, Any]]) -> int:
    """Fetch and store lineups for all matches."""
    total_stored = 0
    
    with get_session() as session:
        for i, match in enumerate(matches):
            match_id = match.get('match_id')
            if not match_id:
                continue
            
            # Check if lineups already exist
            existing = session.query(RawLineup).filter(
                RawLineup.source == 'statsbomb',
                RawLineup.source_match_id == str(match_id)
            ).first()
            
            if existing:
                continue
            
            try:
                lineups = client.get_lineups(match_id)
            except Exception as e:
                logger.warning(f"  Failed to fetch lineups for match {match_id}: {e}")
                continue
            
            for lineup in lineups:
                team_id = str(lineup.get('team_id'))
                raw_lineup = RawLineup(
                    source='statsbomb',
                    source_match_id=str(match_id),
                    source_team_id=team_id,
                    raw_json=lineup,
                    ingested_at=datetime.now(timezone.utc),
                    processed=False
                )
                session.add(raw_lineup)
                total_stored += 1
            
            if (i + 1) % 20 == 0:
                session.commit()
                logger.info(f"    Processed {i + 1}/{len(matches)} matches...")
        
        session.commit()
    
    return total_stored


def main():
    """Run the full international tournaments ingestion pipeline."""
    logger.info("=" * 60)
    logger.info("Starting International Tournaments Data Ingestion")
    logger.info("=" * 60)
    
    client = StatsBombClient()
    all_matches = []
    
    try:
        # Phase 1: Ingest all matches from all competitions
        logger.info("\n--- PHASE 1: Ingesting Matches ---")
        for competition_id, seasons in COMPETITIONS.items():
            for season_id, season_name in seasons.items():
                matches = ingest_matches_for_season(client, competition_id, season_id, season_name)
                all_matches.extend(matches)
        
        logger.info(f"\nTotal matches ingested: {len(all_matches)}")
        
        # Phase 2: Ingest events for all matches
        logger.info("\n--- PHASE 2: Ingesting Events ---")
        events_stored = ingest_events_for_matches(client, all_matches)
        logger.info(f"Total events stored: {events_stored}")
        
        # Phase 3: Ingest lineups for all matches
        logger.info("\n--- PHASE 3: Ingesting Lineups ---")
        lineups_stored = ingest_lineups_for_matches(client, all_matches)
        logger.info(f"Total lineups stored: {lineups_stored}")
        
    finally:
        client.close()
    
    # Phase 4: Run staging jobs
    logger.info("\n--- PHASE 4: Running Staging Pipeline ---")
    config = PipelineConfig(source='statsbomb')
    
    # Stage matches
    logger.info("Staging matches...")
    job_stage_matches = JobStageMatches(config)
    result = job_stage_matches.run()
    logger.info(f"  Staged {result.records_processed} matches")
    
    # Stage events
    logger.info("Staging events...")
    job_stage_events = JobStageEvents(config)
    result = job_stage_events.run()
    logger.info(f"  Staged {result.records_processed} events")
    
    # Stage entities (teams, players)
    logger.info("Staging entities...")
    job_stage_entities = JobStageEntities(config)
    result = job_stage_entities.run()
    logger.info(f"  Staged {result.records_processed} entities")
    
    # Phase 5: Load fact tables
    logger.info("\n--- PHASE 5: Loading Fact Tables ---")
    
    with get_session() as session:
        # Load fact_matches first
        logger.info("Loading fact_matches...")
        matches_loaded = load_fact_matches_from_staging(session, 'statsbomb')
        logger.info(f"  Loaded {matches_loaded} fact matches")
        session.commit()
        
        # Load fact_events
        logger.info("Loading fact_events...")
        events_loaded = load_fact_events_from_staging(session, 'statsbomb')
        logger.info(f"  Loaded {events_loaded} fact events")
        session.commit()
        
        # Load fact_lineups
        logger.info("Loading fact_lineups...")
        lineups_loaded = load_fact_lineups_from_raw(session, 'statsbomb')
        logger.info(f"  Loaded {lineups_loaded} fact lineups")
        session.commit()
    
    logger.info("\n" + "=" * 60)
    logger.info("International Tournaments Ingestion Complete!")
    logger.info("=" * 60)
    
    # Print summary
    with get_session() as session:
        from src.ingestion.schemas import FactMatch, FactEvent, FactLineup, DimPlayer, DimTeam
        
        match_count = session.query(FactMatch).count()
        event_count = session.query(FactEvent).count()
        lineup_count = session.query(FactLineup).count()
        player_count = session.query(DimPlayer).count()
        team_count = session.query(DimTeam).count()
        
        logger.info(f"\nDatabase Summary:")
        logger.info(f"  - fact_matches: {match_count}")
        logger.info(f"  - fact_events: {event_count}")
        logger.info(f"  - fact_lineups: {lineup_count}")
        logger.info(f"  - dim_players: {player_count}")
        logger.info(f"  - dim_teams: {team_count}")


if __name__ == "__main__":
    main()
