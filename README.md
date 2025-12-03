# Football Evolution: Player Skills vs Tactical Setup

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

An end-to-end analytics system that answers the research question:

> **"What drives football evolution more — improvements in player skills or tactical setups?"**

## 🎯 Research Question

Football has evolved dramatically over the past two decades. This project uses statistical analysis, machine learning, and causal inference to quantify how much of this evolution comes from:

- **Player Skills**: Technical abilities, physical attributes, individual quality
- **Tactical Setups**: Formations, pressing systems, buildup patterns, positional play

## 📊 Key Findings (Sample)

| Evolution Metric | Skill Contribution | Tactics Contribution | Interaction |
|------------------|-------------------|---------------------|-------------|
| PPDA (Pressing) | 35% | 52% | 13% |
| xG per Shot | 48% | 38% | 14% |
| Possession | 42% | 45% | 13% |

*Note: These are illustrative values. Run the analysis with actual data for real results.*

## 🏗️ Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Data Sources   │────▶│  Ingestion      │────▶│  Feature        │
│  (StatsBomb,    │     │  Pipeline       │     │  Engineering    │
│   Wyscout, etc) │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                        ┌───────────────────────────────┘
                        ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Matchup        │◀────│  Analysis &     │────▶│  Forecasting    │
│  Engine         │     │  Decomposition  │     │  Engine         │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                ▼
                        ┌─────────────────┐
                        │  FastAPI        │
                        │  REST API       │
                        └─────────────────┘

## 🧱 Ingestion Pipeline

StatsBomb Open is the primary Phase 2 data source. The ETL stack in `src/ingestion/pipeline.py` currently wires up the following jobs and helpers:

1. `JobIngestMatches` – pulls competition/season match lists into `raw_match`.
2. `JobIngestEvents` – fetches per-match event JSON into `raw_event`.
3. `JobIngestLineups` – captures both team lineups for each match into `raw_lineup`.
4. `JobStageMatches` – normalizes match metadata (team & competition names, matchweek, stage, attendance) into `stg_match`.
5. `JobStageEvents` – standardizes locations, subtypes, outcomes, and derived flags (`progressive`, `under_pressure`, etc.) into `stg_event`.
6. `JobStageEntities` – produces `stg_team`/`stg_player` reference data using match, event, and lineup payloads.
7. Fact loaders:
   - `load_fact_matches_from_staging`
   - `load_fact_events_from_staging`
   - `load_fact_lineups_from_raw`

Run them individually or via `Pipeline.run_full_ingestion`, which strings jobs (1)–(6) together before fact materialization. Lineups and enriched event metadata ensure player dimensions and FactLineup rows stay in sync with StatsBomb IDs.
```

## 📁 Project Structure

```
player-v-tactical-analysis/
├── src/
│   ├── ingestion/          # Data ingestion pipeline
│   │   ├── schemas.py      # Database ORM models
│   │   └── pipeline.py     # ETL jobs
│   ├── features/           # Feature engineering
│   │   └── engineering.py  # Tactical & skill features
│   ├── analysis/           # Evolution analysis
│   │   └── variance_decomposition.py
│   ├── forecasting/        # Style prediction
│   │   └── forecast_engine.py
│   ├── matchup/            # Team vs team analysis
│   │   └── matchup_engine.py
│   ├── visualization/      # Charts and dashboards
│   │   └── charts.py
│   └── api/                # REST API
│       └── main.py
├── data/
│   ├── raw/                # Raw ingested data
│   ├── staging/            # Cleaned staging data
│   └── core/               # Feature tables
├── models/                 # Trained model artifacts
├── docs/                   # Documentation
│   └── research_framework.md
├── tests/                  # Test suite
├── requirements.txt
├── pyproject.toml
└── README.md
```

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/varunrout/player-v-tactical-analysis.git
cd player-v-tactical-analysis

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Or install with development dependencies
pip install -e ".[dev]"
```

### Running the API

```bash
# Start the FastAPI server
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# API documentation available at:
# - Swagger UI: http://localhost:8000/docs
# - ReDoc: http://localhost:8000/redoc
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_features.py
```

## 📡 API Endpoints

### Evolution Analysis
```
GET /evolution/{team_id}
```
Returns team style evolution over seasons with era classification.

