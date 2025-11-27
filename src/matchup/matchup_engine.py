"""
Matchup Engine for Football Evolution Analysis

Simulates how two teams' styles clash and predicts match outcomes.

Components:
- Feature assembly for matchup analysis
- Style clash metrics
- Score prediction (Poisson/negative-binomial)
- Tactical narrative generation
"""

import math
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class TeamProfile:
    """Team's style profile for matchup analysis."""
    team_id: int
    team_name: str

    # Pressing profile
    ppda: float = 0.0
    high_press_pct: float = 0.0
    counterpressing_rate: float = 0.0

    # Buildup profile
    possession: float = 0.0
    gk_short_pct: float = 0.0
    progressive_passes: float = 0.0
    buildup_speed: float = 0.0  # Direct vs patient

    # Shape
    defensive_line_height: float = 0.0
    width_index: float = 0.0
    vertical_compactness: float = 0.0

    # Attacking
    xg_per_match: float = 0.0
    xg_per_shot: float = 0.0
    box_shots_pct: float = 0.0
    cross_rate: float = 0.0
    transition_attack_rate: float = 0.0

    # Defensive
    xga_per_match: float = 0.0  # xG against
    tackle_success: float = 0.0
    aerial_win_rate: float = 0.0


@dataclass
class MatchupFeatures:
    """Features derived from comparing two team profiles."""
    team_a_id: int
    team_b_id: int

    # Pressing vs Buildup clash
    pressing_vs_buildup_a: float = 0.0  # A's press vs B's buildup
    pressing_vs_buildup_b: float = 0.0  # B's press vs A's buildup

    # Width vs Compactness
    width_mismatch_a: float = 0.0  # A's width vs B's compactness
    width_mismatch_b: float = 0.0

    # Transition vulnerability
    transition_vulnerability_a: float = 0.0
    transition_vulnerability_b: float = 0.0

    # xG force balance
    xg_force_a: float = 0.0  # A's attack vs B's defense
    xg_force_b: float = 0.0

    # Aerial dominance
    aerial_advantage_a: float = 0.0

    # Tempo difference
    tempo_difference: float = 0.0


@dataclass
class MatchPrediction:
    """Match prediction with probabilities."""
    team_a_id: int
    team_b_id: int

    # Expected goals
    xg_team_a: float = 0.0
    xg_team_b: float = 0.0

    # Score probabilities
    team_a_win_prob: float = 0.0
    draw_prob: float = 0.0
    team_b_win_prob: float = 0.0

    # Most likely score
    most_likely_score: Tuple[int, int] = (0, 0)
    most_likely_score_prob: float = 0.0

    # Goal probabilities
    over_2_5_prob: float = 0.0
    btts_prob: float = 0.0  # Both teams to score

    # Confidence
    prediction_confidence: float = 0.0


@dataclass
class TacticalNarrative:
    """Generated tactical narrative for matchup."""
    team_a_name: str
    team_b_name: str

    # Key matchup points
    key_battles: List[str] = field(default_factory=list)

    # Style clash summary
    clash_summary: str = ""

    # Tactical advantages
    team_a_advantages: List[str] = field(default_factory=list)
    team_b_advantages: List[str] = field(default_factory=list)

    # Key player matchups (if available)
    player_matchups: List[str] = field(default_factory=list)

    # Prediction rationale
    prediction_rationale: str = ""


# ============================================================================
# MATCHUP FEATURE CALCULATOR
# ============================================================================

