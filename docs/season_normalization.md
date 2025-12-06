# Season Normalization Implementation

## Overview

Implemented proper football season handling where seasons run from **August to July** the following year. All season names are normalized to `YYYY/YYYY` format (e.g., `2022/2023`).

## Football Season Logic

- **August - December**: Belongs to current year's season (e.g., Sept 2022 → `2022/2023`)
- **January - July**: Belongs to previous year's season (e.g., March 2023 → `2022/2023`)
- **Date ranges**: August 1 to July 31 of next year

## Changes Made

### 1. Utility Functions (`src/utils.py`)

Added two new utility functions:

#### `normalize_season_name(season_str, match_date=None)`
Normalizes any season string to `YYYY/YYYY` format:
- Input: `"2022"` → Output: `"2022/2023"`
- Input: `"2022/2023"` → Output: `"2022/2023"` (unchanged)
- With match_date context: Uses the actual match date to determine correct season

#### `sort_seasons(season_names)`
Sorts season names chronologically:
- Input: `["2022", "2018/2019", "2020"]`
- Output: `["2018/2019", "2020", "2022"]`

### 2. Data Ingestion Pipeline (`src/ingestion/pipeline.py`)

#### Updated `MatchTransformer.load()`
- Normalizes `season_name` before inserting into `StgMatch`
- Uses match date context for accurate normalization
- Ensures all downstream processes receive normalized season names

#### Updated `_get_or_create_dim_season()`
- Now accepts optional `match_date` parameter
- Uses `normalize_season_name()` to ensure consistency
- Sets correct date ranges: **August 1 to July 31**
- Previous implementation used July 1 to June 30 (incorrect for football)

#### Updated Season Dimension Creation
- Modified the call to `_get_or_create_dim_season()` to pass `stg.match_date`
- Ensures DimSeason records have normalized names and correct date ranges

### 3. Notebook Updates (`notebooks/phase3_5_indicator_discovery.ipynb`)

Added cells to normalize existing feature data:
- Imports normalization utilities from `src.utils`
- Applies normalization to loaded CSV data
- Displays before/after comparison of season values
- Ensures all analysis uses consistent season naming

## Testing

Validation tests confirm:

```python
# Single year normalization
normalize_season_name("2022") → "2022/2023"

# Date-based normalization
normalize_season_name("2022", date(2022, 9, 15)) → "2022/2023"  # September
normalize_season_name("2023", date(2023, 3, 20)) → "2022/2023"  # March

# Idempotency
normalize_season_name("2022/2023") → "2022/2023"

# Database integration
_get_or_create_dim_season(session, "2022", date(2022, 9, 1))
_get_or_create_dim_season(session, "2022/2023", date(2022, 9, 1))
_get_or_create_dim_season(session, "2023", date(2023, 1, 15))
# All three return the same season_id ✓
```

## Impact on Existing Data

### Database
- **New ingestion**: All new data will be automatically normalized
- **Existing data**: Run a migration to update `StgMatch.season_name` and `DimSeason.season_name` for consistency

### Feature Files
- Current CSV files have mixed formats (`"2022"`, `"2018"`, `"2022/2023"`)
- Notebook cells handle normalization at load time
- Re-export features to generate files with normalized season names

### Analysis
- Season-based aggregations will now group correctly
- Time-series analysis will have proper chronological ordering
- Cross-season comparisons will use consistent naming

## Migration Path

To fully normalize existing data:

1. **Database Migration**:
   ```python
   # Update existing StgMatch records
   UPDATE stg_match 
   SET season_name = normalize_based_on_match_date(season_name, match_date)
   WHERE season_name NOT LIKE '%/%'
   
   # Update DimSeason records
   # Merge duplicate seasons (e.g., "2022" and "2022/2023")
   ```

2. **Re-export Features**:
   ```bash
   python scripts/export_features.py
   ```

3. **Update Analysis**:
   - Existing notebooks will automatically normalize on data load
   - No code changes needed in analysis logic

## Benefits

1. **Consistency**: All season references use same format
2. **Accuracy**: Matches correctly assigned to their season
3. **Sortability**: Chronological ordering works correctly
4. **Clarity**: `"2022/2023"` is more explicit than `"2022"`
5. **Compatibility**: Aligns with football industry standards

## Examples

### Before
```
Seasons: ['2022', '2018', '2009/2010', '2022/2023', '2020']
```

### After
```
Seasons: ['2009/2010', '2018/2019', '2020/2021', '2022/2023']
```
