#!/usr/bin/env python3
"""
Batch event staging script for large datasets.
Processes events in batches to avoid memory issues.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy import func, and_

from src.ingestion.db import get_session
from src.ingestion.schemas import RawEvent, StgEvent, FactEvent, FactMatch
from src.ingestion.pipeline import JobStageEvents, PipelineConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_unprocessed_match_ids(session) -> List[str]:
    """Get match IDs that have raw events but no staged events."""
    # Get all match IDs from raw_events
    raw_match_ids = set(
        row[0] for row in session.query(RawEvent.source_match_id)
        .filter(RawEvent.source == 'statsbomb')
        .distinct()
        .all()
    )
    
    # Get match IDs already in stg_events
    staged_match_ids = set(
        row[0] for row in session.query(StgEvent.source_match_id)
        .filter(StgEvent.source == 'statsbomb')
        .distinct()
        .all()
    )
    
    # Return matches that need staging
    return list(raw_match_ids - staged_match_ids)


def stage_events_for_match(match_id: str, config: PipelineConfig) -> int:
    """Stage events for a single match."""
    job = JobStageEvents(config, match_ids=[match_id])
    result = job.run()
    return result.records_processed


def load_fact_events_for_match(session, source: str, match_id: str) -> int:
    """Load fact_events for a specific match."""
    # Get the fact_match for this source_match_id
    fact_match = session.query(FactMatch).filter(
        FactMatch.source == source,
        FactMatch.source_match_id == match_id
    ).one_or_none()
    
    if not fact_match:
        return 0
    
    # Get staged events for this match that aren't already in fact_events
    staged_events = session.query(StgEvent).filter(
        StgEvent.source == source,
        StgEvent.source_match_id == match_id
    ).all()
    
    existing_event_ids = set(
        row[0] for row in session.query(FactEvent.source_event_id)
        .filter(FactEvent.match_id == fact_match.match_id)
        .all()
    )
    
    created = 0
    for stg in staged_events:
        if stg.source_event_id in existing_event_ids:
            continue
        
        fact_event = FactEvent(
            match_id=fact_match.match_id,
            source=source,
            source_event_id=stg.source_event_id,
            event_type=stg.event_type,
            event_subtype=stg.event_subtype,
            minute=stg.minute,
            second=stg.second,
            period=stg.period,
            team_id=stg.team_source_id,  # Will be resolved later
            player_id=stg.player_source_id,  # Will be resolved later
            location_x=stg.location_x,
            location_y=stg.location_y,
            end_location_x=stg.end_location_x,
            end_location_y=stg.end_location_y,
            is_successful=stg.is_successful,
            extra_data=stg.extra_data,
        )
        session.add(fact_event)
        created += 1
    
    return created


def main():
    """Run batched event staging."""
    config = PipelineConfig(source='statsbomb')
    
    with get_session() as session:
        unprocessed = get_unprocessed_match_ids(session)
        logger.info(f"Found {len(unprocessed)} matches with unstaged events")
    
    if not unprocessed:
        logger.info("No events to stage!")
        return
    
    total_staged = 0
    total_loaded = 0
    
    for i, match_id in enumerate(unprocessed):
        try:
            # Stage events for this match
            staged = stage_events_for_match(match_id, config)
            total_staged += staged
            
            # Load fact_events for this match
            with get_session() as session:
                loaded = load_fact_events_for_match(session, 'statsbomb', match_id)
                session.commit()
                total_loaded += loaded
            
            if (i + 1) % 10 == 0:
                logger.info(f"Progress: {i + 1}/{len(unprocessed)} matches, {total_staged} staged, {total_loaded} loaded")
                
        except Exception as e:
            logger.error(f"Failed to process match {match_id}: {e}")
            continue
    
    logger.info(f"Done! Staged {total_staged} events, loaded {total_loaded} fact_events")
    
    # Print final counts
    with get_session() as session:
        stg_count = session.query(StgEvent).count()
        fact_count = session.query(FactEvent).count()
        logger.info(f"Final counts: stg_events={stg_count}, fact_events={fact_count}")


if __name__ == "__main__":
    main()