class MatchupCalculator:
    """
    Calculate matchup features from team profiles.

    Analyzes how two teams' styles interact to predict outcomes.
    """

    def calculate_matchup_features(self, team_a: TeamProfile,
                                   team_b: TeamProfile) -> MatchupFeatures:
        """
        Calculate all matchup features between two teams.

        Key matchup dimensions:
        1. Pressing intensity vs buildup quality
        2. Width vs defensive compactness
        3. High line vs counter-attack threat
        4. Aerial dominance
        5. Tempo and possession battle
        """
        features = MatchupFeatures(
            team_a_id=team_a.team_id,
            team_b_id=team_b.team_id
        )

        # Pressing vs Buildup
        # Lower PPDA = more pressing. High gk_short% = patient buildup
        features.pressing_vs_buildup_a = self._calculate_press_buildup_clash(
            team_a.ppda, team_a.high_press_pct,
            team_b.gk_short_pct, team_b.progressive_passes
        )
        features.pressing_vs_buildup_b = self._calculate_press_buildup_clash(
            team_b.ppda, team_b.high_press_pct,
            team_a.gk_short_pct, team_a.progressive_passes
        )

        # Width vs Compactness
        features.width_mismatch_a = self._calculate_width_mismatch(
            team_a.width_index, team_b.vertical_compactness
        )
        features.width_mismatch_b = self._calculate_width_mismatch(
            team_b.width_index, team_a.vertical_compactness
        )

        # Transition vulnerability
        features.transition_vulnerability_a = self._calculate_transition_vulnerability(
            team_a.defensive_line_height, team_b.transition_attack_rate
        )
        features.transition_vulnerability_b = self._calculate_transition_vulnerability(
            team_b.defensive_line_height, team_a.transition_attack_rate
        )

        # xG force balance
        features.xg_force_a = self._calculate_xg_force(
            team_a.xg_per_match, team_b.xga_per_match
        )
        features.xg_force_b = self._calculate_xg_force(
            team_b.xg_per_match, team_a.xga_per_match
        )

        # Aerial advantage
        features.aerial_advantage_a = team_a.aerial_win_rate - team_b.aerial_win_rate

        # Tempo difference
        features.tempo_difference = team_a.possession - team_b.possession

        return features

    def _calculate_press_buildup_clash(self, ppda: float, high_press_pct: float,
                                       opponent_gk_short: float,
                                       opponent_progressive: float) -> float:
        """
        Calculate pressing vs buildup clash score.

        High score = pressing team has advantage.
        Low score = buildup team can play through press.
        """
        # Pressing intensity (inverse of PPDA, capped)
        press_intensity = max(0, 100 - ppda * 5) * (high_press_pct / 100)

        # Buildup resilience
        buildup_resilience = (opponent_gk_short * 0.5 + opponent_progressive * 0.5)

        # Clash score: positive = press wins, negative = buildup wins
        return press_intensity - buildup_resilience

    def _calculate_width_mismatch(self, attacker_width: float,
                                  defender_compactness: float) -> float:
        """
        Calculate width vs compactness mismatch.

        Wide attackers vs compact defenders creates space in wide areas.
        """
        return attacker_width - defender_compactness

    def _calculate_transition_vulnerability(self, defensive_line: float,
                                            opponent_transition_rate: float) -> float:
        """
        Calculate vulnerability to counter-attacks.

        High defensive line + opponent with good transitions = vulnerable.
        """
        return (defensive_line - 50) * opponent_transition_rate / 10

    def _calculate_xg_force(self, attacking_xg: float,
                            opponent_defensive_xg: float) -> float:
        """
        Calculate expected goal force.

        Combines team's attacking output with opponent's defensive weakness.
        """
        return attacking_xg * (opponent_defensive_xg / 1.5)


# ============================================================================
# SCORE PREDICTION MODEL
# ============================================================================

