"""
Evolution Analysis & Variance Decomposition Module

This module quantifies how much of football's evolution comes from skill vs tactics.

Components:
- Three-model framework (Skill-only, Tactic-only, Combined)
- Variance decomposition analysis
- Feature importance (SHAP values)
- Natural experiment analysis
"""

import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json


# ============================================================================
# DATA STRUCTURES
# ============================================================================

class ModelType(Enum):
    """Model types for comparison."""
    SKILL_ONLY = "skill_only"
    TACTIC_ONLY = "tactic_only"
    COMBINED = "combined"


@dataclass
class ModelResult:
    """Results from a trained model."""
    model_type: ModelType
    target: str
    r2_score: float
    mae: float
    rmse: float
    feature_importances: Dict[str, float] = field(default_factory=dict)
    shap_values: Optional[np.ndarray] = None
    cv_scores: List[float] = field(default_factory=list)


@dataclass
class VarianceDecomposition:
    """Variance decomposition results."""
    target: str
    r2_skill_only: float
    r2_tactic_only: float
    r2_combined: float
    r2_unique_skill: float  # Variance explained uniquely by skill
    r2_unique_tactics: float  # Variance explained uniquely by tactics
    r2_shared: float  # Shared/interaction variance
    skill_contribution_pct: float
    tactics_contribution_pct: float
    interaction_pct: float


@dataclass
class NaturalExperiment:
    """Natural experiment analysis result."""
    experiment_type: str  # 'manager_change', 'star_player', 'tactical_shift'
    team_id: int
    treatment_date: str
    pre_period: Tuple[str, str]
    post_period: Tuple[str, str]
    control_variable: str
    treatment_variable: str
    outcome_variable: str
    pre_mean: float
    post_mean: float
    difference: float
    p_value: float
    effect_size: float
    interpretation: str


# ============================================================================
# FEATURE DEFINITIONS
# ============================================================================

# Skill features - Player-level aggregated to team
SKILL_FEATURES = [
    # Technical
    'squad_pass_accuracy',
    'squad_dribble_success',
    'squad_progressive_passes',
    'squad_cross_accuracy',
    'squad_long_pass_accuracy',

    # Shooting/Attacking
    'squad_xg_per_90',
    'squad_xa_per_90',
    'squad_shot_quality',
    'squad_shot_accuracy',

    # Defensive
    'squad_tackle_success',
    'squad_interception_rate',
    'squad_aerial_win_rate',
    'squad_pressure_success',

    # Physical/Intensity
    'squad_sprints_per_90',
    'squad_distance_covered',
    'squad_duels_per_90',

    # Composition
    'squad_avg_age',
    'squad_minutes_weighted_age',
    'xg_concentration',
    'creativity_concentration',
]

# Tactical features - Team structure and patterns
TACTICAL_FEATURES = [
    # Formation & Shape
    'primary_formation_encoded',
    'formation_flexibility',
    'vertical_compactness',

    # Line heights
    'avg_defensive_line',
    'avg_midfield_line',
    'avg_attacking_line',

    # Pressing profile
    'ppda_avg',
    'high_press_pct_avg',
    'press_zone_attacking',
    'press_zone_middle',
    'counterpressing_rate',

    # Buildup structure
    'gk_short_pct_avg',
    'short_buildup_pct',
    'wing_buildup_pct',
    'central_buildup_pct',

    # Network
    'centralization_index',
    'clustering_coefficient',
    'avg_pass_chain_length',

    # Width & positioning
    'width_index_avg',
    'left_side_pct_avg',
    'right_side_pct_avg',

    # Transition
    'direct_counter_rate',
    'transition_attack_rate',
]

# Target/Evolution metrics
EVOLUTION_TARGETS = [
    'ppda_avg',  # Pressing intensity evolution
    'possession_avg',  # Possession evolution
    'xg_per_shot_avg',  # Shot quality evolution
    'xg_total_avg',  # Total attacking output
    'high_press_pct_avg',  # High pressing adoption
    'progressive_passes_avg',  # Progressive play evolution
    'transition_attack_rate',  # Counter-attacking evolution
]


