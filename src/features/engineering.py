"""
Feature Engineering Layer for Football Evolution Analysis

This module creates tactical, skill, and evolution metrics from event data.

Feature Tables:
- f_team_match_style: Per-match team style features
- f_team_season_style: Season-aggregated team evolution metrics
- f_player_season_profile: Player skill profiles
- f_squad_season_skill: Squad-level skill aggregations
- f_team_season_tactics: Tactical structure features
"""

import math
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class PitchZone:
    """Define pitch zones for analysis."""
    name: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float

    def contains(self, x: float, y: float) -> bool:
        """Check if coordinates fall within this zone."""
        return self.x_min <= x <= self.x_max and self.y_min <= y <= self.y_max


# Standard pitch zones (0-100 normalized coordinates)
PITCH_ZONES = {
    'defensive_third': PitchZone('defensive_third', 0, 33.33, 0, 100),
    'middle_third': PitchZone('middle_third', 33.33, 66.67, 0, 100),
    'attacking_third': PitchZone('attacking_third', 66.67, 100, 0, 100),
    'left_flank': PitchZone('left_flank', 0, 100, 0, 30),
    'central': PitchZone('central', 0, 100, 30, 70),
    'right_flank': PitchZone('right_flank', 0, 100, 70, 100),
    'box': PitchZone('box', 83.33, 100, 21.1, 78.9),  # Penalty area
    'deep_def': PitchZone('deep_def', 0, 16.67, 0, 100),  # Own box area
}


class PassType(Enum):
    """Pass classification types."""
    SHORT = 'short'
    MEDIUM = 'medium'
    LONG = 'long'
    PROGRESSIVE = 'progressive'
    THROUGH_BALL = 'through_ball'
    CROSS = 'cross'
    SWITCH = 'switch'


# ============================================================================
# TEAM MATCH STYLE FEATURES (f_team_match_style)
# ============================================================================

@dataclass
class TeamMatchStyle:
    """
    Team-level features for a single match.

    Schema: f_team_match_style
    """
    # Identifiers
    match_id: int
    team_id: int
    is_home: bool

    # Tempo & Possession
    possession_pct: float = 0.0
    passes_total: int = 0
    passes_successful: int = 0
    pass_accuracy: float = 0.0
    passes_per_minute: float = 0.0
    avg_pass_length: float = 0.0
    direct_speed_index: float = 0.0  # How quickly ball moves up the pitch

    # Pressing Profile
    ppda: float = 0.0  # Passes per defensive action (lower = more pressing)
    ppda_attacking_third: float = 0.0
    high_press_pct: float = 0.0  # % of pressures in attacking third
    counterpressing_recoveries: int = 0  # Recoveries within 5 sec of loss
    pressures_total: int = 0
    pressures_successful: int = 0

    # Buildup Structure
    buildup_passes: int = 0  # Passes in own half
    gk_short_pass_pct: float = 0.0  # GK passes that are short
    progressive_passes: int = 0
    progressive_carries: int = 0
    deep_completions: int = 0  # Passes into final third

    # Chance Creation
    shots: int = 0
    shots_on_target: int = 0
    xg_total: float = 0.0
    xg_per_shot: float = 0.0
    big_chances: int = 0  # xG > 0.3
    crosses: int = 0
    through_balls: int = 0
    set_piece_xg: float = 0.0

    # Shot Profile
    box_shots_pct: float = 0.0  # % of shots from box
    header_shots_pct: float = 0.0
    counter_attack_shots: int = 0

    # Width & Shape
    width_index: float = 0.0  # Avg y-distance from center
    left_side_pct: float = 0.0
    right_side_pct: float = 0.0
    central_pct: float = 0.0

    # Defensive Metrics
    tackles: int = 0
    interceptions: int = 0
    clearances: int = 0
    blocks: int = 0
    ball_recoveries: int = 0
    defensive_line_height: float = 0.0  # Avg x-position of defensive actions

    # Duels & Intensity
    aerial_duels_won: int = 0
    aerial_duels_lost: int = 0
    ground_duels_won: int = 0
    ground_duels_lost: int = 0
    fouls_committed: int = 0
    fouls_won: int = 0

    # Transition Metrics
    transition_attacks: int = 0  # Attacks starting within 5 sec of recovery
    counter_attacks: int = 0
    avg_attack_duration: float = 0.0