class ScorePredictionModel:
    """
    Predict match scores using Poisson/negative-binomial distribution.

    Steps:
    1. Estimate expected goals for each team
    2. Apply Poisson distribution for goal probabilities
    3. Calculate match outcome probabilities
    """

    def __init__(self, league_avg_goals: float = 2.75):
        self.league_avg_goals = league_avg_goals
        self.home_advantage = 0.25  # xG boost for home team

    def predict_match(self, team_a: TeamProfile, team_b: TeamProfile,
                      matchup_features: MatchupFeatures,
                      team_a_home: bool = True) -> MatchPrediction:
        """
        Generate match prediction.

        Uses team profiles and matchup features to estimate xG,
        then applies Poisson distribution for probabilities.
        """
        # Estimate expected goals
        xg_a = self._estimate_xg(team_a, team_b, matchup_features, team_a_home)
        xg_b = self._estimate_xg(team_b, team_a, matchup_features, not team_a_home)

        # Calculate outcome probabilities using Poisson
        win_a, draw, win_b = self._calculate_outcome_probabilities(xg_a, xg_b)

        # Most likely score
        score, score_prob = self._most_likely_score(xg_a, xg_b)

        # Over/under and BTTS
        over_2_5 = self._calculate_over_probability(xg_a, xg_b, 2.5)
        btts = self._calculate_btts_probability(xg_a, xg_b)

        return MatchPrediction(
            team_a_id=team_a.team_id,
            team_b_id=team_b.team_id,
            xg_team_a=xg_a,
            xg_team_b=xg_b,
            team_a_win_prob=win_a,
            draw_prob=draw,
            team_b_win_prob=win_b,
            most_likely_score=score,
            most_likely_score_prob=score_prob,
            over_2_5_prob=over_2_5,
            btts_prob=btts,
            prediction_confidence=self._calculate_confidence(win_a, draw, win_b)
        )

    def _estimate_xg(self, team: TeamProfile, opponent: TeamProfile,
                     features: MatchupFeatures, is_home: bool) -> float:
        """
        Estimate expected goals for a team.

        Formula:
        xG = base_attack * defensive_weakness_factor * matchup_factor * home_factor
        """
        # Base attacking output
        base_xg = team.xg_per_match

        # Opponent defensive factor (higher xGA = weaker defense)
        defense_factor = opponent.xga_per_match / self.league_avg_goals * 2

        # Matchup adjustments
        xg_force = features.xg_force_a if team.team_id == features.team_a_id else features.xg_force_b
        matchup_factor = 1 + (xg_force - 1) * 0.2

        # Home advantage
        home_factor = 1 + (self.home_advantage if is_home else -self.home_advantage * 0.5)

        estimated_xg = base_xg * defense_factor * matchup_factor * home_factor

        # Cap at reasonable range
        return max(0.3, min(4.0, estimated_xg))

    def _poisson_probability(self, lam: float, k: int) -> float:
        """Calculate Poisson probability P(X = k) for lambda."""
        return (lam ** k) * math.exp(-lam) / math.factorial(k)

    def _calculate_outcome_probabilities(self, xg_a: float,
                                         xg_b: float) -> Tuple[float, float, float]:
        """
        Calculate win/draw/loss probabilities.

        Uses Poisson distribution for each possible scoreline.
        """
        max_goals = 10  # Consider up to 10 goals per team

        win_a = 0.0
        draw = 0.0
        win_b = 0.0

        for goals_a in range(max_goals):
            prob_a = self._poisson_probability(xg_a, goals_a)
            for goals_b in range(max_goals):
                prob_b = self._poisson_probability(xg_b, goals_b)
                joint_prob = prob_a * prob_b

                if goals_a > goals_b:
                    win_a += joint_prob
                elif goals_a == goals_b:
                    draw += joint_prob
                else:
                    win_b += joint_prob

        # Normalize
        total = win_a + draw + win_b
        return win_a / total, draw / total, win_b / total

    def _most_likely_score(self, xg_a: float,
                           xg_b: float) -> Tuple[Tuple[int, int], float]:
        """Find most likely scoreline."""
        max_prob = 0.0
        best_score = (0, 0)

        for goals_a in range(6):
            for goals_b in range(6):
                prob = (self._poisson_probability(xg_a, goals_a) *
                        self._poisson_probability(xg_b, goals_b))
                if prob > max_prob:
                    max_prob = prob
                    best_score = (goals_a, goals_b)

        return best_score, max_prob

    def _calculate_over_probability(self, xg_a: float, xg_b: float,
                                    threshold: float) -> float:
        """Calculate probability of total goals over threshold."""
        max_goals = 10
        over_prob = 0.0

        for goals_a in range(max_goals):
            prob_a = self._poisson_probability(xg_a, goals_a)
            for goals_b in range(max_goals):
                prob_b = self._poisson_probability(xg_b, goals_b)
                if goals_a + goals_b > threshold:
                    over_prob += prob_a * prob_b

        return over_prob

    def _calculate_btts_probability(self, xg_a: float, xg_b: float) -> float:
        """Calculate probability of both teams scoring."""
        # P(A scores) * P(B scores)
        prob_a_scores = 1 - self._poisson_probability(xg_a, 0)
        prob_b_scores = 1 - self._poisson_probability(xg_b, 0)
        return prob_a_scores * prob_b_scores

    def _calculate_confidence(self, win_a: float, draw: float,
                              win_b: float) -> float:
        """
        Calculate prediction confidence.

        Higher confidence when one outcome dominates.
        """
        max_prob = max(win_a, draw, win_b)
        # Confidence based on how dominant the prediction is
        return max_prob * 2 if max_prob > 0.5 else max_prob


