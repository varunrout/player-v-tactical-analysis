"""Tests for matchup engine module."""

import pytest
from src.matchup.matchup_engine import (
    TeamProfile,
    MatchupFeatures,
    MatchPrediction,
    TacticalNarrative,
    MatchupCalculator,
    ScorePredictionModel,
    TacticalNarrativeGenerator,
    MatchupEngine,
)


class TestTeamProfile:
    """Test TeamProfile data structure."""

    def test_default_values(self):
        """Test default values are set correctly."""
        profile = TeamProfile(team_id=1, team_name="Test FC")
        assert profile.ppda == 0.0
        assert profile.possession == 0.0
        assert profile.xg_per_match == 0.0

    def test_custom_values(self):
        """Test custom values are set correctly."""
        profile = TeamProfile(
            team_id=1,
            team_name="Test FC",
            ppda=8.5,
            possession=58.0,
            xg_per_match=1.8
        )
        assert profile.ppda == 8.5
        assert profile.possession == 58.0
        assert profile.xg_per_match == 1.8


class TestMatchupCalculator:
    """Test matchup feature calculation."""

    @pytest.fixture
    def high_pressing_team(self):
        """Create a high-pressing team profile."""
        return TeamProfile(
            team_id=1,
            team_name="High Press FC",
            ppda=7.5,
            high_press_pct=45.0,
            possession=52.0,
            gk_short_pct=60.0,
            progressive_passes=50.0,
            defensive_line_height=55.0,
            width_index=25.0,
            vertical_compactness=35.0,
            xg_per_match=1.8,
            xga_per_match=1.2,
            transition_attack_rate=12.0,
            aerial_win_rate=52.0
        )

    @pytest.fixture
    def possession_team(self):
        """Create a possession-based team profile."""
        return TeamProfile(
            team_id=2,
            team_name="Possession FC",
            ppda=12.0,
            high_press_pct=30.0,
            possession=62.0,
            gk_short_pct=80.0,
            progressive_passes=60.0,
            defensive_line_height=45.0,
            width_index=22.0,
            vertical_compactness=30.0,
            xg_per_match=1.9,
            xga_per_match=1.0,
            transition_attack_rate=8.0,
            aerial_win_rate=48.0
        )

    def test_calculate_matchup_features(self, high_pressing_team, possession_team):
        """Test basic matchup feature calculation."""
        calculator = MatchupCalculator()
        features = calculator.calculate_matchup_features(
            high_pressing_team, possession_team
        )

        assert features.team_a_id == 1
        assert features.team_b_id == 2

    def test_pressing_vs_buildup_asymmetric(self, high_pressing_team, possession_team):
        """Test asymmetric pressing vs buildup calculation."""
        calculator = MatchupCalculator()
        features = calculator.calculate_matchup_features(
            high_pressing_team, possession_team
        )

        # High pressing team should have positive pressing advantage
        # against possession team's patient buildup
        # But possession team's quality buildup should resist
        # The exact values depend on the formula

        assert features.pressing_vs_buildup_a != features.pressing_vs_buildup_b

    def test_tempo_difference(self, high_pressing_team, possession_team):
        """Test tempo difference calculation."""
        calculator = MatchupCalculator()
        features = calculator.calculate_matchup_features(
            high_pressing_team, possession_team
        )

        # Possession team has higher possession (62% vs 52%)
        expected_diff = 52.0 - 62.0  # -10
        assert features.tempo_difference == expected_diff

    def test_aerial_advantage(self, high_pressing_team, possession_team):
        """Test aerial advantage calculation."""
        calculator = MatchupCalculator()
        features = calculator.calculate_matchup_features(
            high_pressing_team, possession_team
        )

        # Team A has 52% aerial win rate, Team B has 48%
        assert features.aerial_advantage_a == 4.0


