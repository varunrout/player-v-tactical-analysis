"""
FastAPI Application for Football Evolution Analysis

Provides REST API endpoints for:
- Team evolution analysis
- Style forecasting
- Matchup predictions
"""

from typing import Dict, List, Any, Optional
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime, timezone


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class TeamProfileResponse(BaseModel):
    """Team style profile response."""
    team_id: int
    team_name: str
    season: str
    ppda: float = Field(..., description="Passes per defensive action (pressing intensity)")
    possession: float = Field(..., description="Average possession percentage")
    high_press_pct: float = Field(..., description="Percentage of pressures in attacking third")
    xg_per_match: float = Field(..., description="Expected goals per match")
    xg_per_shot: float = Field(..., description="Expected goals per shot (shot quality)")
    progressive_passes: float = Field(..., description="Progressive passes per match")
    transition_rate: float = Field(..., description="Transition attack rate")
    defensive_line: float = Field(..., description="Average defensive line height")
    width_index: float = Field(..., description="Width utilization index")
    style_classification: str = Field(..., description="Overall style classification")


class EvolutionDataPoint(BaseModel):
    """Single season evolution data point."""
    season: str
    ppda: float
    possession: float
    xg_per_shot: float
    high_press_pct: float
    progressive_passes: float


class EvolutionResponse(BaseModel):
    """Team evolution over time response."""
    team_id: int
    team_name: str
    current_season: TeamProfileResponse
    evolution_history: List[EvolutionDataPoint]
    era: str = Field(..., description="Current tactical era")
    key_evolution_insights: List[str]


class ForecastPrediction(BaseModel):
    """Single metric forecast."""
    predicted_value: float
    lower_bound: float = Field(..., description="Lower 90% confidence bound")
    upper_bound: float = Field(..., description="Upper 90% confidence bound")


class ForecastResponse(BaseModel):
    """Team forecast response."""
    team_id: int
    team_name: str
    target_season: str
    forecast_date: datetime
    predictions: Dict[str, ForecastPrediction]
    key_drivers: List[Dict[str, float]]
    model_version: str
    confidence_level: str


class MatchupTeamSummary(BaseModel):
    """Team summary for matchup."""
    team_id: int
    team_name: str
    style: str
    key_strengths: List[str]


class PredictionProbabilities(BaseModel):
    """Match outcome probabilities."""
    team_a_win: float
    draw: float
    team_b_win: float


class ExpectedGoals(BaseModel):
    """Expected goals for each team."""
    team_a: float
    team_b: float


class MatchupPrediction(BaseModel):
    """Match prediction details."""
    expected_goals: ExpectedGoals
    probabilities: PredictionProbabilities
    likely_score: List[int]
    over_2_5_prob: float
    btts_prob: float


class TacticalAnalysis(BaseModel):
    """Tactical analysis of matchup."""
    clash_summary: str
    key_battles: List[str]
    team_a_advantages: List[str]
    team_b_advantages: List[str]
    prediction_rationale: str


class MatchupResponse(BaseModel):
    """Complete matchup analysis response."""
    team_a: MatchupTeamSummary
    team_b: MatchupTeamSummary
    prediction: MatchupPrediction
    tactical_analysis: TacticalAnalysis
    confidence: float


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    timestamp: datetime


# ============================================================================
# API APPLICATION
# ============================================================================

app = FastAPI(
    title="Football Evolution Analysis API",
    description="""
    API for analyzing football evolution through the lens of player skills vs tactical setups.

    ## Features

    - **Evolution Analysis**: Track how team styles evolve over time
    - **Forecasting**: Predict future team tactical profiles
    - **Matchup Engine**: Simulate how two teams' styles clash

    ## Research Question

    What drives football evolution more — improvements in player skills or tactical setups?
    """,
    version="1.0.0",
    contact={
        "name": "Football Analytics Team",
    },
    license_info={
        "name": "MIT",
    }
)


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/", response_model=HealthResponse)
async def root():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.now(timezone.utc)
    )