# ============================================================================
# TACTICAL NARRATIVE GENERATOR
# ============================================================================

class TacticalNarrativeGenerator:
    """
    Generate human-readable tactical narratives for matchups.

    Explains:
    - How styles will clash
    - Key tactical advantages
    - Prediction rationale
    """

    def generate_narrative(self, team_a: TeamProfile, team_b: TeamProfile,
                           features: MatchupFeatures,
                           prediction: MatchPrediction) -> TacticalNarrative:
        """Generate complete tactical narrative."""
        narrative = TacticalNarrative(
            team_a_name=team_a.team_name,
            team_b_name=team_b.team_name
        )

        # Generate clash summary
        narrative.clash_summary = self._generate_clash_summary(
            team_a, team_b, features
        )

        # Key battles
        narrative.key_battles = self._identify_key_battles(
            team_a, team_b, features
        )

        # Team advantages
        narrative.team_a_advantages = self._identify_advantages(
            team_a, team_b, features, True
        )
        narrative.team_b_advantages = self._identify_advantages(
            team_b, team_a, features, False
        )

        # Prediction rationale
        narrative.prediction_rationale = self._generate_prediction_rationale(
            team_a, team_b, features, prediction
        )

        return narrative

    def _generate_clash_summary(self, team_a: TeamProfile, team_b: TeamProfile,
                                features: MatchupFeatures) -> str:
        """Generate overview of style clash."""
        # Determine primary styles
        style_a = self._classify_style(team_a)
        style_b = self._classify_style(team_b)

        return (
            f"This match features a clash between {team_a.team_name}'s "
            f"{style_a} approach and {team_b.team_name}'s {style_b} style. "
            f"{self._describe_tempo_battle(features)}"
        )

    def _classify_style(self, team: TeamProfile) -> str:
        """Classify team's primary style."""
        if team.ppda < 8 and team.high_press_pct > 40:
            return "high-pressing, intense"
        elif team.possession > 55:
            return "possession-dominant"
        elif team.transition_attack_rate > 15:
            return "counter-attacking"
        elif team.defensive_line_height < 40:
            return "deep-block defensive"
        else:
            return "balanced"

    def _describe_tempo_battle(self, features: MatchupFeatures) -> str:
        """Describe the tempo battle between teams."""
        if abs(features.tempo_difference) > 10:
            if features.tempo_difference > 0:
                return "Expect a possession battle with Team A looking to dominate the ball."
            else:
                return "Team B will likely control possession, forcing Team A to be patient."
        else:
            return "Both teams have similar possession profiles, suggesting an even contest for control."

    def _identify_key_battles(self, team_a: TeamProfile, team_b: TeamProfile,
                              features: MatchupFeatures) -> List[str]:
        """Identify key tactical battles."""
        battles = []

        # Press vs Buildup
        if abs(features.pressing_vs_buildup_a) > 10:
            if features.pressing_vs_buildup_a > 0:
                battles.append(
                    f"{team_a.team_name}'s high press will test "
                    f"{team_b.team_name}'s buildup play"
                )
            else:
                battles.append(
                    f"{team_b.team_name}'s patient buildup should be able to "
                    f"play through {team_a.team_name}'s press"
                )

        # Width battle
        if abs(features.width_mismatch_a) > 5:
            if features.width_mismatch_a > 0:
                battles.append(
                    f"{team_a.team_name}'s wide overloads will target "
                    f"{team_b.team_name}'s narrow block"
                )
            else:
                battles.append(
                    f"{team_b.team_name}'s compact shape should limit "
                    f"{team_a.team_name}'s wide attacks"
                )

        # Transition threat
        if features.transition_vulnerability_a > 5:
            battles.append(
                f"{team_a.team_name}'s high line leaves space for "
                f"{team_b.team_name}'s counter-attacks"
            )
        if features.transition_vulnerability_b > 5:
            battles.append(
                f"{team_b.team_name}'s high line creates opportunities for "
                f"{team_a.team_name}'s transitions"
            )

        # Aerial battle
        if abs(features.aerial_advantage_a) > 10:
            winner = team_a.team_name if features.aerial_advantage_a > 0 else team_b.team_name
            battles.append(f"{winner} has a clear aerial advantage")

        return battles

    def _identify_advantages(self, team: TeamProfile, opponent: TeamProfile,
                             features: MatchupFeatures, is_team_a: bool) -> List[str]:
        """Identify tactical advantages for a team."""
        advantages = []

        # Higher xG output
        if team.xg_per_match > opponent.xg_per_match + 0.3:
            advantages.append("Superior attacking output")

        # Better defense
        if team.xga_per_match < opponent.xga_per_match - 0.3:
            advantages.append("Stronger defensive record")

        # Pressing advantage
        if team.ppda < opponent.ppda - 3:
            advantages.append("More intense pressing game")

        # Transition threat
        if team.transition_attack_rate > opponent.transition_attack_rate + 5:
            advantages.append("More dangerous in transition")

        # Set piece threat (from cross rate as proxy)
        if team.cross_rate > opponent.cross_rate + 3:
            advantages.append("Greater threat from wide areas and set pieces")

        return advantages

    def _generate_prediction_rationale(self, team_a: TeamProfile,
                                       team_b: TeamProfile,
                                       features: MatchupFeatures,
                                       prediction: MatchPrediction) -> str:
        """Generate explanation for the prediction."""
        # Determine predicted winner
        if prediction.team_a_win_prob > prediction.team_b_win_prob + 0.1:
            winner = team_a.team_name
            prob = prediction.team_a_win_prob
            xg_diff = prediction.xg_team_a - prediction.xg_team_b
        elif prediction.team_b_win_prob > prediction.team_a_win_prob + 0.1:
            winner = team_b.team_name
            prob = prediction.team_b_win_prob
            xg_diff = prediction.xg_team_b - prediction.xg_team_a
        else:
            return (
                f"This is projected to be a tight contest. Both teams are "
                f"evenly matched with draw probability at {prediction.draw_prob:.0%}. "
                f"Expected scoreline: {prediction.most_likely_score[0]}-{prediction.most_likely_score[1]}."
            )

        return (
            f"{winner} is favored to win ({prob:.0%} probability) based on "
            f"an expected goals advantage of {xg_diff:.2f}. "
            f"Most likely scoreline: {prediction.most_likely_score[0]}-{prediction.most_likely_score[1]} "
            f"({prediction.most_likely_score_prob:.0%})."
        )


