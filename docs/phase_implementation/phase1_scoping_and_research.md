# Phase 1 – Scoping & Research Design

This document explains how Phase 1 of the research framework is structured in this repo: the objectives, core ideas, and how they are captured in documentation and code.

---

## 1. Objectives

- **Clarify the central research question**:
  - Primary: *What drives football evolution more — improvements in player skills or tactical setups?*
  - Secondary: how to quantify evolution, how to represent skill vs tactics, and how to design natural experiments.
- **Define evolution metrics** that will later be computed from event and tracking data.
- **Specify feature families** for player skills and tactical setup.
- **Lay out era segmentation** so later analyses can compare trends over time.
- **Design the causal framework** (model classes and natural experiments) to separate skill vs tactics contributions.

These objectives live primarily in documentation in Phase 1; Phase 2+ then implement the data and computation layers needed to operationalize them.

---

## 2. Conceptual Structure

Phase 1 is captured mainly in `docs/research_framework.md` and the high‑level README. The structure is:

1. **Research Question (Section 1)**
   - Precise articulation of primary and secondary questions.
2. **Evolution Metrics (Section 2)**
   - Table of metrics (PPDA, xG/shot, possession %, build‑up score, press %, transition speed, vertical compactness, width utilization), each with:
     - Natural language definition.
     - Formula sketch.
     - Category (tactical vs attacking quality vs control).
3. **Player-Skill Features (Section 3)**
   - Grouped into technical, physical/intensity, defensive, attacking.
   - Defines the *space* of per‑player features we will engineer from events and tracking.
4. **Tactical Features (Section 4)**
   - Formation & shape, pressing profile, build‑up structure, chance creation, network metrics.
   - Each group lists concrete quantities (e.g. PPDA, GK build‑up rate, CB split width, centralization index).
5. **Era Segmentation (Section 5)**
   - Four eras (Pre‑Analytics, Barcelona Revolution, Pressing Renaissance, Hybrid Era) with years, dominant trends, and tactical shifts.
6. **Model Comparison Framework (Section 6)**
   - Three model types: skill‑only, tactics‑only, combined.
   - Variance decomposition formula for $R^2$ into skill, tactics, interaction components.
7. **Natural Experiments (Section 7)**
   - Design patterns for manager changes, star player moves, and tactical shifts.
8. **Competitions & Seasons (Section 8)**
   - Target competitions (Premier League, La Liga, Bundesliga, UCL) and years (2010–2024).
9. **Statistical Methods (Section 9)**
   - Causal inference (DiD, RD, IV), feature importance (SHAP, permutation, group‑wise), and evaluation (R², MAE/RMSE, CV).

Taken together, these pieces define *what we want to measure* and *how we intend to argue* about evolution before writing substantial code.

---

## 3. Mapping Concepts to Implementation

### 3.1. Where Phase 1 Lives in the Repo

- **Primary design doc**: `docs/research_framework.md` (you’re viewing an excerpt above).
- **High‑level project framing**: `README.md`:
  - Introduces the problem of football evolution and the player‑vs‑tactics lens.
  - Describes the overall architecture (ingestion → features → models → matchup engine → viz).

Phase 1 is intentionally documentation‑heavy; no dedicated `phase1` Python module exists. Instead, its ideas drive the design of later layers:

- **Evolution metrics** drive what we need from facts and features:
  - PPDA, possession %, build‑up score, etc. imply counts and rates over **events**, **pressures**, **passes**, and **recoveries** — motivating the `RawEvent` → `StgEvent` → `FactEvent` path and many of the transformations in `src/features/engineering.py`.
- **Player‑skill features** inform how we structure per‑player aggregates in the feature engine.
- **Tactical features** influence how we aggregate by team, formation, and phases of play.
- **Era segmentation** influences time windows and labeling in downstream analysis.
- **Model comparison & natural experiments** shape how `variance_decomposition.py` and future analysis notebooks will be structured.

### 3.2. Early Code Touchpoints

Even in Phase 1, some stubs and modules are created with the research framework in mind:

- `src/analysis/variance_decomposition.py`:
  - Currently mostly a skeleton, but conceptually aligned with Section 6’s variance decomposition.
- `src/features/engineering.py`:
  - Houses feature builders (e.g., progressive passes/carries, pressures, xG contributions) that map almost 1:1 to the feature lists in Sections 3–4.
- `src/matchup/matchup_engine.py`:
  - Encodes the matchup‑level comparison logic that will later answer “how does this tactical setup perform versus that player profile?”

These are more fully realized in later phases, but their structure traces directly back to the Phase 1 document.

---

## 4. Implementation Process & Decisions

Although Phase 1 is mostly conceptual, there were concrete process decisions:

1. **Front‑loading the research doc**
   - The `research_framework.md` was written first to anchor all subsequent engineering decisions.
   - This doc uses tables and bullet lists to ensure every metric/feature has a clear informal definition before any SQL/Python is written.

2. **Backwards design from metrics**
   - Starting from metrics like PPDA and transition speed, we worked backwards to:
     - What raw events we need (pressures, passes, recoveries, carries, shots).
     - What pitch coordinate normalization is required (e.g. 0–100 scale for events).
     - How matches, events, and players must be linked.
   - This informs the schema in `src/ingestion/schemas.py` and the transformations in `src/ingestion/pipeline.py`.

3. **Clear separation of skill vs tactics features**
   - Features are grouped explicitly into **skill** and **tactics** in the doc, which later allows:
     - Block‑wise feature selection in modeling (skill block vs tactics block).
     - Group‑wise importance and variance decomposition.

4. **Era and competition choices as constraints**
   - Choosing 2010–2024 and specific top‑five‑style competitions constrains:
     - The StatsBomb open‑data coverage we rely on.
     - The volume of data we must ingest in Phase 2.
     - How we handle club/manager histories in `DimTeam`, `DimManager`, and history tables.

5. **Causal framing baked in from the start**
   - By writing down natural experiments early, the data model includes:
     - Manager histories (`TeamManagerHistory`).
     - Player transfers (`PlayerTransferHistory`).
   - This avoids having to retrofit relational structures later when we perform DiD/RD analyses.

---

## 5. How to Use Phase 1 in Later Work

When working on later phases (2–8), Phase 1 serves as your *design contract*:

- When adding or modifying features in `src/features/engineering.py`, check whether they align with the feature lists in Sections 3 and 4.
- When building analysis notebooks or scripts, use the evolution metrics table from Section 2 to name and interpret outputs consistently.
- When designing experiments (e.g., manager changes), refer back to Section 7 to keep the causal setup coherent.
- When expanding competitions or eras, update both:
  - The ingestion configuration (which competitions/seasons to pull).
  - The `Competitions & Seasons` table in this doc.

Phase 1 is “done” when the conceptual map is stable enough that it rarely changes even as we iterate on implementation details. The current repo state reflects that: the research framework is rich and drives the structure of the ingestion, feature, and analysis modules that follow.