@app.get("/evolution/{team_id}", response_model=EvolutionResponse)
async def get_team_evolution(
    team_id: int,
    seasons: int = Query(5, ge=1, le=15, description="Number of seasons to include"),
    include_era_analysis: bool = Query(True, description="Include era comparison")
):
    """
    Get evolution analysis for a team.

    Returns:
    - Current season profile
    - Historical evolution data
    - Key insights about style changes
    - Era classification

    Example insights:
    - "PPDA decreased by 15% since 2020, indicating more intense pressing"
    - "Possession increased from 52% to 58% under current manager"
    """
    # Placeholder - would query actual database
    # In production: team_data = db.get_team_evolution(team_id, seasons)

    sample_history = [
        EvolutionDataPoint(
            season="2023/24",
            ppda=9.5,
            possession=58.2,
            xg_per_shot=0.12,
            high_press_pct=42.0,
            progressive_passes=55.3
        ),
        EvolutionDataPoint(
            season="2022/23",
            ppda=10.2,
            possession=56.8,
            xg_per_shot=0.11,
            high_press_pct=38.5,
            progressive_passes=52.1
        ),
    ]

    current = TeamProfileResponse(
        team_id=team_id,
        team_name="Sample Team",
        season="2023/24",
        ppda=9.5,
        possession=58.2,
        high_press_pct=42.0,
        xg_per_match=1.85,
        xg_per_shot=0.12,
        progressive_passes=55.3,
        transition_rate=12.5,
        defensive_line=45.2,
        width_index=22.5,
        style_classification="possession-dominant"
    )

    return EvolutionResponse(
        team_id=team_id,
        team_name="Sample Team",
        current_season=current,
        evolution_history=sample_history,
        era="Hybrid Era (2019-Present)",
        key_evolution_insights=[
            "Pressing intensity increased by 7% over the last 3 seasons",
            "Transition attack rate stable despite tactical changes",
            "xG per shot improved, indicating better chance creation"
        ]
    )


@app.get("/forecast/{team_id}", response_model=ForecastResponse)
async def get_team_forecast(
    team_id: int,
    target_season: Optional[str] = Query(None, description="Season to forecast (default: next)"),
    include_skill_factors: bool = Query(True, description="Include skill feature contributions"),
    include_tactical_factors: bool = Query(True, description="Include tactical feature contributions")
):
    """
    Get style forecast for a team.

    Predicts future tactical profile based on:
    - Current style trajectory
    - Squad composition changes
    - Manager stability
    - Historical patterns

    Returns predictions with confidence intervals.
    """
    # Placeholder forecast
    predictions = {
        "ppda": ForecastPrediction(
            predicted_value=9.2,
            lower_bound=8.5,
            upper_bound=10.1
        ),
        "possession": ForecastPrediction(
            predicted_value=59.5,
            lower_bound=56.0,
            upper_bound=62.0
        ),
        "xg_per_shot": ForecastPrediction(
            predicted_value=0.13,
            lower_bound=0.11,
            upper_bound=0.15
        ),
        "high_press_pct": ForecastPrediction(
            predicted_value=44.0,
            lower_bound=40.0,
            upper_bound=48.0
        )
    }

    key_drivers = [
        {"manager_tenure": 0.25},
        {"squad_pass_accuracy": 0.18},
        {"current_ppda": 0.15},
        {"progressive_passes_trend": 0.12}
    ]

    return ForecastResponse(
        team_id=team_id,
        team_name="Sample Team",
        target_season=target_season or "2024/25",
        forecast_date=datetime.now(timezone.utc),
        predictions=predictions,
        key_drivers=key_drivers,
        model_version="v1.2.3",
        confidence_level="high"
    )