# ============================================================================
# MODEL FRAMEWORK
# ============================================================================

class EvolutionModelFramework:
    """
    Three-model framework for skill vs tactics analysis.

    Models:
    1. M_skill: Uses only squad skill features
    2. M_tactic: Uses only tactical setup features
    3. M_combined: Uses all features

    Analysis:
    - Compare R², MAE across model sets
    - Variance decomposition
    - Feature importance via SHAP
    """

    def __init__(self, random_state: int = 42):
        self.random_state = random_state
        self.models: Dict[str, Dict[ModelType, Any]] = {}
        self.results: Dict[str, Dict[ModelType, ModelResult]] = {}

    def prepare_features(self, data: List[Dict[str, Any]],
                         model_type: ModelType) -> Tuple[np.ndarray, List[str]]:
        """
        Prepare feature matrix based on model type.

        Args:
            data: List of team-season records
            model_type: Which features to include

        Returns:
            Feature matrix and feature names
        """
        if model_type == ModelType.SKILL_ONLY:
            feature_names = SKILL_FEATURES
        elif model_type == ModelType.TACTIC_ONLY:
            feature_names = TACTICAL_FEATURES
        else:  # COMBINED
            feature_names = SKILL_FEATURES + TACTICAL_FEATURES

        # Build feature matrix
        X = []
        for record in data:
            row = [record.get(f, 0) for f in feature_names]
            X.append(row)

        return np.array(X), feature_names

    def prepare_target(self, data: List[Dict[str, Any]], target: str) -> np.ndarray:
        """Extract target variable from data."""
        return np.array([record.get(target, 0) for record in data])

    def train_model(self, X: np.ndarray, y: np.ndarray,
                    model_type: ModelType, target: str) -> ModelResult:
        """
        Train a model and return results.

        Uses Ridge regression for interpretability.
        Cross-validates using time-series aware splits.

        Pseudocode:
        ```python
        from sklearn.linear_model import RidgeCV
        from sklearn.model_selection import TimeSeriesSplit
        from sklearn.metrics import r2_score, mean_absolute_error

        # Time-series cross-validation
        tscv = TimeSeriesSplit(n_splits=5)

        # Fit model
        model = RidgeCV(alphas=[0.1, 1.0, 10.0], cv=tscv)
        model.fit(X, y)

        # Predictions and metrics
        y_pred = model.predict(X)
        r2 = r2_score(y, y_pred)
        mae = mean_absolute_error(y, y_pred)

        # Feature importance from coefficients
        importances = dict(zip(feature_names, abs(model.coef_)))
        ```
        """
        # Placeholder for actual model training
        # In production, use sklearn.linear_model.RidgeCV or XGBoost

        # Simulated results for demonstration
        result = ModelResult(
            model_type=model_type,
            target=target,
            r2_score=0.0,
            mae=0.0,
            rmse=0.0,
            feature_importances={},
            cv_scores=[]
        )

        return result

    def run_full_analysis(self, data: List[Dict[str, Any]],
                          target: str) -> Dict[ModelType, ModelResult]:
        """
        Run all three model types for a target.

        Returns results for comparison.
        """
        results = {}

        for model_type in ModelType:
            X, feature_names = self.prepare_features(data, model_type)
            y = self.prepare_target(data, target)

            result = self.train_model(X, y, model_type, target)
            results[model_type] = result

        self.results[target] = results
        return results

    def compute_variance_decomposition(self, target: str) -> VarianceDecomposition:
        """
        Decompose variance into skill, tactics, and interaction components.

        Formula:
        R²_unique_skill = R²_combined - R²_tactic_only
        R²_unique_tactics = R²_combined - R²_skill_only
        R²_shared = R²_skill_only + R²_tactic_only - R²_combined
                  = R²_combined - R²_unique_skill - R²_unique_tactics
        """
        if target not in self.results:
            raise ValueError(f"No results for target: {target}")

        results = self.results[target]
        r2_skill = results[ModelType.SKILL_ONLY].r2_score
        r2_tactic = results[ModelType.TACTIC_ONLY].r2_score
        r2_combined = results[ModelType.COMBINED].r2_score

        # Variance components
        r2_unique_skill = max(0, r2_combined - r2_tactic)
        r2_unique_tactics = max(0, r2_combined - r2_skill)
        r2_shared = max(0, r2_combined - r2_unique_skill - r2_unique_tactics)

        # Percentages (of combined R²)
        total = r2_unique_skill + r2_unique_tactics + r2_shared
        if total > 0:
            skill_pct = r2_unique_skill / total * 100
            tactics_pct = r2_unique_tactics / total * 100
            interaction_pct = r2_shared / total * 100
        else:
            skill_pct = tactics_pct = interaction_pct = 0

        return VarianceDecomposition(
            target=target,
            r2_skill_only=r2_skill,
            r2_tactic_only=r2_tactic,
            r2_combined=r2_combined,
            r2_unique_skill=r2_unique_skill,
            r2_unique_tactics=r2_unique_tactics,
            r2_shared=r2_shared,
            skill_contribution_pct=skill_pct,
            tactics_contribution_pct=tactics_pct,
            interaction_pct=interaction_pct
        )


