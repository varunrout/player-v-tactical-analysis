# Football Evolution: Player Skills vs Tactical Setup
## Research Framework

### 1. Research Question

**Primary Question**: What drives football evolution more — improvements in player skills or tactical setups?

**Secondary Questions**:
- How do we quantify football evolution over time?
- What features best represent player skill vs tactical setup?
- Can we isolate the effect of tactics from player abilities using natural experiments?

---

### 2. Evolution Metrics Definitions

| Metric | Definition | Formula | Category |
|--------|------------|---------|----------|
| **PPDA** | Passes Per Defensive Action (pressing intensity) | `opponent_passes / (tackles + interceptions + fouls)` in opponent's half | Tactical |
| **xG/Shot** | Expected Goals per Shot (shot quality) | `sum(xG) / shots` | Attacking Quality |
| **Possession %** | Ball retention metric | `team_passes / total_passes` | Control |
| **Build-up Score** | Progressive passes in build-up thirds | `progressive_passes_buildup / total_passes` | Tactical |
| **High Press %** | Percentage of pressures in final third | `final_third_pressures / total_pressures` | Tactical |
| **Transition Speed** | Time to reach opponent's third after recovery | `avg_time_to_final_third` in seconds | Tactical |
| **Vertical Compactness** | Distance between defensive and forward lines | `forward_line_y - defensive_line_y` | Tactical |
| **Width Utilization** | Percentage of play in wide zones | `wide_zone_passes / total_passes` | Tactical |

---

### 3. Player-Skill Features

#### Technical Features
- **Progressive Carries**: Carries moving ball 10+ yards toward goal
- **Progressive Passes**: Passes moving ball 10+ yards toward goal
- **Pass Completion %**: Accuracy across different pass types
- **Dribble Success Rate**: Successful dribbles / attempted dribbles
- **Touch Quality**: Dispossessions per touch

#### Physical/Intensity Features
- **Sprint Count**: High-intensity runs per 90 minutes
- **Distance Covered**: Total and high-speed distance
- **Pressure Actions**: Number of pressing events per 90
- **Aerial Duel Win Rate**: Headers won / contested

#### Defensive Features
- **Tackle Success Rate**: Successful tackles / attempted tackles
- **Interception Rate**: Interceptions per 90 in different zones
- **Ball Recoveries**: Recoveries in each third

#### Attacking Features
- **xG Contribution**: xG + xA per 90
- **Shot Creation Actions**: Key passes + successful dribbles leading to shots
- **Final Third Entries**: Carries/passes entering final third

---

### 4. Tactical Features

#### Formation & Shape
- **Formation Code**: e.g., 4-3-3, 3-5-2, 4-2-3-1
- **Dynamic Shape Index**: Shape variance during possession vs defense
- **Line Height (Defensive)**: Average Y-position of defensive line
- **Line Height (Attacking)**: Average Y-position of forward line

#### Pressing Profile
- **PPDA**: Passes allowed per defensive action
- **PPDA Zones**: PPDA broken down by pitch zone
- **Press Trigger Rate**: How often team initiates press
- **Counter-Press Recovery Time**: Time to regain ball after loss

#### Build-up Structure
- **GK Build-up Rate**: Percentage of goal kicks played short
- **CB Split Width**: Average distance between center-backs
- **Deep Progression Rate**: Progression from own third
- **Pivot Involvement**: Midfielder touches in build-up

#### Chance Creation
- **Cross Rate**: Crosses per possession
- **Central Overload Rate**: Passes into central attacking zones
- **Through Ball Rate**: Through balls per attacking possession
- **Set Piece Dependency**: xG from set pieces / total xG

#### Network Metrics
- **Centralization Index**: How much play flows through specific players
- **Average Clustering**: Positional clustering coefficient
- **Passing Asymmetry**: Left vs right side passing balance

---

### 5. Era Segmentation

| Era | Years | Dominant Trends | Key Tactical Shifts |
|-----|-------|-----------------|---------------------|
| **Pre-Analytics** | 2000–2006 | 4-4-2 dominance, direct play | Traditional formations, wing play |
| **Barcelona Revolution** | 2007–2013 | Tiki-taka, possession football | High possession, positional play |
| **Pressing Renaissance** | 2014–2018 | Gegenpressing, high intensity | Counter-pressing, vertical play |
| **Hybrid Era** | 2019–Present | Positional/pressing hybrid | Flexible formations, data-driven |

---

### 6. Research Framework: Model Comparison

#### Model Types

1. **Skill-Only Model (M_skill)**
   - Features: Player technical, physical, defensive, attacking metrics
   - Target: Evolution metrics (PPDA, xG/shot, possession)
   - Purpose: Isolate contribution of player abilities

2. **Tactic-Only Model (M_tactic)**
   - Features: Formation, pressing profile, build-up, network metrics
   - Target: Same evolution metrics
   - Purpose: Isolate contribution of tactical setup

3. **Combined Model (M_combined)**
   - Features: All skill + tactical features
   - Target: Same evolution metrics
   - Purpose: Full explanatory power

#### Variance Decomposition

```
R²_combined = R²_skill + R²_tactics + R²_interaction

Where:
- R²_skill = R²_combined - R²_tactic_only (unique skill contribution)
- R²_tactics = R²_combined - R²_skill_only (unique tactical contribution)
- R²_interaction = R²_combined - R²_skill - R²_tactics (shared/interaction)
```

---

### 7. Natural Experiments

#### Manager Change (Controlled Squad)
- **Setup**: Same squad, different manager
- **Control**: Player skill features (assumed constant)
- **Treatment**: Tactical changes
- **Outcome**: Evolution metric changes
- **Examples**: Guardiola → Bayern, Klopp → Liverpool

#### Star Player Arrival/Departure (Stable Manager)
- **Setup**: Same manager, significant player change
- **Control**: Tactical features (assumed constant)
- **Treatment**: Squad skill changes
- **Outcome**: Evolution metric changes
- **Examples**: Messi → PSG, Ronaldo → Juventus

#### Tactical Shift (Same Squad, Same Manager)
- **Setup**: Manager changes tactical approach mid-season
- **Control**: Squad composition
- **Treatment**: Tactical adjustments
- **Outcome**: Evolution metric changes
- **Examples**: Conte's switch to 3-4-3 at Chelsea

---

### 8. Competitions & Seasons

| Competition | Seasons | Rationale |
|-------------|---------|-----------|
| **Premier League** | 2010–2024 | High data quality, tactical diversity |
| **La Liga** | 2010–2024 | Possession-focused, Barcelona/Real Madrid |
| **Bundesliga** | 2010–2024 | Pressing pioneers, Klopp influence |
| **Champions League** | 2010–2024 | Cross-league tactical clashes |

---

### 9. Statistical Methods

#### Causal Inference Approaches
- **Difference-in-Differences (DiD)**: For manager/player changes
- **Regression Discontinuity (RD)**: For mid-season tactical shifts
- **Instrumental Variables (IV)**: Manager style as instrument for tactics

#### Feature Importance
- **SHAP Values**: Individual feature contributions
- **Permutation Importance**: Feature ablation effects
- **Group-wise Importance**: Skill block vs tactics block contribution

#### Model Evaluation
- **R² Score**: Variance explained
- **MAE / RMSE**: Prediction accuracy
- **Cross-validation**: Time-series aware splits (no future leakage)