class TestScorePredictionModel:
    """Test score prediction model."""

    @pytest.fixture
    def predictor(self):
        """Create predictor with default settings."""
        return ScorePredictionModel(league_avg_goals=2.75)

    @pytest.fixture
    def balanced_teams(self):
        """Create two balanced teams."""
        team_a = TeamProfile(
            team_id=1,
            team_name="Team A",
            xg_per_match=1.5,
            xga_per_match=1.3
        )
        team_b = TeamProfile(
            team_id=2,
            team_name="Team B",
            xg_per_match=1.4,
            xga_per_match=1.4
        )
        return team_a, team_b

    def test_predict_match_returns_valid_probabilities(self, predictor, balanced_teams):
        """Test that probabilities sum to 1."""
        team_a, team_b = balanced_teams
        calculator = MatchupCalculator()
        features = calculator.calculate_matchup_features(team_a, team_b)

        prediction = predictor.predict_match(team_a, team_b, features, team_a_home=True)

        total_prob = prediction.team_a_win_prob + prediction.draw_prob + prediction.team_b_win_prob
        assert total_prob == pytest.approx(1.0, rel=0.01)

    def test_home_advantage_effect(self, predictor, balanced_teams):
        """Test that home team gets xG boost."""
        team_a, team_b = balanced_teams
        calculator = MatchupCalculator()
        features = calculator.calculate_matchup_features(team_a, team_b)

        pred_home = predictor.predict_match(team_a, team_b, features, team_a_home=True)
        pred_away = predictor.predict_match(team_a, team_b, features, team_a_home=False)

        # Team A should have higher xG when at home
        assert pred_home.xg_team_a > pred_away.xg_team_a

    def test_poisson_probability(self, predictor):
        """Test Poisson probability calculation."""
        # P(X=0) when lambda=1 should be e^(-1) ≈ 0.368
        prob = predictor._poisson_probability(1.0, 0)
        assert prob == pytest.approx(0.368, rel=0.01)

        # P(X=1) when lambda=1 should be e^(-1) ≈ 0.368
        prob = predictor._poisson_probability(1.0, 1)
        assert prob == pytest.approx(0.368, rel=0.01)

    def test_btts_probability(self, predictor):
        """Test both teams to score probability."""
        # High xG for both teams = high BTTS
        btts_high = predictor._calculate_btts_probability(2.0, 2.0)
        # Low xG for both teams = lower BTTS
        btts_low = predictor._calculate_btts_probability(0.5, 0.5)

        assert btts_high > btts_low
        assert 0 <= btts_high <= 1
        assert 0 <= btts_low <= 1


class TestTacticalNarrativeGenerator:
    """Test tactical narrative generation."""

    @pytest.fixture
    def generator(self):
        """Create narrative generator."""
        return TacticalNarrativeGenerator()

    @pytest.fixture
    def sample_matchup(self):
        """Create sample matchup data."""
        team_a = TeamProfile(
            team_id=1,
            team_name="High Press FC",
            ppda=7.5,
            high_press_pct=45.0,
            possession=52.0,
            transition_attack_rate=15.0
        )
        team_b = TeamProfile(
            team_id=2,
            team_name="Possession United",
            ppda=12.0,
            high_press_pct=25.0,
            possession=62.0,
            defensive_line_height=40.0
        )
        features = MatchupFeatures(
            team_a_id=1,
            team_b_id=2,
            pressing_vs_buildup_a=15.0,
            pressing_vs_buildup_b=-5.0,
            width_mismatch_a=5.0,
            transition_vulnerability_b=8.0,
            tempo_difference=-10.0
        )
        prediction = MatchPrediction(
            team_a_id=1,
            team_b_id=2,
            xg_team_a=1.6,
            xg_team_b=1.4,
            team_a_win_prob=0.42,
            draw_prob=0.28,
            team_b_win_prob=0.30,
            most_likely_score=(1, 1)
        )
        return team_a, team_b, features, prediction

    def test_generate_narrative_structure(self, generator, sample_matchup):
        """Test narrative has all required fields."""
        team_a, team_b, features, prediction = sample_matchup

        narrative = generator.generate_narrative(team_a, team_b, features, prediction)

        assert narrative.team_a_name == "High Press FC"
        assert narrative.team_b_name == "Possession United"
        assert narrative.clash_summary != ""
        assert isinstance(narrative.key_battles, list)
        assert isinstance(narrative.team_a_advantages, list)
        assert isinstance(narrative.team_b_advantages, list)
        assert narrative.prediction_rationale != ""

    def test_classify_style(self, generator):
        """Test style classification."""
        # High pressing team
        pressing_team = TeamProfile(
            team_id=1,
            team_name="Test",
            ppda=7.0,
            high_press_pct=45.0
        )
        style = generator._classify_style(pressing_team)
        assert "pressing" in style.lower() or "intense" in style.lower()

        # Possession team
        possession_team = TeamProfile(
            team_id=2,
            team_name="Test",
            ppda=12.0,
            possession=58.0
        )
        style = generator._classify_style(possession_team)
        assert "possession" in style.lower()


class TestMatchupEngine:
    """Test complete matchup engine."""

    def test_analyze_matchup(self):
        """Test complete matchup analysis."""
        engine = MatchupEngine()

        team_a = TeamProfile(
            team_id=1,
            team_name="Team A",
            ppda=8.0,
            possession=55.0,
            xg_per_match=1.7,
            xga_per_match=1.2
        )
        team_b = TeamProfile(
            team_id=2,
            team_name="Team B",
            ppda=10.0,
            possession=52.0,
            xg_per_match=1.5,
            xga_per_match=1.4
        )

        result = engine.analyze_matchup(team_a, team_b, team_a_home=True)

        assert 'matchup_features' in result
        assert 'prediction' in result
        assert 'narrative' in result

        # Check prediction probabilities sum to 1
        pred = result['prediction']
        total = pred.team_a_win_prob + pred.draw_prob + pred.team_b_win_prob
        assert total == pytest.approx(1.0, rel=0.01)