# ============================================================================
# SHAP VALUE ANALYSIS
# ============================================================================

class SHAPAnalyzer:
    """
    SHAP-based feature importance analysis.

    Provides:
    - Individual feature contributions
    - Group-wise importance (skill block vs tactics block)
    - Feature interaction effects
    """

    def __init__(self, model, X: np.ndarray, feature_names: List[str]):
        self.model = model
        self.X = X
        self.feature_names = feature_names
        self.shap_values = None

    def compute_shap_values(self):
        """
        Compute SHAP values for the model.

        Pseudocode:
        ```python
        import shap

        explainer = shap.Explainer(self.model, self.X)
        self.shap_values = explainer(self.X)
        ```
        """
        # Placeholder - in production use shap library
        pass

    def get_feature_importance(self) -> Dict[str, float]:
        """
        Get mean absolute SHAP values per feature.

        Returns dict of feature name -> importance score.
        """
        if self.shap_values is None:
            return {}

        # mean(|SHAP|) for each feature
        importances = {}
        for i, name in enumerate(self.feature_names):
            importances[name] = float(np.mean(np.abs(self.shap_values[:, i])))

        return dict(sorted(importances.items(), key=lambda x: -x[1]))

    def get_group_importance(self) -> Dict[str, float]:
        """
        Get importance by feature group (skill vs tactics).

        Returns sum of SHAP values for each group.
        """
        if self.shap_values is None:
            return {'skill': 0, 'tactics': 0}

        skill_importance = 0
        tactics_importance = 0

        for i, name in enumerate(self.feature_names):
            importance = float(np.mean(np.abs(self.shap_values[:, i])))
            if name in SKILL_FEATURES:
                skill_importance += importance
            elif name in TACTICAL_FEATURES:
                tactics_importance += importance

        return {
            'skill': skill_importance,
            'tactics': tactics_importance
        }


# ============================================================================
# NATURAL EXPERIMENTS
# ============================================================================

