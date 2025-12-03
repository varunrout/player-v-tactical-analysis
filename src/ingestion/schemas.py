"""
Database Schema Definitions for Football Evolution Analysis

This module defines the SQLAlchemy ORM models for:
- Raw data tables (raw_*)
- Staging tables (stg_*)
- Dimension tables (dim_*)
- Fact tables (fact_*)
"""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date, Boolean,
    ForeignKey, Text, JSON, Index, UniqueConstraint, Enum as SQLEnum
)
from sqlalchemy.orm import relationship, declarative_base
from enum import Enum

Base = declarative_base()


# ============================================================================
# ENUMS
# ============================================================================

class CompetitionType(Enum):
    LEAGUE = "league"
    CUP = "cup"
    CONTINENTAL = "continental"
    INTERNATIONAL = "international"


class MatchStatus(Enum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"


class EventType(Enum):
    PASS = "pass"
    SHOT = "shot"
    DRIBBLE = "dribble"
    TACKLE = "tackle"
    INTERCEPTION = "interception"
    CLEARANCE = "clearance"
    FOUL = "foul"
    PRESSURE = "pressure"
    CARRY = "carry"
    DUEL = "duel"
    BALL_RECOVERY = "ball_recovery"
    BLOCK = "block"
    GOAL_KEEPER = "goal_keeper"
    SUBSTITUTION = "substitution"
    CARD = "card"


# ============================================================================
# RAW LAYER - Unprocessed data from source APIs
# ============================================================================

class RawMatch(Base):
    """Raw match data as received from source APIs."""
    __tablename__ = "raw_match"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False)  # e.g., 'statsbomb', 'wyscout', 'opta'
    source_match_id = Column(String(100), nullable=False)
    raw_json = Column(JSON, nullable=False)
    ingested_at = Column(DateTime, default=datetime.utcnow)
    processed = Column(Boolean, default=False)
    processing_errors = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint('source', 'source_match_id', name='uq_raw_match_source'),
        Index('ix_raw_match_processed', 'processed'),
    )


class RawEvent(Base):
    """Raw event data as received from source APIs."""
    __tablename__ = "raw_event"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False)
    source_event_id = Column(String(100), nullable=False)
    source_match_id = Column(String(100), nullable=False)
    raw_json = Column(JSON, nullable=False)
    ingested_at = Column(DateTime, default=datetime.utcnow)
    processed = Column(Boolean, default=False)
    processing_errors = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint('source', 'source_event_id', name='uq_raw_event_source'),
        Index('ix_raw_event_match', 'source_match_id'),
        Index('ix_raw_event_processed', 'processed'),
    )


class RawLineup(Base):
    """Raw lineup data as received from source APIs."""
    __tablename__ = "raw_lineup"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False)
    source_match_id = Column(String(100), nullable=False)
    source_team_id = Column(String(100), nullable=False)
    raw_json = Column(JSON, nullable=False)
    ingested_at = Column(DateTime, default=datetime.utcnow)
    processed = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint('source', 'source_match_id', 'source_team_id', name='uq_raw_lineup_source'),
    )


class RawPlayer(Base):
    """Raw player data as received from source APIs."""
    __tablename__ = "raw_player"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False)
    source_player_id = Column(String(100), nullable=False)
    raw_json = Column(JSON, nullable=False)
    ingested_at = Column(DateTime, default=datetime.utcnow)
    processed = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint('source', 'source_player_id', name='uq_raw_player_source'),
    )


class RawTeam(Base):
    """Raw team data as received from source APIs."""
    __tablename__ = "raw_team"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False)
    source_team_id = Column(String(100), nullable=False)
    raw_json = Column(JSON, nullable=False)
    ingested_at = Column(DateTime, default=datetime.utcnow)
    processed = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint('source', 'source_team_id', name='uq_raw_team_source'),
    )


# ============================================================================
# STAGING LAYER - Cleaned and standardized data
# ============================================================================

