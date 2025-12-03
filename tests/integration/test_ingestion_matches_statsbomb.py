import os

import pytest

from src.ingestion.pipeline import (
    PipelineConfig,
    JobIngestMatches,
    JobStageMatches,
    load_fact_matches_from_staging,
)
from src.ingestion.db import init_db, get_session
from src.ingestion.schemas import RawMatch, StgMatch, FactMatch


@pytest.mark.skipif(
    os.getenv("SKIP_STATSBOMB_HTTP", "1") == "1",
    reason="Skipping live StatsBomb Open HTTP calls by default",
)
def test_end_to_end_matches_ingestion_statsbomb(tmp_path, monkeypatch):
    """End-to-end test: StatsBomb Open -> RawMatch -> StgMatch -> FactMatch.

    Uses a temporary SQLite database so it does not touch the main DB.
    """

    # Point DATABASE_URL at a temp SQLite DB
    db_path = tmp_path / "evolution_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    # Re-initialise DB schema against the temp DB
    init_db()

    source = "statsbomb"
    config = PipelineConfig(source=source)

    # Premier League 2019/2020: competition_id=43, season_id inferred from end_date
    competition_ids = ["43"]
    start_date = "2019-08-01"
    end_date = "2020-07-31"

    # 1) Ingest raw matches from StatsBomb Open
    ingest_job = JobIngestMatches(config, start_date, end_date, competition_ids)
    ingest_result = ingest_job.run()
    assert ingest_result.status == "success"
    assert ingest_result.records_processed > 0

    with get_session() as session:
        raw_count = session.query(RawMatch).count()
        assert raw_count == ingest_result.records_processed

    # 2) Stage matches
    stage_job = JobStageMatches(config)
    stage_result = stage_job.run()
    assert stage_result.status == "success"
    assert stage_result.records_processed > 0

    with get_session() as session:
        stg_count = session.query(StgMatch).count()
        assert stg_count == stage_result.records_processed

        # 3) Materialize fact matches
        created = load_fact_matches_from_staging(session, source=source)
        assert created > 0

        fact_count = session.query(FactMatch).count()
        assert fact_count == created