class NaturalExperimentAnalyzer:
    """
    Analyze natural experiments for causal inference.

    Types:
    1. Manager Change (controlled for squad)
    2. Star Player Transfer (controlled for manager)
    3. Mid-season Tactical Shift (controlled for both)
    """

    def __init__(self, team_data: List[Dict], manager_history: List[Dict],
                 transfer_history: List[Dict]):
        self.team_data = team_data
        self.manager_history = manager_history
        self.transfer_history = transfer_history

    def find_manager_change_experiments(self) -> List[NaturalExperiment]:
        """
        Find manager changes with stable squad.

        Criteria:
        - New manager appointment
        - <20% squad turnover
        - At least 10 matches before and after
        """
        experiments = []

        for change in self.manager_history:
            if change.get('is_interim'):
                continue

            team_id = change['team_id']
            change_date = change['start_date']

            # Check squad stability around change
            squad_stability = self._calculate_squad_stability(
                team_id, change_date
            )

            if squad_stability > 0.8:  # 80% continuity
                experiment = self._create_manager_experiment(change)
                if experiment:
                    experiments.append(experiment)

        return experiments

    def find_star_player_experiments(self) -> List[NaturalExperiment]:
        """
        Find star player arrivals/departures with stable manager.

        Criteria:
        - Top 3 player by minutes/xG arrives or leaves
        - Same manager before and after
        - At least 10 matches in each period
        """
        experiments = []

        for transfer in self.transfer_history:
            player_impact = self._assess_player_impact(transfer['player_id'])

            if player_impact >= 0.8:  # High-impact player
                # Check manager stability
                if self._manager_stable_around_transfer(transfer):
                    experiment = self._create_player_experiment(transfer)
                    if experiment:
                        experiments.append(experiment)

        return experiments

    def _calculate_squad_stability(self, team_id: int,
                                   around_date: str) -> float:
        """
        Calculate squad continuity around a date.

        Returns: float 0-1 indicating squad overlap.
        """
        # Placeholder - compare lineups before/after date
        return 0.85

    def _assess_player_impact(self, player_id: int) -> float:
        """
        Assess player's impact on team performance.

        Uses minutes share, xG share, key action rate.
        """
        # Placeholder - query player stats
        return 0.7

    def _manager_stable_around_transfer(self, transfer: Dict) -> bool:
        """Check if same manager before/after transfer."""
        # Placeholder - check manager history
        return True

    def _create_manager_experiment(self, change: Dict) -> Optional[NaturalExperiment]:
        """Create experiment object for manager change."""
        return NaturalExperiment(
            experiment_type='manager_change',
            team_id=change['team_id'],
            treatment_date=change['start_date'],
            pre_period=('', ''),  # To be filled
            post_period=('', ''),
            control_variable='squad_skill_profile',
            treatment_variable='tactical_setup',
            outcome_variable='ppda_avg',
            pre_mean=0.0,
            post_mean=0.0,
            difference=0.0,
            p_value=0.0,
            effect_size=0.0,
            interpretation=''
        )

    def _create_player_experiment(self, transfer: Dict) -> Optional[NaturalExperiment]:
        """Create experiment object for player transfer."""
        return NaturalExperiment(
            experiment_type='star_player',
            team_id=transfer['to_team_id'],
            treatment_date=transfer['transfer_date'],
            pre_period=('', ''),
            post_period=('', ''),
            control_variable='tactical_setup',
            treatment_variable='squad_skill_profile',
            outcome_variable='xg_per_shot_avg',
            pre_mean=0.0,
            post_mean=0.0,
            difference=0.0,
            p_value=0.0,
            effect_size=0.0,
            interpretation=''
        )

    def analyze_difference_in_differences(self,
                                          experiment: NaturalExperiment) -> NaturalExperiment:
        """
        Run Difference-in-Differences analysis.

        DiD Formula:
        Effect = (Y_treated_post - Y_treated_pre) - (Y_control_post - Y_control_pre)

        For manager change:
        - Treatment: new manager
        - Control: Similar teams with no manager change
        """
        # Get pre/post data for treatment group
        pre_data = self._get_period_data(
            experiment.team_id,
            experiment.pre_period
        )
        post_data = self._get_period_data(
            experiment.team_id,
            experiment.post_period
        )

        # Calculate means
        pre_mean = np.mean([d[experiment.outcome_variable] for d in pre_data]) if pre_data else 0
        post_mean = np.mean([d[experiment.outcome_variable] for d in post_data]) if post_data else 0

        # Simple difference (without control group for now)
        difference = post_mean - pre_mean

        # Effect size (Cohen's d)
        pre_std = np.std([d[experiment.outcome_variable] for d in pre_data]) if pre_data else 1
        effect_size = difference / pre_std if pre_std > 0 else 0

        # Update experiment with results
        experiment.pre_mean = pre_mean
        experiment.post_mean = post_mean
        experiment.difference = difference
        experiment.effect_size = effect_size

        # Generate interpretation
        experiment.interpretation = self._generate_interpretation(experiment)

        return experiment

    def _get_period_data(self, team_id: int,
                         period: Tuple[str, str]) -> List[Dict]:
        """Get team data for a time period."""
        return [
            d for d in self.team_data
            if d.get('team_id') == team_id
            and period[0] <= d.get('date', '') <= period[1]
        ]

    def _generate_interpretation(self, experiment: NaturalExperiment) -> str:
        """Generate human-readable interpretation."""
        if experiment.experiment_type == 'manager_change':
            if experiment.difference > 0:
                return (f"After manager change, {experiment.outcome_variable} "
                        f"increased by {experiment.difference:.2f} "
                        f"(effect size: {experiment.effect_size:.2f}). "
                        f"This suggests tactical changes had a positive impact.")
            else:
                return (f"After manager change, {experiment.outcome_variable} "
                        f"decreased by {abs(experiment.difference):.2f}. "
                        f"Tactical adjustments may have reduced this metric.")

        elif experiment.experiment_type == 'star_player':
            direction = "arrival" if experiment.difference > 0 else "departure"
            return (f"Player {direction} changed {experiment.outcome_variable} "
                    f"by {experiment.difference:.2f} "
                    f"(effect size: {experiment.effect_size:.2f}). "
                    f"This quantifies the player's contribution to team style.")

        return "No interpretation available."