class TeamMatchStyleCalculator:
    """
    Calculate team match style features from event data.

    Algorithm Overview:
    1. Filter events by team and match
    2. Aggregate by event type
    3. Calculate derived metrics
    4. Normalize where appropriate
    """

    def __init__(self, events: List[Dict[str, Any]], match_duration_minutes: int = 90):
        self.events = events
        self.match_duration = match_duration_minutes

    def calculate(self, match_id: int, team_id: int, is_home: bool) -> TeamMatchStyle:
        """Calculate all team match style features."""
        team_events = [e for e in self.events if e.get('team_id') == team_id]
        opponent_events = [e for e in self.events if e.get('team_id') != team_id]

        style = TeamMatchStyle(
            match_id=match_id,
            team_id=team_id,
            is_home=is_home
        )

        # Calculate each feature category
        self._calculate_possession(style, team_events)
        self._calculate_passing(style, team_events)
        self._calculate_pressing(style, team_events, opponent_events)
        self._calculate_buildup(style, team_events)
        self._calculate_chances(style, team_events)
        self._calculate_shape(style, team_events)
        self._calculate_defense(style, team_events)
        self._calculate_duels(style, team_events)
        self._calculate_transitions(style, team_events)

        return style

    def _calculate_possession(self, style: TeamMatchStyle, events: List[Dict]):
        """
        Calculate possession percentage.

        Method: Count passes relative to total match passes.
        """
        passes = [e for e in events if e.get('event_type') == 'pass']
        all_passes = [e for e in self.events if e.get('event_type') == 'pass']

        style.passes_total = len(passes)
        if all_passes:
            style.possession_pct = len(passes) / len(all_passes) * 100
        style.passes_per_minute = len(passes) / self.match_duration

    def _calculate_passing(self, style: TeamMatchStyle, events: List[Dict]):
        """
        Calculate passing metrics.

        Metrics:
        - Pass accuracy
        - Average pass length
        - Direct speed index (progression per pass)
        """
        passes = [e for e in events if e.get('event_type') == 'pass']

        if not passes:
            return

        successful = [p for p in passes if p.get('is_successful')]
        style.passes_successful = len(successful)
        style.pass_accuracy = len(successful) / len(passes) * 100

        # Calculate average pass length
        lengths = []
        progressions = []
        for p in passes:
            extra = json.loads(p.get('extra_data', '{}')) if isinstance(p.get('extra_data'), str) else p.get('extra_data', {})
            if extra.get('pass_length'):
                lengths.append(extra['pass_length'])

            # Progression (forward movement)
            if p.get('end_location_x') and p.get('location_x'):
                progression = p['end_location_x'] - p['location_x']
                progressions.append(progression)

        style.avg_pass_length = sum(lengths) / len(lengths) if lengths else 0
        style.direct_speed_index = sum(progressions) / len(progressions) if progressions else 0

    def _calculate_pressing(self, style: TeamMatchStyle, events: List[Dict],
                            opponent_events: List[Dict]):
        """
        Calculate pressing intensity metrics.

        PPDA Formula:
        PPDA = opponent_passes_in_own_half / (tackles + interceptions + fouls)_in_opponent_half

        Lower PPDA = Higher pressing intensity
        """
        # Opponent passes in their own half (our attacking areas)
        opponent_passes = [
            e for e in opponent_events
            if e.get('event_type') == 'pass'
            and e.get('location_x', 0) < 50  # Their defensive half
        ]

        # Our defensive actions in opponent half
        def_actions = [
            e for e in events
            if e.get('event_type') in ('tackle', 'interception', 'foul')
            and e.get('location_x', 0) > 50  # Their half
        ]

        if def_actions:
            style.ppda = len(opponent_passes) / len(def_actions)
        else:
            style.ppda = 100  # Max value if no pressing

        # Pressures
        pressures = [e for e in events if e.get('event_type') == 'pressure']
        style.pressures_total = len(pressures)

        attacking_third_pressures = [
            p for p in pressures
            if PITCH_ZONES['attacking_third'].contains(
                p.get('location_x', 0), p.get('location_y', 50)
            )
        ]
        style.high_press_pct = (
            len(attacking_third_pressures) / len(pressures) * 100
            if pressures else 0
        )

        # Counter-pressing recoveries (within 5 seconds of losing ball)
        # This requires sequence analysis - simplified here
        style.counterpressing_recoveries = len([
            e for e in events
            if e.get('event_type') == 'ball_recovery'
            and e.get('location_x', 0) > 50
        ])

    def _calculate_buildup(self, style: TeamMatchStyle, events: List[Dict]):
        """
        Calculate buildup play metrics.

        Progressive Pass Definition:
        - Moves ball at least 10 yards toward goal
        - Or moves ball into final third
        """
        passes = [e for e in events if e.get('event_type') == 'pass']
        carries = [e for e in events if e.get('event_type') == 'carry']

        # Buildup passes (in own half)
        style.buildup_passes = len([
            p for p in passes
            if p.get('location_x', 100) < 50
        ])

        # GK short passes
        gk_passes = [
            p for p in passes
            if p.get('location_x', 100) < 10  # Near goal line
        ]
        gk_short = [
            p for p in gk_passes
            if self._get_pass_length(p) < 30
        ]
        style.gk_short_pass_pct = (
            len(gk_short) / len(gk_passes) * 100
            if gk_passes else 0
        )

        # Progressive passes
        style.progressive_passes = len([
            p for p in passes
            if self._is_progressive_pass(p)
        ])

        # Progressive carries
        style.progressive_carries = len([
            c for c in carries
            if self._is_progressive_carry(c)
        ])

        # Deep completions (passes into final third)
        style.deep_completions = len([
            p for p in passes
            if p.get('is_successful')
            and p.get('location_x', 0) < 66.67
            and p.get('end_location_x', 0) >= 66.67
        ])

    def _is_progressive_pass(self, pass_event: Dict) -> bool:
        """Check if pass is progressive (moves ball significantly toward goal)."""
        start_x = pass_event.get('location_x', 0)
        end_x = pass_event.get('end_location_x', 0)

        if not (start_x and end_x):
            return False

        # Progressive if moves 10+ yards toward goal
        # Or enters final third from outside
        progression = end_x - start_x
        enters_final_third = start_x < 66.67 and end_x >= 66.67

        return progression >= 10 or enters_final_third

    def _is_progressive_carry(self, carry_event: Dict) -> bool:
        """Check if carry is progressive."""
        start_x = carry_event.get('location_x', 0)
        end_x = carry_event.get('end_location_x', 0)

        if not (start_x and end_x):
            return False

        progression = end_x - start_x
        return progression >= 10

    def _get_pass_length(self, pass_event: Dict) -> float:
        """Calculate pass length from coordinates."""
        start_x = pass_event.get('location_x', 0)
        start_y = pass_event.get('location_y', 0)
        end_x = pass_event.get('end_location_x', 0)
        end_y = pass_event.get('end_location_y', 0)

        return math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)

    def _calculate_chances(self, style: TeamMatchStyle, events: List[Dict]):
        """
        Calculate chance creation and shot metrics.

        xG per shot indicates shot quality.
        Big chances are shots with xG > 0.3.
        """
        shots = [e for e in events if e.get('event_type') == 'shot']
        style.shots = len(shots)

        on_target = [
            s for s in shots
            if s.get('outcome') in ('Goal', 'Saved', 'Saved to Post')
        ]
        style.shots_on_target = len(on_target)

        # xG aggregation
        xg_total = 0
        big_chances = 0
        box_shots = 0
        header_shots = 0

        for shot in shots:
            extra = json.loads(shot.get('extra_data', '{}')) if isinstance(shot.get('extra_data'), str) else shot.get('extra_data', {})
            xg = extra.get('xg', 0)
            xg_total += xg

            if xg > 0.3:
                big_chances += 1

            if PITCH_ZONES['box'].contains(
                shot.get('location_x', 0), shot.get('location_y', 50)
            ):
                box_shots += 1

            if extra.get('body_part') == 'Head':
                header_shots += 1

        style.xg_total = xg_total
        style.xg_per_shot = xg_total / len(shots) if shots else 0
        style.big_chances = big_chances
        style.box_shots_pct = box_shots / len(shots) * 100 if shots else 0
        style.header_shots_pct = header_shots / len(shots) * 100 if shots else 0

        # Crosses and through balls
        passes = [e for e in events if e.get('event_type') == 'pass']
        for p in passes:
            extra = json.loads(p.get('extra_data', '{}')) if isinstance(p.get('extra_data'), str) else p.get('extra_data', {})
            if extra.get('cross'):
                style.crosses += 1
            if extra.get('through_ball'):
                style.through_balls += 1

    def _calculate_shape(self, style: TeamMatchStyle, events: List[Dict]):
        """
        Calculate team shape and width metrics.

        Width index measures how spread out the team plays.
        """
        passes = [e for e in events if e.get('event_type') == 'pass' and e.get('location_y')]

        if not passes:
            return

        y_positions = [p['location_y'] for p in passes]

        # Width index (average distance from center)
        center_y = 50
        style.width_index = sum(abs(y - center_y) for y in y_positions) / len(y_positions)

        # Zone distribution
        left = len([y for y in y_positions if y < 30])
        central = len([y for y in y_positions if 30 <= y <= 70])
        right = len([y for y in y_positions if y > 70])
        total = len(y_positions)

        style.left_side_pct = left / total * 100
        style.central_pct = central / total * 100
        style.right_side_pct = right / total * 100

    def _calculate_defense(self, style: TeamMatchStyle, events: List[Dict]):
        """Calculate defensive metrics."""
        style.tackles = len([e for e in events if e.get('event_type') == 'tackle'])
        style.interceptions = len([e for e in events if e.get('event_type') == 'interception'])
        style.clearances = len([e for e in events if e.get('event_type') == 'clearance'])
        style.blocks = len([e for e in events if e.get('event_type') == 'block'])
        style.ball_recoveries = len([e for e in events if e.get('event_type') == 'ball_recovery'])

        # Defensive line height
        def_events = [
            e for e in events
            if e.get('event_type') in ('tackle', 'interception', 'clearance', 'block')
            and e.get('location_x')
        ]
        if def_events:
            style.defensive_line_height = sum(e['location_x'] for e in def_events) / len(def_events)

    def _calculate_duels(self, style: TeamMatchStyle, events: List[Dict]):
        """Calculate duel statistics."""
        duels = [e for e in events if e.get('event_type') == 'duel']

        for duel in duels:
            subtype = duel.get('event_subtype', '').lower()
            won = duel.get('is_successful', False)

            if 'aerial' in subtype:
                if won:
                    style.aerial_duels_won += 1
                else:
                    style.aerial_duels_lost += 1
            else:
                if won:
                    style.ground_duels_won += 1
                else:
                    style.ground_duels_lost += 1

        style.fouls_committed = len([e for e in events if e.get('event_type') == 'foul'])
        style.fouls_won = len([e for e in events if e.get('event_type') == 'foul_won'])

    def _calculate_transitions(self, style: TeamMatchStyle, events: List[Dict]):
        """
        Calculate transition and counter-attack metrics.

        Transition attack: Attack within 5 seconds of ball recovery.
        Counter-attack: Fast transition leading to shot.
        """
        # This requires possession sequence analysis
        # Simplified implementation here

        recoveries = [e for e in events if e.get('event_type') == 'ball_recovery']
        shots = [e for e in events if e.get('event_type') == 'shot']

        # Count shots that came from quick transitions
        # (within 10 events of a recovery in opponent half)
        style.transition_attacks = len([
            r for r in recoveries
            if r.get('location_x', 0) > 50
        ])


