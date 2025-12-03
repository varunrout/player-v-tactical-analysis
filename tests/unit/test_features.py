"""Tests for feature engineering module."""

import pandas as pd
import pytest
from src.features.engineering import (
    TeamMatchStyle,
    TeamMatchStyleCalculator,
    TeamSeasonStyle,
    aggregate_season_style,
    PlayerSeasonProfile,
    PlayerProfileCalculator,
    SquadSeasonSkill,
    aggregate_squad_skill,
    PITCH_ZONES,
    compute_player_match_features_from_events,
    compute_team_match_features_from_events,
)


class TestPitchZones:
    """Test pitch zone definitions."""

    def test_defensive_third_boundaries(self):
        """Test defensive third zone boundaries."""
        zone = PITCH_ZONES['defensive_third']
        assert zone.contains(0, 50)
        assert zone.contains(33, 50)
        assert not zone.contains(34, 50)

    def test_attacking_third_boundaries(self):
        """Test attacking third zone boundaries."""
        zone = PITCH_ZONES['attacking_third']
        assert zone.contains(67, 50)
        assert zone.contains(100, 50)
        assert not zone.contains(66, 50)

    def test_box_zone(self):
        """Test penalty box zone."""
        zone = PITCH_ZONES['box']
        assert zone.contains(90, 50)  # Inside box
        assert not zone.contains(80, 50)  # Outside box


class TestTeamMatchStyleCalculator:
    """Test team match style calculation."""

    @pytest.fixture
    def sample_events(self):
        """Create sample event data."""
        return [
            {
                'event_type': 'pass',
                'team_id': 1,
                'player_id': 101,
                'is_successful': True,
                'location_x': 30,
                'location_y': 40,
                'end_location_x': 50,
                'end_location_y': 45,
                'extra_data': '{"pass_length": 25}'
            },
            {
                'event_type': 'pass',
                'team_id': 1,
                'player_id': 102,
                'is_successful': True,
                'location_x': 50,
                'location_y': 50,
                'end_location_x': 70,
                'end_location_y': 55,
                'extra_data': '{"pass_length": 22}'
            },
            {
                'event_type': 'pass',
                'team_id': 2,
                'player_id': 201,
                'is_successful': True,
                'location_x': 40,
                'location_y': 50,
                'end_location_x': 45,
                'end_location_y': 50,
                'extra_data': '{"pass_length": 5}'
            },
            {
                'event_type': 'shot',
                'team_id': 1,
                'player_id': 101,
                'outcome': 'Goal',
                'location_x': 90,
                'location_y': 50,
                'extra_data': '{"xg": 0.35}'
            },
            {
                'event_type': 'pressure',
                'team_id': 1,
                'player_id': 102,
                'location_x': 75,
                'location_y': 50,
            },
            {
                'event_type': 'tackle',
                'team_id': 1,
                'player_id': 103,
                'is_successful': True,
                'location_x': 60,
                'location_y': 40,
            },
        ]

    def test_calculate_basic_style(self, sample_events):
        """Test basic style calculation."""
        calculator = TeamMatchStyleCalculator(sample_events, match_duration_minutes=90)
        style = calculator.calculate(match_id=1, team_id=1, is_home=True)

        assert style.match_id == 1
        assert style.team_id == 1
        assert style.is_home is True

    def test_possession_calculation(self, sample_events):
        """Test possession percentage calculation."""
        calculator = TeamMatchStyleCalculator(sample_events)
        style = calculator.calculate(match_id=1, team_id=1, is_home=True)

        # Team 1 has 2 passes, Team 2 has 1 pass = 66.67% possession
        assert style.passes_total == 2
        assert 66 <= style.possession_pct <= 67

    def test_shot_metrics(self, sample_events):
        """Test shot and xG calculation."""
        calculator = TeamMatchStyleCalculator(sample_events)
        style = calculator.calculate(match_id=1, team_id=1, is_home=True)

        assert style.shots == 1
        assert style.xg_total == 0.35
        assert style.xg_per_shot == 0.35

    def test_defensive_metrics(self, sample_events):
        """Test defensive action counting."""
        calculator = TeamMatchStyleCalculator(sample_events)
        style = calculator.calculate(match_id=1, team_id=1, is_home=True)

        assert style.tackles == 1
        assert style.pressures_total == 1

    def test_progressive_pass_detection(self, sample_events):
        """Test progressive pass identification."""
        calculator = TeamMatchStyleCalculator(sample_events)
        style = calculator.calculate(match_id=1, team_id=1, is_home=True)

        # First pass moves 20 yards forward (30 -> 50), so it's progressive
        assert style.progressive_passes >= 1