# ============================================================================
# INTERPRETATION ENGINE
# ============================================================================

class EvolutionInterpreter:
    """
    Generate interpretations for evolution analysis results.

    Explains:
    - What drives pressing evolution
    - What drives shot-quality evolution
    - What drives transition-vs-possession play
    """

    def __init__(self, decomposition_results: Dict[str, VarianceDecomposition],
                 feature_importances: Dict[str, Dict[str, float]]):
        self.decompositions = decomposition_results
        self.importances = feature_importances

    def interpret_pressing_evolution(self) -> str:
        """
        Explain what drives pressing evolution (PPDA changes).

        Analyzes:
        - Tactical factors: Press zone settings, counterpressing systems
        - Skill factors: Player speed, stamina, positioning intelligence
        """
        target = 'ppda_avg'
        if target not in self.decompositions:
            return "No analysis available for pressing evolution."

        decomp = self.decompositions[target]
        imps = self.importances.get(target, {})

        interpretation = [
            "## Pressing Evolution Analysis",
            "",
            f"Pressing intensity (PPDA) is explained by:",
            f"- Tactical factors: {decomp.tactics_contribution_pct:.1f}%",
            f"- Skill factors: {decomp.skill_contribution_pct:.1f}%",
            f"- Interaction: {decomp.interaction_pct:.1f}%",
            "",
        ]

        # Top drivers
        if imps:
            top_features = sorted(imps.items(), key=lambda x: -x[1])[:5]
            interpretation.append("### Top Drivers:")
            for feat, imp in top_features:
                is_tactical = feat in TACTICAL_FEATURES
                category = "tactical" if is_tactical else "skill"
                interpretation.append(f"- {feat} ({category}): {imp:.3f}")

        # Tactical interpretation
        if decomp.tactics_contribution_pct > decomp.skill_contribution_pct:
            interpretation.extend([
                "",
                "### Key Finding:",
                "Pressing intensity is primarily driven by **tactical setup** rather than player skills.",
                "Manager decisions about pressing triggers, zones, and coordination matter more",
                "than individual player attributes for determining pressing intensity."
            ])
        else:
            interpretation.extend([
                "",
                "### Key Finding:",
                "Pressing intensity depends significantly on **player skills**.",
                "Teams need players with the physical capacity and tactical intelligence",
                "to execute high-pressing systems effectively."
            ])

        return "\n".join(interpretation)

    def interpret_shot_quality_evolution(self) -> str:
        """
        Explain what drives shot quality evolution (xG/shot changes).

        Analyzes:
        - Tactical factors: Chance creation patterns, buildup structure
        - Skill factors: Finishing ability, positioning, movement
        """
        target = 'xg_per_shot_avg'
        if target not in self.decompositions:
            return "No analysis available for shot quality evolution."

        decomp = self.decompositions[target]
        imps = self.importances.get(target, {})

        interpretation = [
            "## Shot Quality Evolution Analysis",
            "",
            f"Shot quality (xG/shot) is explained by:",
            f"- Tactical factors: {decomp.tactics_contribution_pct:.1f}%",
            f"- Skill factors: {decomp.skill_contribution_pct:.1f}%",
            f"- Interaction: {decomp.interaction_pct:.1f}%",
            "",
        ]

        # Interpretation based on dominant factor
        if decomp.skill_contribution_pct > 50:
            interpretation.extend([
                "### Key Finding:",
                "Shot quality is heavily influenced by **individual player quality**.",
                "Teams with elite attackers generate higher-quality chances regardless",
                "of tactical setup, suggesting player recruitment is crucial."
            ])
        elif decomp.tactics_contribution_pct > 50:
            interpretation.extend([
                "### Key Finding:",
                "Shot quality is primarily driven by **tactical patterns**.",
                "How teams create chances (central vs wide, quick vs patient)",
                "matters more than individual finishing ability."
            ])
        else:
            interpretation.extend([
                "### Key Finding:",
                "Shot quality requires both **skilled players and good tactics**.",
                "The interaction between individual ability and team patterns",
                "is crucial for generating high-quality chances."
            ])

        return "\n".join(interpretation)

    def interpret_style_evolution(self) -> str:
        """
        Explain transition-vs-possession play evolution.

        Analyzes tempo, directness, and possession patterns.
        """
        targets = ['possession_avg', 'transition_attack_rate']
        interpretations = [
            "## Playing Style Evolution Analysis",
            "",
        ]

        for target in targets:
            if target in self.decompositions:
                decomp = self.decompositions[target]
                interpretations.extend([
                    f"### {target}",
                    f"- Tactics: {decomp.tactics_contribution_pct:.1f}%",
                    f"- Skills: {decomp.skill_contribution_pct:.1f}%",
                    ""
                ])

        interpretations.extend([
            "### Key Insights:",
            "",
            "**Possession Football:**",
            "- Requires both technical players and positional discipline",
            "- Tactical setup (formations, positioning) enables possession",
            "- Player comfort on the ball determines execution quality",
            "",
            "**Transition Play:**",
            "- More dependent on tactical organization (pressing triggers, outlets)",
            "- Speed and directness are player attributes",
            "- Manager philosophy determines when to counter vs retain"
        ])

        return "\n".join(interpretations)

    def generate_full_report(self) -> str:
        """Generate complete evolution analysis report."""
        sections = [
            "# Football Evolution: Skill vs Tactics Analysis Report",
            "",
            self.interpret_pressing_evolution(),
            "",
            self.interpret_shot_quality_evolution(),
            "",
            self.interpret_style_evolution(),
        ]

        return "\n".join(sections)