# ============================================================================
# TEAM SEASON STYLE FEATURES (f_team_season_style)
# ============================================================================

@dataclass
class TeamSeasonStyle:
    """
    Season-aggregated team style features for evolution analysis.

    Schema: f_team_season_style
    """
    team_id: int
    season_id: int

    # Core evolution metrics (targets for analysis)
    ppda_avg: float = 0.0
    ppda_trend: float = 0.0  # Change from start to end of season
    possession_avg: float = 0.0
    xg_per_shot_avg: float = 0.0
    xg_total_avg: float = 0.0
    xg_against_avg: float = 0.0
    goals_per_match: float = 0.0

    # Style consistency
    style_variance: float = 0.0  # How consistent is the team's style

    # Pressing profile (season avg)
    high_press_pct_avg: float = 0.0
    counterpressing_rate: float = 0.0

    # Buildup profile
    gk_short_pct_avg: float = 0.0
    progressive_passes_avg: float = 0.0
    deep_completions_avg: float = 0.0

    # Shape profile
    width_index_avg: float = 0.0
    defensive_line_avg: float = 0.0

    # Chance profile
    big_chances_avg: float = 0.0
    box_shots_pct_avg: float = 0.0
    cross_rate: float = 0.0

    # Transition profile
    transition_attack_rate: float = 0.0
    counter_attack_rate: float = 0.0

    # Matches and context
    matches_played: int = 0
    manager_changes: int = 0
    era: str = ""


