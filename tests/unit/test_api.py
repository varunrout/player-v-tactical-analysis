"""Tests for FastAPI application."""

import pytest
from fastapi.testclient import TestClient
from src.api.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_root_returns_healthy(self, client):
        """Test root endpoint returns healthy status."""
        response = client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "timestamp" in data


class TestEvolutionEndpoint:
    """Test evolution analysis endpoint."""

    def test_get_team_evolution(self, client):
        """Test getting team evolution data."""
        response = client.get("/evolution/1")
        assert response.status_code == 200

        data = response.json()
        assert "team_id" in data
        assert "team_name" in data
        assert "current_season" in data
        assert "evolution_history" in data
        assert "key_evolution_insights" in data

    def test_get_team_evolution_with_params(self, client):
        """Test evolution with query parameters."""
        response = client.get("/evolution/1?seasons=10&include_era_analysis=true")
        assert response.status_code == 200

    def test_evolution_history_structure(self, client):
        """Test evolution history data structure."""
        response = client.get("/evolution/1")
        data = response.json()

        assert isinstance(data["evolution_history"], list)
        if data["evolution_history"]:
            history_point = data["evolution_history"][0]
            assert "season" in history_point
            assert "ppda" in history_point
            assert "possession" in history_point


class TestForecastEndpoint:
    """Test forecasting endpoint."""

    def test_get_team_forecast(self, client):
        """Test getting team forecast."""
        response = client.get("/forecast/1")
        assert response.status_code == 200

        data = response.json()
        assert "team_id" in data
        assert "predictions" in data
        assert "model_version" in data

    def test_forecast_predictions_structure(self, client):
        """Test forecast predictions have confidence intervals."""
        response = client.get("/forecast/1")
        data = response.json()

        predictions = data["predictions"]
        assert "ppda" in predictions

        ppda_pred = predictions["ppda"]
        assert "predicted_value" in ppda_pred
        assert "lower_bound" in ppda_pred
        assert "upper_bound" in ppda_pred

    def test_forecast_with_target_season(self, client):
        """Test forecast with specific target season."""
        response = client.get("/forecast/1?target_season=2024/25")
        assert response.status_code == 200

        data = response.json()
        assert data["target_season"] == "2024/25"


class TestMatchupEndpoint:
    """Test matchup analysis endpoint."""

    def test_get_matchup_analysis(self, client):
        """Test getting matchup analysis."""
        response = client.get("/matchup/1/2")
        assert response.status_code == 200

        data = response.json()
        assert "team_a" in data
        assert "team_b" in data
        assert "prediction" in data
        assert "tactical_analysis" in data

    def test_matchup_prediction_probabilities(self, client):
        """Test matchup probabilities sum to ~1."""
        response = client.get("/matchup/1/2")
        data = response.json()

        probs = data["prediction"]["probabilities"]
        total = probs["team_a_win"] + probs["draw"] + probs["team_b_win"]
        assert 0.99 <= total <= 1.01

    def test_matchup_with_home_away(self, client):
        """Test matchup with home/away parameter."""
        response = client.get("/matchup/1/2?team_a_home=false")
        assert response.status_code == 200

    def test_matchup_tactical_analysis(self, client):
        """Test tactical analysis content."""
        response = client.get("/matchup/1/2")
        data = response.json()

        tactical = data["tactical_analysis"]
        assert "clash_summary" in tactical
        assert "key_battles" in tactical
        assert "team_a_advantages" in tactical
        assert "team_b_advantages" in tactical
        assert "prediction_rationale" in tactical


class TestVarianceDecompositionEndpoint:
    """Test variance decomposition endpoint."""

    def test_get_variance_decomposition(self, client):
        """Test variance decomposition analysis."""
        response = client.get("/variance-decomposition")
        assert response.status_code == 200

        data = response.json()
        assert "target" in data
        assert "skill_contribution" in data
        assert "tactics_contribution" in data
        assert "interpretation" in data

    def test_decomposition_with_target(self, client):
        """Test decomposition for specific target."""
        response = client.get("/variance-decomposition?target=possession_avg")
        assert response.status_code == 200

        data = response.json()
        assert data["target"] == "possession_avg"


class TestNaturalExperimentsEndpoint:
    """Test natural experiments endpoint."""

    def test_get_natural_experiments(self, client):
        """Test natural experiments analysis."""
        response = client.get("/natural-experiments")
        assert response.status_code == 200

        data = response.json()
        assert "experiment_type" in data
        assert "experiments" in data
        assert "aggregate_finding" in data

    def test_experiments_by_type(self, client):
        """Test filtering by experiment type."""
        response = client.get("/natural-experiments?experiment_type=star_player")
        assert response.status_code == 200

        data = response.json()
        assert data["experiment_type"] == "star_player"


class TestTeamsEndpoint:
    """Test teams listing endpoint."""

    def test_list_teams(self, client):
        """Test listing teams."""
        response = client.get("/teams")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

    def test_list_teams_with_filters(self, client):
        """Test listing teams with filters."""
        response = client.get("/teams?competition=Premier League&limit=10")
        assert response.status_code == 200