class TestTeamSeasonStyleAggregation:
    """Test season-level style aggregation."""

    def test_aggregate_empty_list(self):
        """Test aggregation with empty list."""
        result = aggregate_season_style([], season_id=1)
        assert result.team_id == 0
        assert result.matches_played == 0

    def test_aggregate_single_match(self):
        """Test aggregation with single match."""
        match_style = TeamMatchStyle(
            match_id=1,
            team_id=10,
            is_home=True,
            ppda=8.5,
            possession_pct=55.0,
            xg_per_shot=0.12
        )

        result = aggregate_season_style([match_style], season_id=1)

        assert result.team_id == 10
        assert result.season_id == 1
        assert result.matches_played == 1
        assert result.ppda_avg == 8.5
        assert result.possession_avg == 55.0
        assert result.xg_per_shot_avg == 0.12

    def test_aggregate_multiple_matches(self):
        """Test aggregation with multiple matches."""
        matches = [
            TeamMatchStyle(match_id=1, team_id=10, is_home=True, ppda=8.0, possession_pct=55.0),
            TeamMatchStyle(match_id=2, team_id=10, is_home=False, ppda=10.0, possession_pct=50.0),
            TeamMatchStyle(match_id=3, team_id=10, is_home=True, ppda=9.0, possession_pct=60.0),
        ]

        result = aggregate_season_style(matches, season_id=1)

        assert result.matches_played == 3
        assert result.ppda_avg == 9.0  # (8 + 10 + 9) / 3
        assert result.possession_avg == 55.0  # (55 + 50 + 60) / 3


class TestPlayerProfileCalculator:
    """Test player profile calculation."""

    @pytest.fixture
    def player_events(self):
        """Create sample player events."""
        return [
            {
                'event_type': 'pass',
                'player_id': 101,
                'is_successful': True,
                'location_x': 40,
                'location_y': 50,
                'end_location_x': 55,
                'end_location_y': 50,
                'extra_data': '{}'
            },
            {
                'event_type': 'pass',
                'player_id': 101,
                'is_successful': True,
                'location_x': 50,
                'location_y': 50,
                'end_location_x': 60,
                'end_location_y': 50,
                'extra_data': '{}'
            },
            {
                'event_type': 'pass',
                'player_id': 101,
                'is_successful': False,
                'location_x': 60,
                'location_y': 50,
                'end_location_x': 70,
                'end_location_y': 50,
                'extra_data': '{}'
            },
            {
                'event_type': 'dribble',
                'player_id': 101,
                'is_successful': True,
            },
            {
                'event_type': 'shot',
                'player_id': 101,
                'outcome': 'Saved',
                'extra_data': '{"xg": 0.15}'
            },
        ]

    def test_calculate_passing_metrics(self, player_events):
        """Test passing metric calculation."""
        calculator = PlayerProfileCalculator(player_events)
        profile = calculator.calculate(
            player_id=101,
            season_id=1,
            team_id=10,
            minutes_played=900  # 10 matches
        )

        # 3 passes in 900 minutes = 0.3 per 90
        assert profile.passes_per_90 == pytest.approx(0.3, rel=0.01)
        # 2 successful out of 3 = 66.67%
        assert profile.pass_accuracy == pytest.approx(66.67, rel=0.1)

    def test_calculate_shooting_metrics(self, player_events):
        """Test shooting metric calculation."""
        calculator = PlayerProfileCalculator(player_events)
        profile = calculator.calculate(
            player_id=101,
            season_id=1,
            team_id=10,
            minutes_played=900
        )

        # 1 shot with 0.15 xG
        assert profile.xg_per_90 == pytest.approx(0.015, rel=0.01)
        assert profile.xg_per_shot == 0.15