def aggregate_season_style(match_styles: List[TeamMatchStyle],
                           season_id: int) -> TeamSeasonStyle:
    """
    Aggregate match-level styles to season-level.

    SQL Equivalent:
    ```sql
    INSERT INTO f_team_season_style
    SELECT
        team_id,
        season_id,
        AVG(ppda) as ppda_avg,
        AVG(possession_pct) as possession_avg,
        AVG(xg_per_shot) as xg_per_shot_avg,
        ...
    FROM f_team_match_style
    GROUP BY team_id, season_id
    ```
    """
    if not match_styles:
        return TeamSeasonStyle(team_id=0, season_id=season_id)

    team_id = match_styles[0].team_id
    n = len(match_styles)

    return TeamSeasonStyle(
        team_id=team_id,
        season_id=season_id,
        matches_played=n,
        ppda_avg=sum(m.ppda for m in match_styles) / n,
        possession_avg=sum(m.possession_pct for m in match_styles) / n,
        xg_per_shot_avg=sum(m.xg_per_shot for m in match_styles) / n,
        xg_total_avg=sum(m.xg_total for m in match_styles) / n,
        high_press_pct_avg=sum(m.high_press_pct for m in match_styles) / n,
        gk_short_pct_avg=sum(m.gk_short_pass_pct for m in match_styles) / n,
        progressive_passes_avg=sum(m.progressive_passes for m in match_styles) / n,
        deep_completions_avg=sum(m.deep_completions for m in match_styles) / n,
        width_index_avg=sum(m.width_index for m in match_styles) / n,
        defensive_line_avg=sum(m.defensive_line_height for m in match_styles) / n,
        big_chances_avg=sum(m.big_chances for m in match_styles) / n,
        box_shots_pct_avg=sum(m.box_shots_pct for m in match_styles) / n,
        cross_rate=sum(m.crosses for m in match_styles) / n,
        transition_attack_rate=sum(m.transition_attacks for m in match_styles) / n,
    )


# ============================================================================
# PLAYER SEASON PROFILE (f_player_season_profile)
# ============================================================================

@dataclass
class PlayerSeasonProfile:
    """
    Individual player skill profile for a season.

    Schema: f_player_season_profile
    """
    player_id: int
    season_id: int
    team_id: int

    # Metadata
    position: str = ""
    minutes_played: int = 0
    matches_played: int = 0

    # Technical skills (per 90)
    passes_per_90: float = 0.0
    pass_accuracy: float = 0.0
    progressive_passes_per_90: float = 0.0
    progressive_carries_per_90: float = 0.0
    through_balls_per_90: float = 0.0
    key_passes_per_90: float = 0.0
    crosses_per_90: float = 0.0
    cross_accuracy: float = 0.0
    long_pass_accuracy: float = 0.0

    # Dribbling
    dribbles_per_90: float = 0.0
    dribble_success_rate: float = 0.0
    progressive_distance_per_90: float = 0.0
    touches_in_box_per_90: float = 0.0

    # Shooting
    shots_per_90: float = 0.0
    xg_per_90: float = 0.0
    xg_per_shot: float = 0.0
    shot_accuracy: float = 0.0
    goals_per_90: float = 0.0
    npxg_per_90: float = 0.0  # Non-penalty xG

    # Chance creation
    xa_per_90: float = 0.0  # xAssist
    shot_creating_actions_per_90: float = 0.0
    goal_creating_actions_per_90: float = 0.0

    # Defensive skills (per 90)
    tackles_per_90: float = 0.0
    tackle_success_rate: float = 0.0
    interceptions_per_90: float = 0.0
    blocks_per_90: float = 0.0
    clearances_per_90: float = 0.0
    ball_recoveries_per_90: float = 0.0

    # Pressure & intensity
    pressures_per_90: float = 0.0
    pressure_success_rate: float = 0.0
    counterpresses_per_90: float = 0.0

    # Aerial
    aerial_duels_per_90: float = 0.0
    aerial_win_rate: float = 0.0

    # Ball retention
    dispossessed_per_90: float = 0.0
    miscontrols_per_90: float = 0.0
    fouls_won_per_90: float = 0.0

    # Positioning (average positions)
    avg_x_position: float = 0.0
    avg_y_position: float = 0.0
    position_flexibility: float = 0.0  # Variance in positions


