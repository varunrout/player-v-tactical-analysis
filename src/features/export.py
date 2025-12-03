"""
Feature export utilities for persisting computed features to CSV files.

This module provides functions to compute features from the database and
export them to CSV files in the data/features/ directory.
"""
from pathlib import Path
from typing import Optional
from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session

from src.features.engineering import (
    FeatureBuilderFilters,
    build_player_match_features,
    build_team_match_features,
)
from src.ingestion.db import get_session


# Default output directory for feature CSVs
FEATURES_DIR = Path(__file__).parent.parent.parent / "data" / "features"


def ensure_features_dir() -> Path:
    """Ensure the features directory exists and return its path."""
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    return FEATURES_DIR


def export_player_match_features(
    session: Session,
    filters: Optional[FeatureBuilderFilters] = None,
    output_path: Optional[Path] = None,
) -> Path:
    """
    Compute player match features and export to CSV.
    
    Args:
        session: SQLAlchemy database session
        filters: Optional filters for feature computation
        output_path: Optional custom output path. If None, uses default naming.
    
    Returns:
        Path to the exported CSV file.
    """
    features_df = build_player_match_features(session, filters)
    
    if output_path is None:
        ensure_features_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = FEATURES_DIR / f"player_match_features_{timestamp}.csv"
    
    features_df.to_csv(output_path, index=False)
    print(f"Exported {len(features_df)} player match features to {output_path}")
    return output_path


def export_team_match_features(
    session: Session,
    filters: Optional[FeatureBuilderFilters] = None,
    output_path: Optional[Path] = None,
) -> Path:
    """
    Compute team match features and export to CSV.
    
    Args:
        session: SQLAlchemy database session
        filters: Optional filters for feature computation
        output_path: Optional custom output path. If None, uses default naming.
    
    Returns:
        Path to the exported CSV file.
    """
    features_df = build_team_match_features(session, filters)
    
    if output_path is None:
        ensure_features_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = FEATURES_DIR / f"team_match_features_{timestamp}.csv"
    
    features_df.to_csv(output_path, index=False)
    print(f"Exported {len(features_df)} team match features to {output_path}")
    return output_path


def export_all_features(
    session: Session,
    filters: Optional[FeatureBuilderFilters] = None,
) -> dict[str, Path]:
    """
    Compute and export all feature sets to CSV.
    
    Args:
        session: SQLAlchemy database session
        filters: Optional filters for feature computation
    
    Returns:
        Dictionary mapping feature type to output file path.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ensure_features_dir()
    
    paths = {}
    
    # Export player match features
    player_path = FEATURES_DIR / f"player_match_features_{timestamp}.csv"
    paths["player_match"] = export_player_match_features(session, filters, player_path)
    
    # Export team match features
    team_path = FEATURES_DIR / f"team_match_features_{timestamp}.csv"
    paths["team_match"] = export_team_match_features(session, filters, team_path)
    
    return paths


def run_feature_export():
    """
    Main entry point for exporting all features.
    
    Uses the default database connection and no filters.
    """
    with get_session() as session:
        print("Starting feature export...")
        paths = export_all_features(session)
        print("\nExport complete!")
        for feature_type, path in paths.items():
            print(f"  {feature_type}: {path}")


if __name__ == "__main__":
    run_feature_export()