# ============================================================================
# MATCHUP ENGINE API
# ============================================================================

class MatchupEngine:
    """
    Main matchup engine combining all components.

    Provides unified interface for matchup analysis.
    """

    def __init__(self):
        self.matchup_calculator = MatchupCalculator()
        self.score_predictor = ScorePredictionModel()
        self.narrative_generator = TacticalNarrativeGenerator()

    def analyze_matchup(self, team_a: TeamProfile, team_b: TeamProfile,
                        team_a_home: bool = True) -> Dict[str, Any]:
        """
        Complete matchup analysis.

        Returns:
            Dictionary with features, prediction, and narrative.
        """
        # Calculate matchup features
        features = self.matchup_calculator.calculate_matchup_features(
            team_a, team_b
        )

        # Generate prediction
        prediction = self.score_predictor.predict_match(
            team_a, team_b, features, team_a_home
        )

        # Generate narrative
        narrative = self.narrative_generator.generate_narrative(
            team_a, team_b, features, prediction
        )

        return {
            'matchup_features': features,
            'prediction': prediction,
            'narrative': narrative
        }

    def get_team_profile(self, team_id: int) -> Optional[TeamProfile]:
        """
        Load team profile from database.

        Would query f_team_season_style and other feature tables.
        """
        # Placeholder - in production would query database
        return None

    def batch_analyze(self, matchups: List[Tuple[int, int]],
                      team_a_home: List[bool]) -> List[Dict[str, Any]]:
        """Analyze multiple matchups."""
        results = []
        for (team_a_id, team_b_id), is_home in zip(matchups, team_a_home):
            team_a = self.get_team_profile(team_a_id)
            team_b = self.get_team_profile(team_b_id)

            if team_a and team_b:
                result = self.analyze_matchup(team_a, team_b, is_home)
                results.append(result)

        return results