class PlayerProfileCalculator:
    """Calculate player season profiles from event data."""

    def __init__(self, events: List[Dict[str, Any]]):
        self.events = events

    def calculate(self, player_id: int, season_id: int, team_id: int,
                  minutes_played: int) -> PlayerSeasonProfile:
        """Calculate player profile for a season."""
        player_events = [e for e in self.events if e.get('player_id') == player_id]

        profile = PlayerSeasonProfile(
            player_id=player_id,
            season_id=season_id,
            team_id=team_id,
            minutes_played=minutes_played
        )

        # Per 90 multiplier
        per_90 = 90 / minutes_played if minutes_played > 0 else 0

        # Calculate each category
        self._calculate_passing(profile, player_events, per_90)
        self._calculate_dribbling(profile, player_events, per_90)
        self._calculate_shooting(profile, player_events, per_90)
        self._calculate_defensive(profile, player_events, per_90)
        self._calculate_pressure(profile, player_events, per_90)
        self._calculate_positioning(profile, player_events)

        return profile

    def _calculate_passing(self, profile: PlayerSeasonProfile,
                           events: List[Dict], per_90: float):
        """Calculate passing metrics."""
        passes = [e for e in events if e.get('event_type') == 'pass']
        successful = [p for p in passes if p.get('is_successful')]

        profile.passes_per_90 = len(passes) * per_90
        profile.pass_accuracy = len(successful) / len(passes) * 100 if passes else 0

        # Progressive passes
        progressive = [p for p in passes if self._is_progressive_pass(p)]
        profile.progressive_passes_per_90 = len(progressive) * per_90

        # Key passes (leading to shots) - requires sequence analysis
        # Crosses
        crosses = [p for p in passes if self._is_cross(p)]
        crosses_successful = [c for c in crosses if c.get('is_successful')]
        profile.crosses_per_90 = len(crosses) * per_90
        profile.cross_accuracy = len(crosses_successful) / len(crosses) * 100 if crosses else 0

    def _is_progressive_pass(self, pass_event: Dict) -> bool:
        """Check if pass is progressive."""
        start_x = pass_event.get('location_x', 0)
        end_x = pass_event.get('end_location_x', 0)
        return (end_x - start_x) >= 10 if start_x and end_x else False

    def _is_cross(self, pass_event: Dict) -> bool:
        """Check if pass is a cross."""
        extra = json.loads(pass_event.get('extra_data', '{}')) if isinstance(pass_event.get('extra_data'), str) else pass_event.get('extra_data', {})
        return extra.get('cross', False)

    def _calculate_dribbling(self, profile: PlayerSeasonProfile,
                             events: List[Dict], per_90: float):
        """Calculate dribbling metrics."""
        dribbles = [e for e in events if e.get('event_type') == 'dribble']
        successful = [d for d in dribbles if d.get('is_successful')]

        profile.dribbles_per_90 = len(dribbles) * per_90
        profile.dribble_success_rate = len(successful) / len(dribbles) * 100 if dribbles else 0

        # Progressive carries
        carries = [e for e in events if e.get('event_type') == 'carry']
        progressive_dist = 0
        for carry in carries:
            start_x = carry.get('location_x', 0)
            end_x = carry.get('end_location_x', 0)
            if end_x > start_x:
                progressive_dist += (end_x - start_x)

        profile.progressive_distance_per_90 = progressive_dist * per_90

    def _calculate_shooting(self, profile: PlayerSeasonProfile,
                            events: List[Dict], per_90: float):
        """Calculate shooting metrics."""
        shots = [e for e in events if e.get('event_type') == 'shot']

        profile.shots_per_90 = len(shots) * per_90

        xg_total = 0
        goals = 0
        on_target = 0

        for shot in shots:
            extra = json.loads(shot.get('extra_data', '{}')) if isinstance(shot.get('extra_data'), str) else shot.get('extra_data', {})
            xg_total += extra.get('xg', 0)
            if shot.get('outcome') == 'Goal':
                goals += 1
            if shot.get('outcome') in ('Goal', 'Saved', 'Saved to Post'):
                on_target += 1

        profile.xg_per_90 = xg_total * per_90
        profile.xg_per_shot = xg_total / len(shots) if shots else 0
        profile.goals_per_90 = goals * per_90
        profile.shot_accuracy = on_target / len(shots) * 100 if shots else 0

    def _calculate_defensive(self, profile: PlayerSeasonProfile,
                             events: List[Dict], per_90: float):
        """Calculate defensive metrics."""
        tackles = [e for e in events if e.get('event_type') == 'tackle']
        tackles_won = [t for t in tackles if t.get('is_successful')]

        profile.tackles_per_90 = len(tackles) * per_90
        profile.tackle_success_rate = len(tackles_won) / len(tackles) * 100 if tackles else 0

        profile.interceptions_per_90 = len([e for e in events if e.get('event_type') == 'interception']) * per_90
        profile.blocks_per_90 = len([e for e in events if e.get('event_type') == 'block']) * per_90
        profile.clearances_per_90 = len([e for e in events if e.get('event_type') == 'clearance']) * per_90
        profile.ball_recoveries_per_90 = len([e for e in events if e.get('event_type') == 'ball_recovery']) * per_90

    def _calculate_pressure(self, profile: PlayerSeasonProfile,
                            events: List[Dict], per_90: float):
        """Calculate pressing and intensity metrics."""
        pressures = [e for e in events if e.get('event_type') == 'pressure']
        successful = [p for p in pressures if p.get('is_successful')]

        profile.pressures_per_90 = len(pressures) * per_90
        profile.pressure_success_rate = len(successful) / len(pressures) * 100 if pressures else 0

        # Aerial duels
        duels = [e for e in events if e.get('event_type') == 'duel']
        aerial = [d for d in duels if 'aerial' in d.get('event_subtype', '').lower()]
        aerial_won = [d for d in aerial if d.get('is_successful')]

        profile.aerial_duels_per_90 = len(aerial) * per_90
        profile.aerial_win_rate = len(aerial_won) / len(aerial) * 100 if aerial else 0

    def _calculate_positioning(self, profile: PlayerSeasonProfile, events: List[Dict]):
        """Calculate average positions."""
        events_with_location = [
            e for e in events
            if e.get('location_x') is not None and e.get('location_y') is not None
        ]

        if events_with_location:
            profile.avg_x_position = sum(e['location_x'] for e in events_with_location) / len(events_with_location)
            profile.avg_y_position = sum(e['location_y'] for e in events_with_location) / len(events_with_location)