class TestSquadSkillAggregation:
    """Test squad-level skill aggregation."""

    def test_aggregate_empty_list(self):
        """Test aggregation with empty list."""
        result = aggregate_squad_skill([], {}, team_id=10, season_id=1)
        assert result.squad_size == 0

    def test_weighted_average(self):
        """Test minutes-weighted averaging."""
        players = [
            PlayerSeasonProfile(
                player_id=101,
                season_id=1,
                team_id=10,
                minutes_played=900,  # 10 matches
                pass_accuracy=90.0
            ),
            PlayerSeasonProfile(
                player_id=102,
                season_id=1,
                team_id=10,
                minutes_played=900,
                pass_accuracy=80.0
            ),
        ]

        result = aggregate_squad_skill(players, {}, team_id=10, season_id=1)

        # Equal minutes = simple average
        assert result.squad_pass_accuracy == 85.0

    def test_weighted_average_unequal_minutes(self):
        """Test weighted average with unequal playing time."""
        players = [
            PlayerSeasonProfile(
                player_id=101,
                season_id=1,
                team_id=10,
                minutes_played=900,  # Plays more
                pass_accuracy=90.0
            ),
            PlayerSeasonProfile(
                player_id=102,
                season_id=1,
                team_id=10,
                minutes_played=300,  # Plays less
                pass_accuracy=60.0
            ),
        ]

        result = aggregate_squad_skill(players, {}, team_id=10, season_id=1)

        # Weighted: (90*900 + 60*300) / 1200 = 82.5
        assert result.squad_pass_accuracy == pytest.approx(82.5, rel=0.01)


