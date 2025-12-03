# Phase 3: Feature Engineering Schemas

This document captures the working schema for the core feature grains that will power the Phase 3 analysis (skill vs tactical contributions) and later modeling phases.

---

## 1. Feature Grains

| Grain | Natural Key | Typical Usage |
|-------|-------------|----------------|
| `PlayerMatchFeature` | `(source, competition_id, season_id, match_id, team_source_id, player_source_id)` | Player-skill metrics per appearance; feeds skill-only models and player trend dashboards |
| `TeamMatchFeature` | `(source, competition_id, season_id, match_id, team_source_id)` | Tactical metrics per team per match; feeds tactic-only models, PPDA tracking |
| `TeamEraFeature` | `(source, competition_id, era_label, team_source_id)` | Aggregated tactical signatures by era (Pre-Analytics, Barcelona Revolution, etc.) |
| `PlayerEraFeature` | `(source, competition_id, era_label, player_source_id)` | High-level player skill evolution across eras |

---

## 2. PlayerMatchFeature Schema (Skill Block)

| Column | Type | Description / Formula | Source Tables |
|--------|------|-----------------------|---------------|
| `minutes_played` | FLOAT | Derived from substitutions + lineup; default 90 if full match | `StgEvent`, `FactMatch` |
| `touches` | INT | Count of on-ball events (pass, carry, shot, duel with possession) | `StgEvent` |
| `progressive_carries` | INT | Carries advancing ≥10 yards towards goal | `StgEvent` (Carry) |
| `progressive_passes` | INT | Passes advancing ≥10 yards towards goal | `StgEvent` (Pass) |
| `progressive_actions_per90` | FLOAT | `(progressive_carries + progressive_passes) / (minutes_played / 90)` | derived |
| `pass_completion_pct` | FLOAT | `completed_passes / attempted_passes` | `StgEvent` (Pass) |
| `dribble_success_pct` | FLOAT | `successful_dribbles / total_dribbles` | `StgEvent` (Dribble) |
| `touch_quality` | FLOAT | `dispossessions / touches` | `StgEvent` |
| `pressure_actions_per90` | FLOAT | `pressures / (minutes_played / 90)` | `StgEvent` (Pressure) |
| `sprints_per90` | FLOAT | Proxy using high-speed carries (>7 m/s) or pressure tag | `StgEvent` |
| `tackles_won_per90` | FLOAT | Successful tackles normalized by minutes | `StgEvent` (Duel/Defensive) |
| `interceptions_per90` | FLOAT | Interceptions normalized | `StgEvent` (Interception) |
| `ball_recoveries_per90` | FLOAT | | `StgEvent` (Ball Recovery) |
| `xg` | FLOAT | Sum of StatsBomb `shot.statsbomb_xg` | `StgEvent` (Shot) |
| `xa` | FLOAT | Sum of pass xAssist (if available) else expected assists proxy | `StgEvent` |
| `xg_xa_per90` | FLOAT | `(xg + xa) / (minutes_played / 90)` | derived |
| `shot_creation_actions` | INT | Key pass + successful dribble leading to shot | event joins |
| `final_third_entries` | INT | Carries or passes entering final third | `StgEvent` (Carry/Pass) |
| `aerial_duel_win_pct` | FLOAT | `won_aerials / aerial_attempts` | `StgEvent` (Duel aerial) |
| `pressure_regains` | INT | Pressures leading to regain within 5s | sequence logic |

---

## 3. TeamMatchFeature Schema (Tactic Block)

| Column | Type | Description / Formula | Source Tables |
|--------|------|-----------------------|---------------|
| `possessions` | INT | Number of discrete possessions | derived from `StgEvent` |
| `ppda` | FLOAT | `opponent_passes_in_final_third / (def_actions)` | `StgEvent` |
| `ppda_final_third` | FLOAT | PPDA restricted to final third | `StgEvent` |
| `high_press_pct` | FLOAT | `% of pressures in final third` | `StgEvent` (Pressure + pitch bins) |
| `press_regain_time_sec` | FLOAT | Avg seconds to regain after losing possession | event sequences |
| `press_triggers_per_match` | INT | Number of defined press triggers | heuristics |
| `build_up_pass_share` | FLOAT | `% passes originating own third leading to opponent half within 10s` | `StgEvent` |
| `gk_short_build_rate` | FLOAT | `% of goal kicks short (<25m)` | `StgEvent` |
| `cb_split_width` | FLOAT | Avg distance between CBs during GK distribution (needs tracking) | location stats |
| `pivot_involvement_pct` | FLOAT | `% build-up touches by DM/pivot roles` | `StgEvent` + lineup roles |
| `vertical_compactness` | FLOAT | `attacking_line_y - defensive_line_y` (avg) | location features |
| `line_height_def` | FLOAT | Average defensive line y-coordinate | event positions |
| `line_height_att` | FLOAT | Average attacking line y-coordinate | event positions |
| `transition_speed_sec` | FLOAT | Avg time to reach final third after recovery | sequences |
| `width_utilization_pct` | FLOAT | `% passes occurring in wide lanes` | `StgEvent` |
| `cross_rate` | FLOAT | Crosses per possession | `StgEvent` (Pass.cross) |
| `central_overload_rate` | FLOAT | Central channel passes per possession | `StgEvent` |
| `through_ball_rate` | FLOAT | Through balls per attacking possession | `StgEvent` |
| `set_piece_xg_share` | FLOAT | `xg from set pieces / total xg` | `StgEvent` |
| `passing_network_centralization` | FLOAT | Degree centralization of pass graph | aggregated network |
| `passing_clustering_coeff` | FLOAT | Avg clustering of pass network | |
| `passing_asymmetry` | FLOAT | | `left_side_passes - right_side_passes` ratio |
| `match_outcome` | STRING | Win/Draw/Loss from `FactMatch` | `FactMatch` |

---

## 4. Era Aggregates

Era-level tables reuse the same columns but aggregated across the relevant seasons:

- `TeamEraFeature`: same columns as `TeamMatchFeature` plus `matches_played`, `era_label`, `seasons_covered`, `avg_ppda`, `std_ppda`, etc.
- `PlayerEraFeature`: aggregated skill metrics with `appearances`, `minutes_total`, `progressive_actions_per90`, etc.

---

## 5. Target Blocks for Phase 4 Modeling

| Block | Features | Notes |
|-------|----------|-------|
| `skill_features` | Subset of `PlayerMatchFeature` columns (progressions, duels, xG/xA, defensive metrics) keyed by `(team, player, match)` | Feed `M_skill` |
| `tactic_features` | `TeamMatchFeature` columns (PPDA, pressing, build-up, network) keyed by `(team, match)` | Feed `M_tactic` |
| `combined_features` | Joined matrix where each row is `(team, match)` with aggregated player skill stats + team tactics | Feed `M_combined` |

---

## 6. Implementation Notes

- All builders will live in `src/features/engineering.py` with pure functions returning Pandas DataFrames keyed by the grains above.
- StatsBomb pitch coordinates will be normalized (0-100) using existing staging logic.
- Where StatsBomb data lacks explicit attributes (e.g., sprint counts), metrics will use event-derived proxies with clear docstrings.
- Feature store helpers will accept filters (`competitions`, `seasons`, `teams`, `players`, `era_label`) to streamline Phase 4 pipelines.

This schema is intentionally opinionated but covers every metric listed in Phase 1. Adjustments/new columns can be appended as needed while engineering the calculations.