# ============================================================================
# SQUAD SEASON SKILL (f_squad_season_skill)
# ============================================================================

@dataclass
class SquadSeasonSkill:
    """
    Squad-level skill aggregation for a season.

    Aggregates individual player profiles to team-level skill metrics.

    Schema: f_squad_season_skill
    """
    team_id: int
    season_id: int

    # Squad composition
    squad_size: int = 0
    avg_age: float = 0.0
    minutes_weighted_avg_age: float = 0.0

    # Technical aggregate (weighted by minutes)
    squad_pass_accuracy: float = 0.0
    squad_dribble_success: float = 0.0
    squad_progressive_passes: float = 0.0

    # Attacking aggregate
    squad_xg_per_90: float = 0.0
    squad_xa_per_90: float = 0.0
    squad_shot_quality: float = 0.0

    # Defensive aggregate
    squad_tackle_success: float = 0.0
    squad_aerial_win_rate: float = 0.0
    squad_pressure_success: float = 0.0

    # Skill concentration
    xg_concentration: float = 0.0  # How concentrated is goal threat (Herfindahl index)
    creativity_concentration: float = 0.0

    # Squad depth
    starting_xi_minutes_share: float = 0.0
    rotation_index: float = 0.0


def aggregate_squad_skill(player_profiles: List[PlayerSeasonProfile],
                          player_ages: Dict[int, int],
                          team_id: int, season_id: int) -> SquadSeasonSkill:
    """
    Aggregate player profiles to squad-level skill.

    Uses minutes-weighted averages for most metrics.
    """
    if not player_profiles:
        return SquadSeasonSkill(team_id=team_id, season_id=season_id)

    total_minutes = sum(p.minutes_played for p in player_profiles)

    squad = SquadSeasonSkill(
        team_id=team_id,
        season_id=season_id,
        squad_size=len(player_profiles)
    )

    if total_minutes == 0:
        return squad

    # Minutes-weighted aggregations
    def weighted_avg(field: str) -> float:
        return sum(
            getattr(p, field) * p.minutes_played / total_minutes
            for p in player_profiles
        )

    squad.squad_pass_accuracy = weighted_avg('pass_accuracy')
    squad.squad_dribble_success = weighted_avg('dribble_success_rate')
    squad.squad_progressive_passes = weighted_avg('progressive_passes_per_90')
    squad.squad_xg_per_90 = weighted_avg('xg_per_90')
    squad.squad_xa_per_90 = weighted_avg('xa_per_90')
    squad.squad_shot_quality = weighted_avg('xg_per_shot')
    squad.squad_tackle_success = weighted_avg('tackle_success_rate')
    squad.squad_aerial_win_rate = weighted_avg('aerial_win_rate')
    squad.squad_pressure_success = weighted_avg('pressure_success_rate')

    # Average age
    if player_ages:
        ages = [player_ages.get(p.player_id, 0) for p in player_profiles if player_ages.get(p.player_id)]
        squad.avg_age = sum(ages) / len(ages) if ages else 0

        # Minutes-weighted age
        weighted_ages = sum(
            player_ages.get(p.player_id, 0) * p.minutes_played
            for p in player_profiles
            if player_ages.get(p.player_id)
        )
        squad.minutes_weighted_avg_age = weighted_ages / total_minutes

    # xG concentration (Herfindahl index)
    total_xg = sum(p.xg_per_90 * p.minutes_played / 90 for p in player_profiles)
    if total_xg > 0:
        xg_shares = [
            (p.xg_per_90 * p.minutes_played / 90 / total_xg) ** 2
            for p in player_profiles
        ]
        squad.xg_concentration = sum(xg_shares)

    return squad


# ============================================================================
# TEAM SEASON TACTICS (f_team_season_tactics)
# ============================================================================