class StgMatch(Base):
    """Staging table for cleaned match data."""
    __tablename__ = "stg_match"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False)
    source_match_id = Column(String(100), nullable=False)

    # Standardized fields
    home_team_source_id = Column(String(100), nullable=False)
    away_team_source_id = Column(String(100), nullable=False)
    competition_source_id = Column(String(100), nullable=False)
    competition_name = Column(String(200), nullable=True)
    season_name = Column(String(50), nullable=False)  # e.g., "2023/2024"
    home_team_name = Column(String(200), nullable=True)
    away_team_name = Column(String(200), nullable=True)
    match_date = Column(Date, nullable=False)
    match_time = Column(String(10), nullable=True)  # HH:MM
    match_week = Column(Integer, nullable=True)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    status = Column(String(20), nullable=True)
    competition_stage = Column(String(100), nullable=True)
    stadium = Column(String(200), nullable=True)
    referee = Column(String(100), nullable=True)
    attendance = Column(Integer, nullable=True)

    # Metadata
    processed_at = Column(DateTime, default=datetime.utcnow)
    validated = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint('source', 'source_match_id', name='uq_stg_match_source'),
    )


class StgEvent(Base):
    """Staging table for cleaned event data."""
    __tablename__ = "stg_event"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False)
    source_event_id = Column(String(100), nullable=False)
    source_match_id = Column(String(100), nullable=False)

    # Standardized fields
    event_type = Column(String(50), nullable=False)
    event_subtype = Column(String(100), nullable=True)
    minute = Column(Integer, nullable=False)
    second = Column(Integer, nullable=True)
    period = Column(Integer, nullable=False)  # 1 = first half, 2 = second half, etc.

    # Location (normalized 0-100 coordinate system)
    location_x = Column(Float, nullable=True)
    location_y = Column(Float, nullable=True)
    end_location_x = Column(Float, nullable=True)
    end_location_y = Column(Float, nullable=True)

    # Player/Team
    player_source_id = Column(String(100), nullable=True)
    team_source_id = Column(String(100), nullable=False)

    # Outcome
    outcome = Column(String(50), nullable=True)
    is_successful = Column(Boolean, nullable=True)

    # Additional data
    extra_data = Column(JSON, nullable=True)

    # Metadata
    processed_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_stg_event_match', 'source_match_id'),
        Index('ix_stg_event_type', 'event_type'),
    )


class StgPlayer(Base):
    """Staging table for cleaned player data."""
    __tablename__ = "stg_player"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False)
    source_player_id = Column(String(100), nullable=False)

    # Standardized fields
    name = Column(String(200), nullable=False)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    nationality = Column(String(100), nullable=True)
    position = Column(String(50), nullable=True)
    height_cm = Column(Integer, nullable=True)
    weight_kg = Column(Integer, nullable=True)
    preferred_foot = Column(String(10), nullable=True)

    processed_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('source', 'source_player_id', name='uq_stg_player_source'),
    )


class StgTeam(Base):
    """Staging table for cleaned team data."""
    __tablename__ = "stg_team"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False)
    source_team_id = Column(String(100), nullable=False)

    # Standardized fields
    name = Column(String(200), nullable=False)
    short_name = Column(String(50), nullable=True)
    country = Column(String(100), nullable=True)
    stadium = Column(String(200), nullable=True)

    processed_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('source', 'source_team_id', name='uq_stg_team_source'),
    )


# ============================================================================
# DIMENSION TABLES - Core entities
# ============================================================================