# ============================================================================
# COMPLETE ANALYSIS PIPELINE
# ============================================================================

class EvolutionAnalysisPipeline:
    """
    Complete pipeline for evolution analysis.

    Steps:
    1. Load and prepare data
    2. Train three-model framework for each target
    3. Compute variance decomposition
    4. Run natural experiments
    5. Generate interpretations
    """

    def __init__(self, team_season_data: List[Dict],
                 manager_history: List[Dict],
                 transfer_history: List[Dict]):
        self.team_data = team_season_data
        self.manager_history = manager_history
        self.transfer_history = transfer_history
        self.model_framework = EvolutionModelFramework()
        self.results: Dict[str, Any] = {}

    def run(self) -> Dict[str, Any]:
        """Execute full analysis pipeline."""
        # Step 1: Train models for each target
        for target in EVOLUTION_TARGETS:
            self.model_framework.run_full_analysis(self.team_data, target)

        # Step 2: Variance decomposition
        decompositions = {}
        for target in EVOLUTION_TARGETS:
            decompositions[target] = self.model_framework.compute_variance_decomposition(target)
        self.results['decompositions'] = decompositions

        # Step 3: Natural experiments
        experiment_analyzer = NaturalExperimentAnalyzer(
            self.team_data, self.manager_history, self.transfer_history
        )
        manager_experiments = experiment_analyzer.find_manager_change_experiments()
        player_experiments = experiment_analyzer.find_star_player_experiments()

        # Analyze each experiment
        for exp in manager_experiments + player_experiments:
            experiment_analyzer.analyze_difference_in_differences(exp)

        self.results['experiments'] = {
            'manager_changes': manager_experiments,
            'player_transfers': player_experiments
        }

        # Step 4: Generate report
        interpreter = EvolutionInterpreter(decompositions, {})
        self.results['report'] = interpreter.generate_full_report()

        return self.results


