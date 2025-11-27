"""
Visualization Module for Football Evolution Analysis

Provides visualization components for:
- Evolution timeline charts
- Feature importances
- Manager-change case studies
- Pass networks
- Average position maps
- Style clash diagrams
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class ChartConfig:
    """Configuration for chart generation."""
    width: int = 800
    height: int = 500
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    color_scheme: str = "default"
    show_legend: bool = True
    interactive: bool = True


@dataclass
class TimeSeriesData:
    """Data for time series visualization."""
    x_values: List[str]  # Dates/seasons
    y_values: List[float]
    label: str
    color: Optional[str] = None


@dataclass
class BarChartData:
    """Data for bar chart visualization."""
    categories: List[str]
    values: List[float]
    colors: Optional[List[str]] = None


@dataclass
class PassNetworkNode:
    """Node in pass network."""
    player_id: int
    player_name: str
    x_position: float
    y_position: float
    size: float  # Based on pass involvement


@dataclass
class PassNetworkEdge:
    """Edge in pass network."""
    from_player: int
    to_player: int
    weight: float  # Pass count


@dataclass
class PassNetwork:
    """Complete pass network data."""
    team_id: int
    match_id: int
    nodes: List[PassNetworkNode]
    edges: List[PassNetworkEdge]


# ============================================================================
# EVOLUTION TIMELINE CHARTS
# ============================================================================

class EvolutionTimelineGenerator:
    """
    Generate evolution timeline visualizations.

    Creates multi-line charts showing how metrics evolve over seasons.
    """

    def __init__(self, team_season_data: List[Dict]):
        self.data = team_season_data

    def create_metric_timeline(self, team_id: int, metrics: List[str],
                               config: ChartConfig) -> Dict[str, Any]:
        """
        Create timeline chart for selected metrics.

        Returns chart specification (for Plotly/Vega-Lite).

        Plotly Example:
        ```python
        import plotly.graph_objects as go

        fig = go.Figure()
        for metric in metrics:
            seasons = [d['season'] for d in team_data]
            values = [d[metric] for d in team_data]
            fig.add_trace(go.Scatter(
                x=seasons, y=values, mode='lines+markers', name=metric
            ))
        fig.update_layout(title=config.title)
        return fig.to_dict()
        ```
        """
        team_data = [d for d in self.data if d.get('team_id') == team_id]
        team_data.sort(key=lambda x: x.get('season', ''))

        traces = []
        for metric in metrics:
            trace_data = TimeSeriesData(
                x_values=[d.get('season', '') for d in team_data],
                y_values=[d.get(metric, 0) for d in team_data],
                label=metric.replace('_', ' ').title()
            )
            traces.append(trace_data)

        # Return chart specification
        return {
            "type": "line",
            "config": {
                "width": config.width,
                "height": config.height,
                "title": config.title or f"Evolution Timeline - Team {team_id}",
                "x_axis": {"title": "Season"},
                "y_axis": {"title": "Value"},
                "legend": {"show": config.show_legend}
            },
            "data": [
                {
                    "x": t.x_values,
                    "y": t.y_values,
                    "name": t.label,
                    "mode": "lines+markers"
                }
                for t in traces
            ]
        }

    def create_era_comparison_chart(self, team_id: int,
                                    config: ChartConfig) -> Dict[str, Any]:
        """
        Create chart comparing team across eras.

        Shows how team style changed between eras:
        - Pre-Analytics (2000-2006)
        - Barcelona Revolution (2007-2013)
        - Pressing Renaissance (2014-2018)
        - Hybrid Era (2019-Present)
        """
        era_mapping = {
            'Pre-Analytics': (2000, 2006),
            'Barcelona Revolution': (2007, 2013),
            'Pressing Renaissance': (2014, 2018),
            'Hybrid Era': (2019, 2030)
        }

        team_data = [d for d in self.data if d.get('team_id') == team_id]

        era_averages = {}
        for era_name, (start, end) in era_mapping.items():
            era_data = [
                d for d in team_data
                if start <= int(d.get('season', '2000')[:4]) <= end
            ]
            if era_data:
                era_averages[era_name] = {
                    'ppda': sum(d.get('ppda_avg', 0) for d in era_data) / len(era_data),
                    'possession': sum(d.get('possession_avg', 0) for d in era_data) / len(era_data),
                    'xg_per_shot': sum(d.get('xg_per_shot_avg', 0) for d in era_data) / len(era_data)
                }

        return {
            "type": "grouped_bar",
            "config": {
                "width": config.width,
                "height": config.height,
                "title": config.title or f"Era Comparison - Team {team_id}"
            },
            "data": era_averages
        }


# ============================================================================
# FEATURE IMPORTANCE CHARTS
# ============================================================================

class FeatureImportanceVisualizer:
    """
    Visualize feature importances from models.

    Creates bar charts and SHAP summary plots.
    """

    def create_importance_bar_chart(self, importances: Dict[str, float],
                                    top_n: int = 15,
                                    config: ChartConfig) -> Dict[str, Any]:
        """
        Create horizontal bar chart of feature importances.

        Separates skill and tactical features with colors.
        """
        # Sort by importance
        sorted_features = sorted(
            importances.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_n]

        from src.analysis.variance_decomposition import SKILL_FEATURES, TACTICAL_FEATURES

        # Assign colors
        categories = []
        values = []
        colors = []

        for feature, importance in sorted_features:
            categories.append(feature.replace('_', ' ').title())
            values.append(importance)
            if feature in SKILL_FEATURES:
                colors.append('#2ecc71')  # Green for skill
            elif feature in TACTICAL_FEATURES:
                colors.append('#3498db')  # Blue for tactical
            else:
                colors.append('#95a5a6')  # Gray for other

        return {
            "type": "horizontal_bar",
            "config": {
                "width": config.width,
                "height": config.height,
                "title": config.title or "Feature Importances",
                "x_axis": {"title": "Importance"},
                "y_axis": {"title": "Feature"}
            },
            "data": {
                "categories": categories,
                "values": values,
                "colors": colors
            },
            "legend": {
                "items": [
                    {"label": "Skill Features", "color": "#2ecc71"},
                    {"label": "Tactical Features", "color": "#3498db"}
                ]
            }
        }

    def create_group_contribution_chart(self, skill_r2: float, tactics_r2: float,
                                        interaction_r2: float,
                                        config: ChartConfig) -> Dict[str, Any]:
        """
        Create pie/donut chart showing group contributions.

        Shows relative contribution of skill, tactics, and interaction.
        """
        return {
            "type": "donut",
            "config": {
                "width": config.width,
                "height": config.height,
                "title": config.title or "Variance Decomposition"
            },
            "data": {
                "labels": ["Skill Factors", "Tactical Factors", "Interaction"],
                "values": [skill_r2, tactics_r2, interaction_r2],
                "colors": ["#2ecc71", "#3498db", "#9b59b6"]
            }
        }


# ============================================================================
# MANAGER CHANGE CASE STUDY CHARTS
# ============================================================================

class ManagerChangeCaseStudy:
    """
    Generate visualizations for manager change case studies.

    Shows before/after comparison of team style.
    """

    def create_before_after_chart(self, team_id: int, change_date: str,
                                  pre_data: List[Dict], post_data: List[Dict],
                                  metrics: List[str],
                                  config: ChartConfig) -> Dict[str, Any]:
        """
        Create before/after comparison chart for manager change.

        Shows metrics before and after manager change with difference.
        """
        pre_means = {}
        post_means = {}

        for metric in metrics:
            pre_means[metric] = (
                sum(d.get(metric, 0) for d in pre_data) / len(pre_data)
                if pre_data else 0
            )
            post_means[metric] = (
                sum(d.get(metric, 0) for d in post_data) / len(post_data)
                if post_data else 0
            )

        return {
            "type": "grouped_bar",
            "config": {
                "width": config.width,
                "height": config.height,
                "title": config.title or f"Manager Change Impact - Team {team_id}"
            },
            "data": {
                "categories": [m.replace('_', ' ').title() for m in metrics],
                "series": [
                    {
                        "name": "Before Change",
                        "values": [pre_means[m] for m in metrics],
                        "color": "#e74c3c"
                    },
                    {
                        "name": "After Change",
                        "values": [post_means[m] for m in metrics],
                        "color": "#27ae60"
                    }
                ]
            }
        }

    def create_transition_timeline(self, team_id: int, change_date: str,
                                   match_data: List[Dict], metric: str,
                                   config: ChartConfig) -> Dict[str, Any]:
        """
        Create timeline showing metric transition around manager change.

        Highlights the change point with before/after trend lines.
        """
        match_data.sort(key=lambda x: x.get('date', ''))

        dates = [m.get('date', '') for m in match_data]
        values = [m.get(metric, 0) for m in match_data]

        # Find change point index
        change_idx = next(
            (i for i, d in enumerate(dates) if d >= change_date),
            len(dates) // 2
        )

        return {
            "type": "line_with_annotation",
            "config": {
                "width": config.width,
                "height": config.height,
                "title": config.title or f"{metric} Transition"
            },
            "data": {
                "x": dates,
                "y": values,
                "annotations": [
                    {
                        "x": change_date,
                        "text": "Manager Change",
                        "style": "vertical_line"
                    }
                ]
            },
            "trend_lines": {
                "before": {"start": 0, "end": change_idx},
                "after": {"start": change_idx, "end": len(dates)}
            }
        }


# ============================================================================
# PASS NETWORK VISUALIZATION
# ============================================================================

class PassNetworkVisualizer:
    """
    Create pass network visualizations.

    Shows passing patterns between players with:
    - Node size based on involvement
    - Edge width based on pass frequency
    - Player positions on pitch
    """

    def create_pass_network(self, events: List[Dict],
                            lineups: List[Dict],
                            team_id: int,
                            config: ChartConfig) -> Dict[str, Any]:
        """
        Create pass network visualization from event data.

        Steps:
        1. Calculate average positions from events
        2. Count passes between player pairs
        3. Size nodes by pass involvement
        4. Create network specification
        """
        # Get team passes
        passes = [
            e for e in events
            if e.get('event_type') == 'pass'
            and e.get('team_id') == team_id
            and e.get('is_successful')
        ]

        # Calculate player positions and pass counts
        player_positions: Dict[int, List[Tuple[float, float]]] = {}
        player_passes: Dict[int, int] = {}
        pair_counts: Dict[Tuple[int, int], int] = {}

        for p in passes:
            passer = p.get('player_id')
            receiver = p.get('pass_recipient_id')  # Would need to be in data

            if passer:
                if passer not in player_positions:
                    player_positions[passer] = []
                player_positions[passer].append(
                    (p.get('location_x', 50), p.get('location_y', 50))
                )
                player_passes[passer] = player_passes.get(passer, 0) + 1

            if passer and receiver:
                pair = (passer, receiver)
                pair_counts[pair] = pair_counts.get(pair, 0) + 1

        # Create nodes
        nodes = []
        for player_id, positions in player_positions.items():
            avg_x = sum(p[0] for p in positions) / len(positions)
            avg_y = sum(p[1] for p in positions) / len(positions)

            # Get player name from lineups
            player_name = next(
                (l.get('player_name', f'Player {player_id}')
                 for l in lineups if l.get('player_id') == player_id),
                f'Player {player_id}'
            )

            nodes.append({
                "id": player_id,
                "name": player_name,
                "x": avg_x,
                "y": avg_y,
                "size": player_passes.get(player_id, 0)
            })

        # Create edges
        edges = [
            {
                "from": pair[0],
                "to": pair[1],
                "weight": count
            }
            for pair, count in pair_counts.items()
            if count >= 5  # Only show significant connections
        ]

        return {
            "type": "network",
            "config": {
                "width": config.width,
                "height": config.height,
                "title": config.title or "Pass Network",
                "pitch_background": True
            },
            "data": {
                "nodes": nodes,
                "edges": edges
            }
        }


# ============================================================================
# AVERAGE POSITION MAP
# ============================================================================

class PositionMapVisualizer:
    """
    Create average position maps.

    Shows player average positions on pitch.
    """

    def create_position_map(self, events: List[Dict],
                            lineups: List[Dict],
                            team_id: int,
                            config: ChartConfig) -> Dict[str, Any]:
        """
        Create average position map from event data.

        Calculates average x,y position for each player.
        """
        player_positions: Dict[int, List[Tuple[float, float]]] = {}

        # Collect positions from all events
        for event in events:
            if event.get('team_id') != team_id:
                continue

            player_id = event.get('player_id')
            x = event.get('location_x')
            y = event.get('location_y')

            if player_id and x and y:
                if player_id not in player_positions:
                    player_positions[player_id] = []
                player_positions[player_id].append((x, y))

        # Calculate averages
        avg_positions = []
        for player_id, positions in player_positions.items():
            if len(positions) < 10:  # Minimum events
                continue

            avg_x = sum(p[0] for p in positions) / len(positions)
            avg_y = sum(p[1] for p in positions) / len(positions)

            # Get player info from lineups
            player_info = next(
                (l for l in lineups if l.get('player_id') == player_id),
                {}
            )

            avg_positions.append({
                "player_id": player_id,
                "name": player_info.get('player_name', f'Player {player_id}'),
                "position": player_info.get('position', 'Unknown'),
                "jersey_number": player_info.get('jersey_number', 0),
                "avg_x": avg_x,
                "avg_y": avg_y,
                "event_count": len(positions)
            })

        return {
            "type": "position_map",
            "config": {
                "width": config.width,
                "height": config.height,
                "title": config.title or "Average Positions",
                "pitch_background": True
            },
            "data": {
                "positions": avg_positions
            }
        }


# ============================================================================
# SHOT MAP
# ============================================================================

class ShotMapVisualizer:
    """
    Create shot map visualizations.

    Shows shot locations with xG coloring.
    """

    def create_shot_map(self, events: List[Dict],
                        team_id: int,
                        config: ChartConfig) -> Dict[str, Any]:
        """
        Create shot map from event data.

        Each shot shown as circle with:
        - Position on pitch
        - Size based on xG
        - Color based on outcome (goal, saved, missed)
        """
        import json

        shots = [
            e for e in events
            if e.get('event_type') == 'shot' and e.get('team_id') == team_id
        ]

        shot_data = []
        for shot in shots:
            extra = json.loads(shot.get('extra_data', '{}')) if isinstance(shot.get('extra_data'), str) else shot.get('extra_data', {})

            shot_data.append({
                "x": shot.get('location_x', 0),
                "y": shot.get('location_y', 50),
                "xg": extra.get('xg', 0.1),
                "outcome": shot.get('outcome', 'Missed'),
                "player_name": shot.get('player_name', 'Unknown'),
                "minute": shot.get('minute', 0)
            })

        return {
            "type": "shot_map",
            "config": {
                "width": config.width,
                "height": config.height,
                "title": config.title or "Shot Map",
                "pitch_background": True,
                "show_goal": True
            },
            "data": {
                "shots": shot_data
            },
            "color_scheme": {
                "Goal": "#27ae60",
                "Saved": "#f1c40f",
                "Blocked": "#e67e22",
                "Off T": "#e74c3c",
                "Post": "#9b59b6"
            }
        }


# ============================================================================
# STYLE CLASH DIAGRAM
# ============================================================================

class StyleClashVisualizer:
    """
    Create style clash diagrams for matchup analysis.

    Shows how two teams' styles compare across dimensions.
    """

    def create_radar_comparison(self, team_a: Dict, team_b: Dict,
                                metrics: List[str],
                                config: ChartConfig) -> Dict[str, Any]:
        """
        Create radar chart comparing two teams' styles.

        Each metric shown as an axis on the radar.
        """
        return {
            "type": "radar",
            "config": {
                "width": config.width,
                "height": config.height,
                "title": config.title or "Style Comparison"
            },
            "data": {
                "axes": [m.replace('_', ' ').title() for m in metrics],
                "series": [
                    {
                        "name": team_a.get('team_name', 'Team A'),
                        "values": [team_a.get(m, 0) for m in metrics],
                        "color": "#3498db"
                    },
                    {
                        "name": team_b.get('team_name', 'Team B'),
                        "values": [team_b.get(m, 0) for m in metrics],
                        "color": "#e74c3c"
                    }
                ]
            }
        }

    def create_clash_heatmap(self, matchup_features: Dict,
                             config: ChartConfig) -> Dict[str, Any]:
        """
        Create heatmap showing matchup clash intensities.

        Shows which areas of the game favor which team.
        """
        clash_metrics = [
            ('Pressing vs Buildup', matchup_features.get('pressing_vs_buildup_a', 0)),
            ('Width Advantage', matchup_features.get('width_mismatch_a', 0)),
            ('Transition Threat', -matchup_features.get('transition_vulnerability_a', 0)),
            ('xG Force', matchup_features.get('xg_force_a', 0)),
            ('Aerial Dominance', matchup_features.get('aerial_advantage_a', 0))
        ]

        return {
            "type": "diverging_bar",
            "config": {
                "width": config.width,
                "height": config.height,
                "title": config.title or "Matchup Advantages",
                "center": 0
            },
            "data": {
                "categories": [c[0] for c in clash_metrics],
                "values": [c[1] for c in clash_metrics]
            },
            "color_scheme": {
                "positive": "#3498db",  # Team A advantage
                "negative": "#e74c3c"   # Team B advantage
            },
            "labels": {
                "left": "Team B Advantage",
                "right": "Team A Advantage"
            }
        }


# ============================================================================
# DASHBOARD PLAN
# ============================================================================

DASHBOARD_SPECIFICATION = """
# Football Evolution Dashboard Plan