class DimTeam(Base):
    """Dimension table for teams."""
    __tablename__ = "dim_team"

    team_id = Column(Integer, primary_key=True, autoincrement=True)
    team_name = Column(String(200), nullable=False)
    team_short_name = Column(String(50), nullable=True)
    country = Column(String(100), nullable=True)
    founded_year = Column(Integer, nullable=True)
    stadium = Column(String(200), nullable=True)

    # Source mappings
    statsbomb_id = Column(String(100), nullable=True)
    wyscout_id = Column(String(100), nullable=True)
    opta_id = Column(String(100), nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class DimPlayer(Base):
    """Dimension table for players."""
    __tablename__ = "dim_player"

    player_id = Column(Integer, primary_key=True, autoincrement=True)
    player_name = Column(String(200), nullable=False)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    nationality = Column(String(100), nullable=True)
    primary_position = Column(String(50), nullable=True)
    height_cm = Column(Integer, nullable=True)
    weight_kg = Column(Integer, nullable=True)
    preferred_foot = Column(String(10), nullable=True)

    # Source mappings
    statsbomb_id = Column(String(100), nullable=True)
    wyscout_id = Column(String(100), nullable=True)
    opta_id = Column(String(100), nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class DimManager(Base):
    """Dimension table for managers."""
    __tablename__ = "dim_manager"

    manager_id = Column(Integer, primary_key=True, autoincrement=True)
    manager_name = Column(String(200), nullable=False)
    date_of_birth = Column(Date, nullable=True)
    nationality = Column(String(100), nullable=True)
    playing_career_end = Column(Date, nullable=True)

    # Tactical profile
    primary_formation = Column(String(20), nullable=True)
    tactical_style = Column(String(100), nullable=True)  # e.g., "possession", "counter-pressing"

    # Source mappings
    statsbomb_id = Column(String(100), nullable=True)
    wyscout_id = Column(String(100), nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DimSeason(Base):
    """Dimension table for seasons."""
    __tablename__ = "dim_season"

    season_id = Column(Integer, primary_key=True, autoincrement=True)
    season_name = Column(String(50), nullable=False)  # e.g., "2023/2024"
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    era = Column(String(50), nullable=True)  # e.g., "Pressing Renaissance"

    __table_args__ = (
        UniqueConstraint('season_name', name='uq_dim_season_name'),
    )


class DimCompetition(Base):
    """Dimension table for competitions."""
    __tablename__ = "dim_competition"

    competition_id = Column(Integer, primary_key=True, autoincrement=True)
    competition_name = Column(String(200), nullable=False)
    competition_short_name = Column(String(50), nullable=True)
    country = Column(String(100), nullable=True)
    competition_type = Column(String(20), nullable=True)  # league, cup, continental
    tier = Column(Integer, nullable=True)  # 1 = top division

    # Source mappings
    statsbomb_id = Column(String(100), nullable=True)
    wyscout_id = Column(String(100), nullable=True)
    opta_id = Column(String(100), nullable=True)


# ============================================================================
# FACT TABLES - Transactional data
# ============================================================================

class FactMatch(Base):
    """Fact table for matches."""
    __tablename__ = "fact_match"

    match_id = Column(Integer, primary_key=True, autoincrement=True)

    # Dimensions
    home_team_id = Column(Integer, ForeignKey('dim_team.team_id'), nullable=False)
    away_team_id = Column(Integer, ForeignKey('dim_team.team_id'), nullable=False)
    competition_id = Column(Integer, ForeignKey('dim_competition.competition_id'), nullable=False)
    season_id = Column(Integer, ForeignKey('dim_season.season_id'), nullable=False)
    home_manager_id = Column(Integer, ForeignKey('dim_manager.manager_id'), nullable=True)
    away_manager_id = Column(Integer, ForeignKey('dim_manager.manager_id'), nullable=True)

    # Match details
    match_date = Column(Date, nullable=False)
    match_time = Column(String(10), nullable=True)
    matchweek = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False)

    # Scores
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    home_score_ht = Column(Integer, nullable=True)
    away_score_ht = Column(Integer, nullable=True)

    # Match metrics
    home_xg = Column(Float, nullable=True)
    away_xg = Column(Float, nullable=True)
    home_possession = Column(Float, nullable=True)
    away_possession = Column(Float, nullable=True)

    # Formations
    home_formation = Column(String(20), nullable=True)
    away_formation = Column(String(20), nullable=True)

    # Venue
    stadium = Column(String(200), nullable=True)
    attendance = Column(Integer, nullable=True)
    referee = Column(String(100), nullable=True)

    # Source tracking
    source = Column(String(50), nullable=False)
    source_match_id = Column(String(100), nullable=False)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    home_team = relationship("DimTeam", foreign_keys=[home_team_id])
    away_team = relationship("DimTeam", foreign_keys=[away_team_id])
    competition = relationship("DimCompetition")
    season = relationship("DimSeason")

    __table_args__ = (
        Index('ix_fact_match_date', 'match_date'),
        Index('ix_fact_match_season', 'season_id'),
        Index('ix_fact_match_competition', 'competition_id'),
        UniqueConstraint('source', 'source_match_id', name='uq_fact_match_source'),
    )


class FactEvent(Base):
    """Fact table for match events."""
    __tablename__ = "fact_event"

    event_id = Column(Integer, primary_key=True, autoincrement=True)

    # Dimensions
    match_id = Column(Integer, ForeignKey('fact_match.match_id'), nullable=False)
    team_id = Column(Integer, ForeignKey('dim_team.team_id'), nullable=False)
    player_id = Column(Integer, ForeignKey('dim_player.player_id'), nullable=True)

    # Event details
    event_type = Column(String(50), nullable=False)
    event_subtype = Column(String(100), nullable=True)
    minute = Column(Integer, nullable=False)
    second = Column(Integer, nullable=True)
    period = Column(Integer, nullable=False)

    # Location
    location_x = Column(Float, nullable=True)
    location_y = Column(Float, nullable=True)
    end_location_x = Column(Float, nullable=True)
    end_location_y = Column(Float, nullable=True)

    # Outcome
    outcome = Column(String(50), nullable=True)
    is_successful = Column(Boolean, nullable=True)

    # Advanced metrics
    xg = Column(Float, nullable=True)  # For shots
    pass_length = Column(Float, nullable=True)
    pass_angle = Column(Float, nullable=True)
    carry_distance = Column(Float, nullable=True)

    # Tactical context
    possession_sequence_id = Column(Integer, nullable=True)
    is_progressive = Column(Boolean, nullable=True)  # Progressive pass/carry
    is_under_pressure = Column(Boolean, nullable=True)

    # Source tracking
    source = Column(String(50), nullable=False)
    source_event_id = Column(String(100), nullable=False)

    # Extra data
    extra_data = Column(JSON, nullable=True)

    __table_args__ = (
        Index('ix_fact_event_match', 'match_id'),
        Index('ix_fact_event_type', 'event_type'),
        Index('ix_fact_event_player', 'player_id'),
    )


class FactLineup(Base):
    """Fact table for match lineups."""
    __tablename__ = "fact_lineup"

    lineup_id = Column(Integer, primary_key=True, autoincrement=True)

    # Dimensions
    match_id = Column(Integer, ForeignKey('fact_match.match_id'), nullable=False)
    team_id = Column(Integer, ForeignKey('dim_team.team_id'), nullable=False)
    player_id = Column(Integer, ForeignKey('dim_player.player_id'), nullable=False)

    # Lineup details
    is_starter = Column(Boolean, nullable=False)
    position = Column(String(50), nullable=True)
    jersey_number = Column(Integer, nullable=True)
    captain = Column(Boolean, default=False)

    # Playing time
    minutes_played = Column(Integer, nullable=True)
    sub_on_minute = Column(Integer, nullable=True)
    sub_off_minute = Column(Integer, nullable=True)

    # Average position (from event data)
    avg_position_x = Column(Float, nullable=True)
    avg_position_y = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint('match_id', 'player_id', name='uq_lineup_match_player'),
        Index('ix_fact_lineup_match', 'match_id'),
    )


# ============================================================================
# TEAM MANAGER HISTORY - Track manager changes for natural experiments
# ============================================================================

class TeamManagerHistory(Base):
    """Track manager tenures at teams."""
    __tablename__ = "team_manager_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, ForeignKey('dim_team.team_id'), nullable=False)
    manager_id = Column(Integer, ForeignKey('dim_manager.manager_id'), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)  # NULL = current manager
    is_interim = Column(Boolean, default=False)

    # Performance during tenure
    matches = Column(Integer, nullable=True)
    wins = Column(Integer, nullable=True)
    draws = Column(Integer, nullable=True)
    losses = Column(Integer, nullable=True)

    team = relationship("DimTeam")
    manager = relationship("DimManager")

    __table_args__ = (
        Index('ix_manager_history_team', 'team_id'),
        Index('ix_manager_history_dates', 'start_date', 'end_date'),
    )


# ============================================================================
# PLAYER TRANSFER HISTORY - Track player movements for natural experiments
# ============================================================================

class PlayerTransferHistory(Base):
    """Track player transfers between teams."""
    __tablename__ = "player_transfer_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey('dim_player.player_id'), nullable=False)
    from_team_id = Column(Integer, ForeignKey('dim_team.team_id'), nullable=True)
    to_team_id = Column(Integer, ForeignKey('dim_team.team_id'), nullable=False)
    transfer_date = Column(Date, nullable=False)
    transfer_type = Column(String(50), nullable=True)  # permanent, loan, free
    fee_euros = Column(Float, nullable=True)
    contract_end_date = Column(Date, nullable=True)

    player = relationship("DimPlayer")
    from_team = relationship("DimTeam", foreign_keys=[from_team_id])
    to_team = relationship("DimTeam", foreign_keys=[to_team_id])

    __table_args__ = (
        Index('ix_transfer_player', 'player_id'),
        Index('ix_transfer_date', 'transfer_date'),
    )