### Style Forecasting
```
GET /forecast/{team_id}
```
Predicts future tactical profile based on current trends and squad dynamics.

### Matchup Analysis
```
GET /matchup/{team_a_id}/{team_b_id}
```
Simulates style clash and predicts match outcomes with tactical narrative.

### Variance Decomposition
```
GET /variance-decomposition?target=ppda_avg
```
Shows how much skill vs tactics explains evolution of a metric.

## 📈 Data Model

### Dimension Tables
- `dim_team`: Team master data
- `dim_player`: Player master data
- `dim_manager`: Manager profiles
- `dim_season`: Season definitions with era mapping

### Fact Tables
- `fact_match`: Match-level data and aggregates
- `fact_event`: Event-level data (passes, shots, tackles, etc.)
- `fact_lineup`: Match lineups with positions

### Feature Tables
- `f_team_match_style`: Per-match team style features
- `f_team_season_style`: Season-aggregated evolution metrics
- `f_player_season_profile`: Player skill profiles
- `f_squad_season_skill`: Squad-level skill aggregations
- `f_team_season_tactics`: Tactical structure features

## 🔬 Methodology

### Three-Model Framework

1. **Skill-Only Model (M_skill)**
   - Features: Player technical, physical, defensive, attacking metrics
   - Purpose: Isolate contribution of player abilities

2. **Tactic-Only Model (M_tactic)**
   - Features: Formation, pressing profile, build-up, network metrics
   - Purpose: Isolate contribution of tactical setup

3. **Combined Model (M_combined)**
   - Features: All skill + tactical features
   - Purpose: Full explanatory power

### Variance Decomposition

```
R²_combined = R²_unique_skill + R²_unique_tactics + R²_shared

Where:
- R²_unique_skill = R²_combined - R²_tactic_only
- R²_unique_tactics = R²_combined - R²_skill_only
- R²_shared = remaining interaction variance
```

### Natural Experiments

To establish causal relationships:

1. **Manager Changes**: Same squad, different manager → isolate tactical effects
2. **Star Player Transfers**: Same manager, changed squad → isolate skill effects
3. **Mid-Season Shifts**: Same squad, same manager, tactical change → tactical effects

## 📊 Key Metrics

### Evolution Metrics (Targets)
| Metric | Definition |
|--------|------------|
| PPDA | Passes per defensive action (pressing intensity) |
| xG/Shot | Shot quality metric |
| Possession % | Ball retention |
| High Press % | Attacking third pressures / total pressures |
| Progressive Passes | Passes moving ball 10+ yards toward goal |

### Skill Features
- Squad pass accuracy
- Dribble success rate
- xG per 90 (attacking quality)
- Tackle success rate
- Aerial win rate

### Tactical Features
- Formation flexibility
- Defensive line height
- Centralization index (network metric)
- Pressing zone distribution
- Build-up structure

## 🗓️ Era Segmentation

| Era | Years | Dominant Trends |
|-----|-------|-----------------|
| Pre-Analytics | 2000–2006 | 4-4-2 dominance, direct play |
| Barcelona Revolution | 2007–2013 | Tiki-taka, possession football |
| Pressing Renaissance | 2014–2018 | Gegenpressing, high intensity |
| Hybrid Era | 2019–Present | Positional/pressing hybrid |

## 🛠️ Development

### Code Quality

```bash
# Format code
black src tests

# Sort imports
isort src tests

# Lint
ruff check src tests

# Type check
mypy src
```

### Adding New Features

1. Define feature in `src/features/engineering.py`
2. Add to appropriate feature list in `src/analysis/variance_decomposition.py`
3. Update SQL DDL if database-backed
4. Add tests in `tests/unit/`

## 📚 Documentation

- [Research Framework](docs/research_framework.md) - Detailed methodology
- [API Documentation](http://localhost:8000/docs) - OpenAPI/Swagger (when running)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [StatsBomb](https://statsbomb.com/) for open data
- Football analytics community for methodology inspiration
- Research papers on causal inference in sports analytics

---

**Research Question**: What drives football evolution more — improvements in player skills or tactical setups?

*This project provides a statistical, data-driven answer.*