# ============================================================================
# API RESPONSE SCHEMAS
# ============================================================================

@dataclass
class EvolutionResponse:
    """Response schema for /evolution/{team_id} endpoint."""
    team_id: int
    team_name: str
    current_season: Dict[str, float]
    historical_evolution: List[Dict[str, Any]]
    era_comparison: Dict[str, Any]
    key_changes: List[str]


@dataclass
class ForecastResponse:
    """Response schema for /forecast/{team_id} endpoint."""
    team_id: int
    team_name: str
    target_season: int
    predictions: Dict[str, float]
    confidence_intervals: Dict[str, Tuple[float, float]]
    key_drivers: List[Dict[str, float]]
    model_info: Dict[str, str]


@dataclass
class MatchupResponse:
    """Response schema for /matchup/{teamA}/{teamB} endpoint."""
    team_a: Dict[str, Any]
    team_b: Dict[str, Any]
    matchup_features: Dict[str, float]
    prediction: Dict[str, float]
    narrative: Dict[str, Any]
    tactical_insights: List[str]


def format_evolution_response(team_profile: TeamProfile,
                              historical_data: List[Dict]) -> Dict:
    """Format evolution data for API response."""
    return {
        "team_id": team_profile.team_id,
        "team_name": team_profile.team_name,
        "current_profile": {
            "ppda": team_profile.ppda,
            "possession": team_profile.possession,
            "xg_per_match": team_profile.xg_per_match,
            "high_press_pct": team_profile.high_press_pct,
            "transition_rate": team_profile.transition_attack_rate
        },
        "evolution_trend": historical_data,
        "style_classification": MatchupCalculator()._classify_style(
            team_profile) if hasattr(MatchupCalculator, '_classify_style') else "balanced"
    }


def format_matchup_response(result: Dict[str, Any],
                            team_a: TeamProfile,
                            team_b: TeamProfile) -> Dict:
    """Format matchup result for API response."""
    prediction = result['prediction']
    narrative = result['narrative']

    return {
        "teams": {
            "team_a": {"id": team_a.team_id, "name": team_a.team_name},
            "team_b": {"id": team_b.team_id, "name": team_b.team_name}
        },
        "prediction": {
            "expected_goals": {
                "team_a": prediction.xg_team_a,
                "team_b": prediction.xg_team_b
            },
            "probabilities": {
                "team_a_win": prediction.team_a_win_prob,
                "draw": prediction.draw_prob,
                "team_b_win": prediction.team_b_win_prob
            },
            "likely_score": prediction.most_likely_score,
            "over_2_5": prediction.over_2_5_prob,
            "btts": prediction.btts_prob
        },
        "tactical_analysis": {
            "clash_summary": narrative.clash_summary,
            "key_battles": narrative.key_battles,
            "team_a_advantages": narrative.team_a_advantages,
            "team_b_advantages": narrative.team_b_advantages,
            "prediction_rationale": narrative.prediction_rationale
        }
    }