@dataclass
class TeamSeasonTactics:
    """
    Tactical structure features for a team season.

    Schema: f_team_season_tactics
    """
    team_id: int
    season_id: int

    # Formation analysis
    primary_formation: str = ""
    formation_flexibility: float = 0.0  # How often formation changes
    formations_used: int = 0

    # Network metrics
    centralization_index: float = 0.0  # How much play flows through key players
    clustering_coefficient: float = 0.0  # Team compactness in passing
    avg_pass_chain_length: float = 0.0

    # Line heights
    avg_defensive_line: float = 0.0
    avg_midfield_line: float = 0.0
    avg_attacking_line: float = 0.0
    vertical_compactness: float = 0.0  # Distance between def and att lines

    # Pressing zones
    press_zone_defensive: float = 0.0  # % of pressures in own third
    press_zone_middle: float = 0.0
    press_zone_attacking: float = 0.0
    press_intensity_variation: float = 0.0  # How pressing changes game-to-game

    # Buildup patterns
    short_buildup_pct: float = 0.0
    long_buildup_pct: float = 0.0
    wing_buildup_pct: float = 0.0
    central_buildup_pct: float = 0.0

    # Set piece reliance
    set_piece_goals_pct: float = 0.0
    set_piece_xg_pct: float = 0.0

    # Transition profile
    avg_transition_time: float = 0.0  # Seconds from recovery to shot
    direct_counter_rate: float = 0.0
    possession_regain_rate: float = 0.0


class TacticalAnalyzer:
    """
    Analyze tactical patterns from event data.

    Calculates network centralization, line heights, and pressing zones.
    """

    def __init__(self, events: List[Dict[str, Any]], lineups: List[Dict[str, Any]]):
        self.events = events
        self.lineups = lineups

    def analyze_network_centralization(self, team_id: int) -> float:
        """
        Calculate network centralization index.

        Formula: C = sum(c_max - c_i) / max_possible_sum
        Where c_i is the degree centrality of player i.

        High centralization = play flows through few key players.
        """
        team_passes = [
            e for e in self.events
            if e.get('event_type') == 'pass'
            and e.get('team_id') == team_id
            and e.get('is_successful')
        ]

        # Build pass count per player
        pass_counts: Dict[int, int] = {}
        for p in team_passes:
            player_id = p.get('player_id')
            if player_id:
                pass_counts[player_id] = pass_counts.get(player_id, 0) + 1

        if len(pass_counts) < 2:
            return 0.0

        # Calculate centralization
        max_passes = max(pass_counts.values())
        sum_differences = sum(max_passes - count for count in pass_counts.values())
        max_possible = (len(pass_counts) - 1) * max_passes

        return sum_differences / max_possible if max_possible > 0 else 0

    def analyze_line_heights(self, team_id: int) -> Dict[str, float]:
        """
        Calculate average line heights for defensive, midfield, and attacking lines.

        Uses average positions from event locations.
        """
        team_events = [
            e for e in self.events
            if e.get('team_id') == team_id and e.get('location_x')
        ]

        # Group by player position from lineups
        position_x_values: Dict[str, List[float]] = {
            'defender': [],
            'midfielder': [],
            'forward': []
        }

        player_positions = {
            l['player_id']: l.get('position', '')
            for l in self.lineups
            if l.get('team_id') == team_id
        }

        for event in team_events:
            player_id = event.get('player_id')
            position = player_positions.get(player_id, '').lower()
            x = event.get('location_x')

            if 'back' in position or 'defender' in position:
                position_x_values['defender'].append(x)
            elif 'mid' in position:
                position_x_values['midfielder'].append(x)
            elif 'forward' in position or 'striker' in position or 'wing' in position:
                position_x_values['forward'].append(x)

        return {
            'defensive_line': sum(position_x_values['defender']) / len(position_x_values['defender']) if position_x_values['defender'] else 0,
            'midfield_line': sum(position_x_values['midfielder']) / len(position_x_values['midfielder']) if position_x_values['midfielder'] else 0,
            'attacking_line': sum(position_x_values['forward']) / len(position_x_values['forward']) if position_x_values['forward'] else 0,
        }

    def analyze_pressing_zones(self, team_id: int) -> Dict[str, float]:
        """
        Calculate pressing zone distribution.

        Returns percentage of pressures in each third.
        """
        pressures = [
            e for e in self.events
            if e.get('event_type') == 'pressure'
            and e.get('team_id') == team_id
            and e.get('location_x')
        ]

        if not pressures:
            return {'defensive': 0, 'middle': 0, 'attacking': 0}

        defensive = len([p for p in pressures if p['location_x'] < 33.33])
        middle = len([p for p in pressures if 33.33 <= p['location_x'] < 66.67])
        attacking = len([p for p in pressures if p['location_x'] >= 66.67])
        total = len(pressures)

        return {
            'defensive': defensive / total * 100,
            'middle': middle / total * 100,
            'attacking': attacking / total * 100
        }

    def calculate_team_tactics(self, team_id: int, season_id: int) -> TeamSeasonTactics:
        """Calculate full tactical profile for a team season."""
        tactics = TeamSeasonTactics(team_id=team_id, season_id=season_id)

        # Network analysis
        tactics.centralization_index = self.analyze_network_centralization(team_id)

        # Line heights
        lines = self.analyze_line_heights(team_id)
        tactics.avg_defensive_line = lines['defensive_line']
        tactics.avg_midfield_line = lines['midfield_line']
        tactics.avg_attacking_line = lines['attacking_line']
        tactics.vertical_compactness = tactics.avg_attacking_line - tactics.avg_defensive_line

        # Pressing zones
        zones = self.analyze_pressing_zones(team_id)
        tactics.press_zone_defensive = zones['defensive']
        tactics.press_zone_middle = zones['middle']
        tactics.press_zone_attacking = zones['attacking']

        return tactics