# ============================================================================
# SQL QUERIES FOR ANALYSIS
# ============================================================================

VARIANCE_DECOMPOSITION_QUERY = """
-- Prepare analysis dataset joining skill and tactical features
WITH analysis_data AS (
    SELECT
        ts.team_id,
        ts.season_id,
        -- Skill features (from squad skill table)
        ss.squad_pass_accuracy,
        ss.squad_dribble_success,
        ss.squad_xg_per_90,
        ss.squad_tackle_success,
        ss.squad_aerial_win_rate,
        ss.xg_concentration,
        ss.avg_age,
        -- Tactical features (from tactics table)
        tt.centralization_index,
        tt.avg_defensive_line,
        tt.avg_attacking_line,
        tt.vertical_compactness,
        tt.press_zone_attacking,
        tt.gk_short_pct_avg,
        -- Evolution targets
        ts.ppda_avg,
        ts.possession_avg,
        ts.xg_per_shot_avg,
        ts.transition_attack_rate
    FROM f_team_season_style ts
    JOIN f_squad_season_skill ss ON ts.team_id = ss.team_id AND ts.season_id = ss.season_id
    JOIN f_team_season_tactics tt ON ts.team_id = tt.team_id AND ts.season_id = tt.season_id
    WHERE ts.matches_played >= 10  -- Minimum sample size
)
SELECT * FROM analysis_data
ORDER BY season_id, team_id;
"""

MANAGER_CHANGE_EXPERIMENT_QUERY = """
-- Find manager changes with squad stability
WITH manager_changes AS (
    SELECT
        tmh.team_id,
        tmh.manager_id,
        tmh.start_date,
        tmh.end_date,
        dm.manager_name,
        LAG(tmh.manager_id) OVER (PARTITION BY tmh.team_id ORDER BY tmh.start_date) as prev_manager
    FROM team_manager_history tmh
    JOIN dim_manager dm ON tmh.manager_id = dm.manager_id
    WHERE tmh.is_interim = FALSE
),
squad_continuity AS (
    -- Calculate squad overlap before/after change
    SELECT
        mc.team_id,
        mc.start_date as change_date,
        COUNT(DISTINCT CASE WHEN l1.player_id IS NOT NULL AND l2.player_id IS NOT NULL THEN l1.player_id END) * 1.0 /
        NULLIF(COUNT(DISTINCT l1.player_id), 0) as continuity_rate
    FROM manager_changes mc
    JOIN fact_lineup l1 ON l1.team_id = mc.team_id AND l1.match_date < mc.start_date
    JOIN fact_lineup l2 ON l2.team_id = mc.team_id AND l2.match_date > mc.start_date
        AND l1.player_id = l2.player_id
    GROUP BY mc.team_id, mc.start_date
)
SELECT
    mc.*,
    sc.continuity_rate
FROM manager_changes mc
JOIN squad_continuity sc ON mc.team_id = sc.team_id AND mc.start_date = sc.change_date
WHERE sc.continuity_rate >= 0.8  -- At least 80% squad continuity
ORDER BY mc.start_date;
"""