## Pages

### 1. Evolution Overview
- **Header**: Research question and key findings
- **Chart 1**: League-wide evolution timeline (PPDA, possession, xG trends)
- **Chart 2**: Era comparison bar chart
- **Chart 3**: Variance decomposition donut chart
- **Interactive**: Filter by competition, era

### 2. Team Style Explorer
- **Team Selector**: Dropdown to select team
- **Profile Card**: Current season style summary
- **Chart 1**: Team evolution timeline (multi-metric)
- **Chart 2**: Season-by-season radar chart
- **Chart 3**: Manager change impact timeline
- **Interactive**: Compare with league average toggle

### 3. Manager Change Impact
- **Experiment Selector**: Choose manager change case
- **Before/After Cards**: Key metric changes
- **Chart 1**: Transition timeline with change point
- **Chart 2**: Style shift radar
- **Statistical Summary**: Effect sizes and significance

### 4. Matchup Simulator
- **Team A Selector**: Choose first team
- **Team B Selector**: Choose second team
- **Prediction Card**: Win/draw/loss probabilities
- **Chart 1**: Style clash radar
- **Chart 2**: Matchup advantages diverging bar
- **Narrative**: Generated tactical preview

## Components

### Charts
All charts should support:
- Dark/light mode
- Export to PNG/SVG
- Hover tooltips
- Responsive sizing

### Filters
- Competition (Premier League, La Liga, etc.)
- Season range
- Era selection
- Team selection

### Data Refresh
- Daily update for current season
- Historical data static
- Cache for performance

## Technical Stack (Recommended)
- **Framework**: React + TypeScript
- **Charts**: Plotly.js or D3.js
- **State**: React Query for API data
- **Styling**: Tailwind CSS
- **Pitch Visualizations**: Custom SVG or mplsoccer-inspired
"""