# ============================================================================
# SQL MATERIALIZATION LOGIC
# ============================================================================

TEAM_MATCH_STYLE_DDL = """
CREATE TABLE IF NOT EXISTS f_team_match_style (
    match_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    is_home BOOLEAN NOT NULL,

    -- Tempo & Possession
    possession_pct FLOAT,
    passes_total INTEGER,
    passes_successful INTEGER,
    pass_accuracy FLOAT,
    passes_per_minute FLOAT,
    avg_pass_length FLOAT,
    direct_speed_index FLOAT,

    -- Pressing
    ppda FLOAT,
    ppda_attacking_third FLOAT,
    high_press_pct FLOAT,
    counterpressing_recoveries INTEGER,
    pressures_total INTEGER,

    -- Buildup
    buildup_passes INTEGER,
    gk_short_pass_pct FLOAT,
    progressive_passes INTEGER,
    progressive_carries INTEGER,
    deep_completions INTEGER,

    -- Chances
    shots INTEGER,
    shots_on_target INTEGER,
    xg_total FLOAT,
    xg_per_shot FLOAT,
    big_chances INTEGER,
    crosses INTEGER,
    through_balls INTEGER,

    -- Shape
    width_index FLOAT,
    left_side_pct FLOAT,
    right_side_pct FLOAT,
    central_pct FLOAT,

    -- Defense
    tackles INTEGER,
    interceptions INTEGER,
    clearances INTEGER,
    blocks INTEGER,
    ball_recoveries INTEGER,
    defensive_line_height FLOAT,

    -- Duels
    aerial_duels_won INTEGER,
    aerial_duels_lost INTEGER,
    ground_duels_won INTEGER,
    ground_duels_lost INTEGER,
    fouls_committed INTEGER,
    fouls_won INTEGER,

    -- Transitions
    transition_attacks INTEGER,
    counter_attacks INTEGER,

    PRIMARY KEY (match_id, team_id),
    FOREIGN KEY (match_id) REFERENCES fact_match(match_id),
    FOREIGN KEY (team_id) REFERENCES dim_team(team_id)
);

CREATE INDEX idx_team_match_style_team ON f_team_match_style(team_id);
CREATE INDEX idx_team_match_style_match ON f_team_match_style(match_id);
"""

TEAM_SEASON_STYLE_DDL = """
CREATE TABLE IF NOT EXISTS f_team_season_style (
    team_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,

    -- Core metrics
    ppda_avg FLOAT,
    possession_avg FLOAT,
    xg_per_shot_avg FLOAT,
    xg_total_avg FLOAT,
    goals_per_match FLOAT,

    -- Pressing
    high_press_pct_avg FLOAT,
    counterpressing_rate FLOAT,

    -- Buildup
    gk_short_pct_avg FLOAT,
    progressive_passes_avg FLOAT,
    deep_completions_avg FLOAT,

    -- Shape
    width_index_avg FLOAT,
    defensive_line_avg FLOAT,

    -- Chances
    big_chances_avg FLOAT,
    box_shots_pct_avg FLOAT,
    cross_rate FLOAT,

    -- Transitions
    transition_attack_rate FLOAT,
    counter_attack_rate FLOAT,

    -- Context
    matches_played INTEGER,
    manager_changes INTEGER,
    era VARCHAR(50),

    PRIMARY KEY (team_id, season_id),
    FOREIGN KEY (team_id) REFERENCES dim_team(team_id),
    FOREIGN KEY (season_id) REFERENCES dim_season(season_id)
);
"""

PLAYER_SEASON_PROFILE_DDL = """
CREATE TABLE IF NOT EXISTS f_player_season_profile (
    player_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,

    position VARCHAR(50),
    minutes_played INTEGER,
    matches_played INTEGER,

    -- Passing
    passes_per_90 FLOAT,
    pass_accuracy FLOAT,
    progressive_passes_per_90 FLOAT,
    crosses_per_90 FLOAT,
    cross_accuracy FLOAT,

    -- Dribbling
    dribbles_per_90 FLOAT,
    dribble_success_rate FLOAT,
    progressive_distance_per_90 FLOAT,

    -- Shooting
    shots_per_90 FLOAT,
    xg_per_90 FLOAT,
    xg_per_shot FLOAT,
    goals_per_90 FLOAT,

    -- Defending
    tackles_per_90 FLOAT,
    tackle_success_rate FLOAT,
    interceptions_per_90 FLOAT,
    blocks_per_90 FLOAT,
    ball_recoveries_per_90 FLOAT,

    -- Pressure
    pressures_per_90 FLOAT,
    pressure_success_rate FLOAT,

    -- Aerial
    aerial_duels_per_90 FLOAT,
    aerial_win_rate FLOAT,

    -- Position
    avg_x_position FLOAT,
    avg_y_position FLOAT,

    PRIMARY KEY (player_id, season_id, team_id),
    FOREIGN KEY (player_id) REFERENCES dim_player(player_id),
    FOREIGN KEY (season_id) REFERENCES dim_season(season_id),
    FOREIGN KEY (team_id) REFERENCES dim_team(team_id)
);
"""
