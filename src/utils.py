"""
Shared utility functions for the football evolution analysis system.
"""

import json
from typing import Any, Dict


def parse_extra_data(extra_data: Any) -> Dict[str, Any]:
    """
    Parse extra_data field from event records.

    Handles both string JSON and dict formats consistently.

    Args:
        extra_data: Either a JSON string or dict from event record

    Returns:
        Parsed dictionary, or empty dict if parsing fails
    """
    if extra_data is None:
        return {}

    if isinstance(extra_data, dict):
        return extra_data

    if isinstance(extra_data, str):
        try:
            return json.loads(extra_data)
        except (json.JSONDecodeError, TypeError):
            return {}

    return {}


def classify_team_style(ppda: float = 0.0,
                        high_press_pct: float = 0.0,
                        possession: float = 0.0,
                        transition_attack_rate: float = 0.0,
                        defensive_line_height: float = 50.0) -> str:
    """
    Classify a team's primary playing style.

    Args:
        ppda: Passes per defensive action (lower = more pressing)
        high_press_pct: Percentage of pressures in attacking third
        possession: Average possession percentage
        transition_attack_rate: Rate of transition attacks
        defensive_line_height: Average defensive line height (0-100)

    Returns:
        String description of team's style
    """
    if ppda < 8 and high_press_pct > 40:
        return "high-pressing, intense"
    elif possession > 55:
        return "possession-dominant"
    elif transition_attack_rate > 15:
        return "counter-attacking"
    elif defensive_line_height < 40:
        return "deep-block defensive"
    else:
        return "balanced"


def normalize_coordinates(x: float, y: float,
                          source_width: float = 120.0,
                          source_height: float = 80.0,
                          target_scale: float = 100.0) -> tuple[float, float]:
    """
    Normalize coordinates to a standard scale.

    Args:
        x: X coordinate in source system
        y: Y coordinate in source system
        source_width: Width of source coordinate system
        source_height: Height of source coordinate system
        target_scale: Target scale (0 to target_scale)

    Returns:
        Tuple of (normalized_x, normalized_y)
    """
    norm_x = (x / source_width) * target_scale if source_width else 0
    norm_y = (y / source_height) * target_scale if source_height else 0
    return norm_x, norm_y


def calculate_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    """
    Calculate Euclidean distance between two points.

    Args:
        x1, y1: First point coordinates
        x2, y2: Second point coordinates

    Returns:
        Distance between the points
    """
    return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5


def weighted_average(values: list[float], weights: list[float]) -> float:
    """
    Calculate weighted average of values.

    Args:
        values: List of values to average
        weights: List of weights (e.g., minutes played)

    Returns:
        Weighted average, or 0 if no valid data
    """
    if not values or not weights:
        return 0.0

    total_weight = sum(weights)
    if total_weight == 0:
        return 0.0

    return sum(v * w for v, w in zip(values, weights)) / total_weight