class TestFeatureBuilders:
    """Tests for the lightweight feature builder helpers."""

    def test_compute_player_match_features_progressions(self):
        """Player feature frame captures progressions, xG, and regains."""

        shared = {
            'source': 'statsbomb',
            'competition_id': 1,
            'competition_source_id': 'league_1',
            'season_id': 99,
            'season_name': '2020/21',
            'match_id': 1001,
            'team_id': 10,
            'team_source_id': 'team_a',
            'player_source_id': 'player_1',
            'home_score': 2,
            'away_score': 1,
            'is_home': True,
        }

        events = pd.DataFrame([
            {
                **shared,
                'event_type': 'pass',
                'event_subtype': None,
                'minute': 5,
                'second': 0,
                'location_x': 40,
                'location_y': 50,
                'end_location_x': 72,
                'end_location_y': 60,
                'is_successful': True,
                'extra_data': {'pass_length': 30},
            },
            {
                **shared,
                'event_type': 'pass',
                'minute': 10,
                'second': 0,
                'location_x': 20,
                'location_y': 40,
                'end_location_x': 25,
                'end_location_y': 45,
                'is_successful': False,
                'extra_data': {'pass_length': 6},
            },
            {
                **shared,
                'event_type': 'carry',
                'minute': 20,
                'second': 0,
                'location_x': 60,
                'location_y': 40,
                'end_location_x': 80,
                'end_location_y': 42,
                'is_successful': True,
                'extra_data': {'carry_distance': 18},
            },
            {
                **shared,
                'event_type': 'dribble',
                'minute': 25,
                'second': 0,
                'location_x': 70,
                'location_y': 50,
                'is_successful': True,
                'extra_data': {},
            },
            {
                **shared,
                'event_type': 'shot',
                'minute': 30,
                'second': 0,
                'location_x': 82,
                'location_y': 52,
                'is_successful': True,
                'extra_data': {'xg': 0.2, 'type': 'Open Play'},
            },
            {
                **shared,
                'event_type': 'pressure',
                'minute': 40,
                'second': 0,
                'location_x': 70,
                'location_y': 55,
                'extra_data': {},
            },
            {
                **shared,
                'event_type': 'ball_recovery',
                'minute': 40,
                'second': 3,
                'location_x': 72,
                'location_y': 50,
                'extra_data': {},
            },
            {
                **shared,
                'event_type': 'miscontrol',
                'minute': 50,
                'second': 0,
                'location_x': 55,
                'location_y': 48,
                'extra_data': {},
            },
        ])

        result = compute_player_match_features_from_events(events)
        assert len(result) == 1
        row = result.iloc[0]
        assert row['progressive_passes'] == 1
        assert row['progressive_carries'] == 1
        assert row['final_third_entries'] == 2
        assert row['xg'] == pytest.approx(0.2, rel=1e-3)
        assert row['pressure_regains'] == 1

    def test_compute_team_match_features_basic(self):
        """Team feature frame captures PPDA, build-up, and outcome."""

        shared_home = {
            'source': 'statsbomb',
            'competition_id': 1,
            'competition_source_id': 'league_1',
            'season_id': 99,
            'season_name': '2020/21',
            'match_id': 555,
            'home_score': 2,
            'away_score': 1,
        }

        team_a = {
            'team_id': 10,
            'team_source_id': 'team_a',
            'is_home': True,
        }
        team_b = {
            'team_id': 20,
            'team_source_id': 'team_b',
            'is_home': False,
        }

        events = pd.DataFrame([
            {**shared_home, **team_a, 'event_type': 'pass', 'minute': 5, 'second': 0, 'location_x': 20, 'location_y': 40,
             'end_location_x': 55, 'end_location_y': 45, 'player_source_id': 'a1', 'is_successful': True,
             'extra_data': {'pass_length': 35}},
            {**shared_home, **team_a, 'event_type': 'pass', 'minute': 15, 'second': 0, 'location_x': 70, 'location_y': 10,
             'end_location_x': 80, 'end_location_y': 12, 'player_source_id': 'a1', 'is_successful': True,
             'extra_data': {'pass_length': 14, 'cross': True}},
            {**shared_home, **team_a, 'event_type': 'pass', 'minute': 18, 'second': 0, 'location_x': 60, 'location_y': 50,
             'end_location_x': 75, 'end_location_y': 48, 'player_source_id': 'a2', 'is_successful': True,
             'extra_data': {'pass_length': 18, 'through_ball': True}},
            {**shared_home, **team_a, 'event_type': 'carry', 'minute': 19, 'second': 0, 'location_x': 45, 'location_y': 45,
             'end_location_x': 70, 'end_location_y': 46, 'player_source_id': 'a3', 'is_successful': True,
             'extra_data': {'carry_distance': 25}},
            {**shared_home, **team_a, 'event_type': 'pressure', 'minute': 20, 'second': 0, 'location_x': 70, 'location_y': 50,
             'player_source_id': 'a4', 'is_successful': False, 'extra_data': {}},
            {**shared_home, **team_a, 'event_type': 'ball_recovery', 'minute': 20, 'second': 3, 'location_x': 72, 'location_y': 52,
             'player_source_id': 'a4', 'is_successful': True, 'extra_data': {}},
            {**shared_home, **team_a, 'event_type': 'tackle', 'minute': 30, 'second': 0, 'location_x': 55, 'location_y': 45,
             'player_source_id': 'a5', 'is_successful': True, 'extra_data': {}},
            {**shared_home, **team_a, 'event_type': 'shot', 'minute': 40, 'second': 0, 'location_x': 85, 'location_y': 48,
             'player_source_id': 'a6', 'is_successful': True, 'extra_data': {'xg': 0.3, 'type': 'Open Play'}},
            {**shared_home, **team_a, 'event_type': 'ball_receipt', 'minute': 50, 'second': 0, 'location_x': 60, 'location_y': 50,
             'player_source_id': 'a7', 'is_successful': True, 'extra_data': {}},
            {**shared_home, **team_b, 'event_type': 'pass', 'minute': 7, 'second': 0, 'location_x': 40, 'location_y': 55,
             'end_location_x': 45, 'end_location_y': 50, 'player_source_id': 'b1', 'is_successful': True,
             'extra_data': {'pass_length': 8}},
            {**shared_home, **team_b, 'event_type': 'pass', 'minute': 12, 'second': 0, 'location_x': 70, 'location_y': 60,
             'end_location_x': 75, 'end_location_y': 62, 'player_source_id': 'b1', 'is_successful': True,
             'extra_data': {'pass_length': 7}},
            {**shared_home, **team_b, 'event_type': 'ball_recovery', 'minute': 13, 'second': 0, 'location_x': 55, 'location_y': 40,
             'player_source_id': 'b2', 'is_successful': True, 'extra_data': {}},
        ])

        result = compute_team_match_features_from_events(events)
        assert set(result['team_source_id']) == {'team_a', 'team_b'}

        team_row = result[result['team_source_id'] == 'team_a'].iloc[0]
        assert team_row['match_outcome'] == 'W'
        assert team_row['ppda'] is not None
        assert team_row['build_up_pass_share'] > 0
        assert team_row['cross_rate'] > 0