@app.get("/matchup/{team_a_id}/{team_b_id}", response_model=MatchupResponse)
async def get_matchup_analysis(
    team_a_id: int,
    team_b_id: int,
    team_a_home: bool = Query(True, description="Is team A playing at home?"),
    include_narrative: bool = Query(True, description="Include tactical narrative")
):
    """
    Get matchup analysis between two teams.

    Analyzes how the teams' styles will clash:
    - Pressing vs buildup
    - Width vs compactness
    - Transition vulnerabilities
    - Set piece threats

    Returns:
    - Win/draw/loss probabilities
    - Expected goals
    - Likely scoreline
    - Tactical narrative
    """
    team_a = MatchupTeamSummary(
        team_id=team_a_id,
        team_name="Team A",
        style="High-pressing, intense",
        key_strengths=[
            "Elite pressing intensity (PPDA: 8.2)",
            "Strong in transitions",
            "Aerial dominance"
        ]
    )

    team_b = MatchupTeamSummary(
        team_id=team_b_id,
        team_name="Team B",
        style="Possession-dominant",
        key_strengths=[
            "Patient buildup play",
            "High shot quality (xG/shot: 0.14)",
            "Wide overloads"
        ]
    )

    prediction = MatchupPrediction(
        expected_goals=ExpectedGoals(team_a=1.65, team_b=1.42),
        probabilities=PredictionProbabilities(
            team_a_win=0.42,
            draw=0.28,
            team_b_win=0.30
        ),
        likely_score=[1, 1],
        over_2_5_prob=0.52,
        btts_prob=0.58
    )

    tactical = TacticalAnalysis(
        clash_summary=(
            "This match features a clash between Team A's high-pressing, "
            "intense approach and Team B's possession-dominant style. "
            "Expect a contested midfield battle."
        ),
        key_battles=[
            "Team A's high press will test Team B's buildup play",
            "Team B's wide overloads will target Team A's narrow block",
            "Team A's high line leaves space for Team B's counters"
        ],
        team_a_advantages=[
            "Superior pressing intensity",
            "Aerial dominance",
            "Home advantage"
        ],
        team_b_advantages=[
            "Better shot quality",
            "More patient buildup",
            "Counter-attacking threat"
        ],
        prediction_rationale=(
            "Team A is slightly favored (42% win probability) due to home advantage "
            "and pressing intensity. However, Team B's quality in possession "
            "makes this a tight contest. Most likely scoreline: 1-1."
        )
    )

    return MatchupResponse(
        team_a=team_a,
        team_b=team_b,
        prediction=prediction,
        tactical_analysis=tactical,
        confidence=0.72
    )


@app.get("/teams", response_model=List[Dict[str, Any]])
async def list_teams(
    competition: Optional[str] = Query(None, description="Filter by competition"),
    season: Optional[str] = Query(None, description="Filter by season"),
    limit: int = Query(50, ge=1, le=100)
):
    """List available teams."""
    # Placeholder
    return [
        {"team_id": 1, "team_name": "Team 1", "competition": "Premier League"},
        {"team_id": 2, "team_name": "Team 2", "competition": "Premier League"},
    ]


@app.get("/variance-decomposition", response_model=Dict[str, Any])
async def get_variance_decomposition(
    target: str = Query("ppda_avg", description="Evolution metric to analyze"),
    competition: Optional[str] = Query(None, description="Filter by competition"),
    era: Optional[str] = Query(None, description="Filter by era")
):
    """
    Get variance decomposition analysis.

    Shows how much of the target metric's evolution is explained by:
    - Player skill factors
    - Tactical setup factors
    - Interaction effects

    This answers the core research question.
    """
    return {
        "target": target,
        "total_r2": 0.72,
        "skill_contribution": {
            "r2": 0.35,
            "percentage": 48.6,
            "top_features": [
                {"feature": "squad_pass_accuracy", "importance": 0.12},
                {"feature": "squad_dribble_success", "importance": 0.08},
                {"feature": "squad_xg_per_90", "importance": 0.07}
            ]
        },
        "tactics_contribution": {
            "r2": 0.28,
            "percentage": 38.9,
            "top_features": [
                {"feature": "pressing_zone_attacking", "importance": 0.10},
                {"feature": "defensive_line_height", "importance": 0.08},
                {"feature": "centralization_index", "importance": 0.05}
            ]
        },
        "interaction": {
            "r2": 0.09,
            "percentage": 12.5
        },
        "interpretation": (
            f"For {target}, player skills explain 48.6% of the variance, "
            "tactical setup explains 38.9%, with 12.5% from interactions. "
            "This suggests both factors are important, with skills having "
            "a slight edge in explaining pressing intensity changes."
        )
    }


@app.get("/natural-experiments", response_model=Dict[str, Any])
async def get_natural_experiments(
    experiment_type: str = Query(
        "manager_change",
        description="Type: manager_change, star_player, tactical_shift"
    ),
    limit: int = Query(10, ge=1, le=50)
):
    """
    Get natural experiment analysis results.

    Natural experiments help establish causal relationships:
    - Manager changes with stable squad → isolate tactical effects
    - Star player transfers with stable manager → isolate skill effects
    """
    return {
        "experiment_type": experiment_type,
        "count": 2,
        "experiments": [
            {
                "team": "Sample Team",
                "date": "2022-07-01",
                "type": experiment_type,
                "outcome": "ppda_avg",
                "change": -2.3,
                "effect_size": 0.85,
                "interpretation": (
                    "Manager change led to significant decrease in PPDA, "
                    "indicating more intense pressing under new management."
                )
            }
        ],
        "aggregate_finding": (
            f"Across {experiment_type} experiments, tactical changes account for "
            "approximately 55% of observed style changes when controlling for "
            "squad composition."
        )
    }
