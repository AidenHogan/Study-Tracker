"""
Correlation engine
------------------

This module prepares daily feature matrices and runs several automated
analyses (OLS, Lasso, PCA) to find relationships between study time and
physiological/behavioral variables.

Variables included (if present in the database or computed):
- sleep_score: Sleep quality score from Garmin / manual entries (unitless)
- resting_hr: Resting heart rate (bpm) — may be NULL unless OAuth1-level data is available
- body_battery: Garmin Body Battery (unitless)
- pulse_ox: Avg. SpO2 (percent) — may be NULL unless OAuth1-level data is available
- respiration: Avg. respiration rate (breaths per minute)
- sleep_duration_seconds: Raw sleep duration in seconds (derived column: sleep_duration_hours)
- avg_stress: Average daily stress (Garmin-derived score)

Activity-derived variables (per day):
- running_minutes: Total running duration in minutes
- distance: Sum of activity distances for the day (units as stored in `activities.distance`)
- activity_count: Number of activities logged that day
- breathwork_sessions: Count of breathwork-type activities

Custom factors:
- Any `custom_factors` logged into `custom_factor_log` appear as columns prefixed with `factor_`.

Caveats:
- Many Garmin-derived metrics (resting_hr, pulse_ox, detailed body battery) require OAuth1 access
    to Garmin Connect and will be NULL when the lighter API access is used. The engine will still
    run using available fields.
- All potential feature columns are coerced to numeric (non-numeric values become NaN) and
    a feature must have at least 10 non-null values to be considered for modeling.
- Activity `distance` is used as-provided; convert units if you need a standard unit across records.

If you want a different set of variables included or a UI toggle to control groups
(health/activity/custom factors), I can add that as a follow-up.
"""

import pandas as pd
import statsmodels.api as sm
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.linear_model import LassoCV
from . import database_manager as db


# --- Constants for column names and prefixes ---
TARGET_VARIABLE = 'total_study_minutes'
DAY_OF_WEEK_COL = 'day_of_week'
CUSTOM_FACTOR_PREFIX = 'factor_'
DATE_COL = 'date'
START_TIME_COL = 'start_time'

# List of potential feature columns to look for in DataFrames
POTENTIAL_FEATURE_COLS = [
    'sleep_score', 'avg_stress', 'body_battery', 'sleep_duration_seconds',
    'resting_hr', 'pulse_ox', 'respiration',
    'running_minutes', 'distance', 'activity_count', 'breathwork_sessions',
    'total_activity_minutes', 'total_calories', 'avg_activity_duration_minutes'
]
DAYS_OF_WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def prepare_daily_features(start_date, end_date, where_clause, params):
    """
    Gathers all data sources and engineers them into a daily feature DataFrame.
    """
    date_range = pd.date_range(start=start_date, end=end_date, freq='D')
    df = pd.DataFrame(index=date_range)

    # --- 1. Get Study Data (Now uses the filter) ---
    study_query = f"SELECT date(s.start_time) as date, SUM(s.duration_seconds) as total_study_seconds FROM sessions s JOIN tags t ON s.tag = t.name {where_clause} GROUP BY date(s.start_time)"
    with db.db_connection() as conn:
        study_data = pd.read_sql_query(study_query, conn, params=params, index_col='date',
                                       parse_dates=['date'])
    df['total_study_minutes'] = study_data['total_study_seconds'] / 60
    df['total_study_minutes'] = df['total_study_minutes'].fillna(0)

    # ... (rest of the function is unchanged) ...
    # --- 2. Get Health Metrics ---
    # Pull all numeric fields that may exist in health_metrics so new columns
    # added later (e.g., resting_hr, pulse_ox) are automatically included.
    health_query = "SELECT date, sleep_score, resting_hr, body_battery, pulse_ox, respiration, sleep_duration_seconds, avg_stress FROM health_metrics WHERE date BETWEEN ? AND ?"
    with db.db_connection() as conn:
        health_data = pd.read_sql_query(health_query, conn, params=[start_date, end_date], index_col='date',
                                        parse_dates=['date'])
    df = df.join(health_data)

    # --- 3. Get Activity Data ---
    # --- 3. Get Activity Data ---
    # Fetch activity records including distance and count per day
    activity_query = "SELECT start_time, activity_type, duration_seconds, distance FROM activities WHERE date(start_time) BETWEEN ? AND ?"
    with db.db_connection() as conn:
        activity_data = pd.read_sql_query(activity_query, conn, params=[start_date, end_date],
                                          parse_dates=['start_time'])

    if not activity_data.empty:
        activity_data['date'] = activity_data['start_time'].dt.date
        # Running minutes
        df['running_minutes'] = activity_data[activity_data['activity_type'].str.contains("Running", case=False)].groupby('date')['duration_seconds'].sum() / 60
        # Total distance per day (in original units stored)
        df['distance'] = activity_data.groupby('date')['distance'].sum()
        # Count of activities per day
        df['activity_count'] = activity_data.groupby('date').size()
        # Breathwork sessions count
        df['breathwork_sessions'] = activity_data[activity_data['activity_type'].str.contains("Breathwork", case=False)].groupby('date').size()
        # Total activity minutes per day and total calories
        df['total_activity_minutes'] = activity_data.groupby('date')['duration_seconds'].sum() / 60
        if 'calories' in activity_data.columns:
            df['total_calories'] = activity_data.groupby('date')['calories'].sum()
        else:
            df['total_calories'] = 0
        # Average activity duration (minutes) per day
        df['avg_activity_duration_minutes'] = activity_data.groupby('date')['duration_seconds'].mean() / 60

    # --- 4. Get Custom Factors ---
    custom_factors = db.get_custom_factors()
    for factor_name, in custom_factors:
        col_name = f"factor_{factor_name.replace(' ', '_')}"
        overrides_query = "SELECT date, value FROM custom_factor_log WHERE factor_name = ?"
        with db.db_connection() as conn:
            overrides = pd.read_sql_query(overrides_query, conn, params=[factor_name], index_col='date',
                                          parse_dates=['date'])
        if not overrides.empty:
            overrides = overrides.reindex(date_range, method='ffill').fillna(0)
            df[col_name] = overrides['value']
        else:
            df[col_name] = 0

    # --- 5. Add Day of Week ---
    df['day_of_week'] = df.index.day_name()

    # --- 6. Clean all potential feature columns ---
    # Build the list of features to coerce from the global POTENTIAL_FEATURE_COLS plus any custom factors
    potential_features = POTENTIAL_FEATURE_COLS.copy()
    for col in df.columns:
        if col.startswith('factor_'):
            potential_features.append(col)

    # Coerce all potential features to numeric (any non-numeric becomes NaN)
    for col in potential_features:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    if 'sleep_duration_seconds' in df.columns:
        df['sleep_duration_hours'] = df['sleep_duration_seconds'] / 3600

    return df


def compute_rolling_features(df, windows=(7, 14, 28), min_periods=3):
    """
    Given a daily-indexed DataFrame, compute rolling means, stds, lags and cumulative sums
    for the configured windows. Returns a new DataFrame with added columns.

    Columns will be named like: sleep_score_roll7_mean, total_study_minutes_roll14_sum, etc.
    """
    df = df.copy()
    # Ensure daily index
    df.index = pd.to_datetime(df.index)

    for w in windows:
        roll = df.rolling(window=w, min_periods=min_periods)
        for col in ['sleep_score', 'resting_hr', 'body_battery', 'avg_stress', 'total_study_minutes', 'running_minutes', 'distance', 'total_activity_minutes', 'intensity_minutes', 'hydration_ml']:
            if col in df.columns:
                df[f'{col}_roll{w}_mean'] = roll[col].mean()
                df[f'{col}_roll{w}_std'] = roll[col].std()
                df[f'{col}_roll{w}_sum'] = roll[col].sum()
                # lag by window (previous window's mean)
                df[f'{col}_lag{w}_mean'] = df[f'{col}_roll{w}_mean'].shift(w)

    return df


def run_weekly_analysis(start_date, end_date, data_method='Imputed', model_type='Lasso', window=7, where_clause=None, params=None):
    """
    Prepare weekly-aggregated features (resample W-SUN), compute rolling and lag features,
    then run the requested model. Returns the same structure as run_analysis.
    """
    # Default where clause
    if where_clause is None:
        where_clause = "WHERE date(s.start_time) BETWEEN ? AND ?"
    if params is None:
        params = [start_date.isoformat(), end_date.isoformat()]

    # Get daily features first
    daily = prepare_daily_features(start_date, end_date, where_clause, params)

    # Create weekly resampled frame ending on Sunday
    # Build aggregation dict only for columns that exist in the daily DataFrame
    candidate_aggs = {
        'total_study_minutes': 'sum',
        'sleep_score': 'mean',
        'avg_stress': 'mean',
        'body_battery': 'mean',
        'sleep_duration_hours': 'mean',
        'running_minutes': 'sum',
        'distance': 'sum',
        'total_activity_minutes': 'sum',
        'total_calories': 'sum',
        'hydration_ml': 'mean',
        'intensity_minutes': 'sum'
    }
    agg_dict = {k: v for k, v in candidate_aggs.items() if k in daily.columns}
    # If target isn't present, ensure total_study_minutes is created (fill 0)
    if 'total_study_minutes' not in daily.columns:
        daily['total_study_minutes'] = 0
        agg_dict['total_study_minutes'] = 'sum'

    weekly = daily.resample('W-SUN').agg(agg_dict).dropna(how='all')

    # Compute rolling features on the weekly data (so windows interpreted in weeks)
    weekly_with_rolls = compute_rolling_features(weekly, windows=(1,2,4), min_periods=1)

    # Map weekly index to date strings for compatibility with model preparation
    # Reuse _get_available_features/_prepare_model_data logic by temporarily treating weekly index as 'date'
    weekly_with_rolls.index = pd.to_datetime(weekly_with_rolls.index)

    # Create DataFrame shaped similarly to daily for downstream methods
    df = weekly_with_rolls.copy()

    # Update target and day-of-week column to weekly context
    df['day_of_week'] = df.index.day_name()

    # Identify available features under weekly naming and run model prep
    available_features = _get_available_features(df)
    # Reuse _prepare_model_data but it expects a daily index; hack by calling directly
    # Build required columns list
    required_cols_for_model = [TARGET_VARIABLE, DAY_OF_WEEK_COL] + available_features

    if data_method == 'Imputed':
        model_df = df[required_cols_for_model].copy()
        for col in available_features:
            model_df[col] = model_df[col].fillna(model_df[col].mean())
    else:
        model_df = df.dropna(subset=required_cols_for_model).copy()

    if model_df.shape[0] < 4:
        return {"error": f"Not enough weekly data for a meaningful analysis (need >=4 weeks)."}

    # Run selected model
    if model_type == 'Standard':
        return run_standard_ols_analysis(model_df, available_features)
    elif model_type == 'Lasso':
        return run_lasso_analysis(model_df, available_features)
    elif model_type == 'PCA':
        return run_pca_analysis(model_df, available_features)
    else:
        return {"error": "Invalid model type selected."}


def _get_available_features(df):
    """Identifies feature columns that have enough data to be used in a model."""
    custom_factor_cols = [col for col in df.columns if col.startswith(CUSTOM_FACTOR_PREFIX)]
    all_potential_features = POTENTIAL_FEATURE_COLS + custom_factor_cols
    # A feature is available if it exists and has at least 10 non-null data points.
    return [f for f in all_potential_features if f in df.columns and df[f].notna().sum() >= 10]


def _prepare_model_data(df, data_method):
    """Prepares the final DataFrame for modeling based on available features and data method."""
    available_features = _get_available_features(df)
    if not available_features:
        return {"error": "No single factor had enough data points (min 10) in this period to run an analysis."}, None

    required_cols_for_model = [TARGET_VARIABLE, DAY_OF_WEEK_COL] + available_features

    if data_method == 'Imputed':
        model_df = df[required_cols_for_model].copy()
        for col in available_features:
            model_df[col] = model_df[col].fillna(model_df[col].mean())
    else:  # Strict
        model_df = df.dropna(subset=required_cols_for_model).copy()

    if model_df.shape[0] < 10:
        error_message = f"Not enough overlapping data for a '{data_method}' analysis. Need at least 10 complete days."
        return {"error": error_message}, None

    return model_df, available_features


def _prepare_model_matrices(model_df, available_features):
    """Creates the final X (features) and Y (target) matrices for regression models."""
    Y = model_df[TARGET_VARIABLE]
    X = model_df[available_features].copy()
    # Create dummy variables for day of the week to capture weekly patterns
    day_dummies = pd.get_dummies(model_df[DAY_OF_WEEK_COL], drop_first=True, dtype=int)
    X = X.join(day_dummies)
    return X, Y


def _get_display_name(factor):
    """Cleans up factor names for display."""
    return factor.replace(CUSTOM_FACTOR_PREFIX, '').replace('_', ' ').title()


def _is_day_of_week_feature(factor_name):
    """Checks if a feature name corresponds to a day of the week dummy variable."""
    return any(day in factor_name for day in DAYS_OF_WEEK)


def run_standard_ols_analysis(model_df, available_features):
    """Performs the standard Ordinary Least Squares regression."""
    X, Y = _prepare_model_matrices(model_df, available_features)
    X = sm.add_constant(X, has_constant='add')
    model = sm.OLS(Y, X.astype(float)).fit()

    results = {"model_type": "Standard", "model_summary": str(model.summary()), "significant_factors": [], "insignificant_factors": []}
    for factor, p_value in model.pvalues.items():
        if factor.lower() == 'const' or _is_day_of_week_feature(factor):
            continue
        coef = model.params[factor]
        insight = f"A 1-unit increase is associated with a {'increase' if coef >= 0 else 'decrease'} of {abs(coef):.2f} study minutes."
        factor_data = {"name": _get_display_name(factor), "coefficient": coef, "p_value": p_value, "insight": insight}
        if p_value < 0.05:
            results["significant_factors"].append(factor_data)
        else:
            results["insignificant_factors"].append(factor_data)
    results["significant_factors"].sort(key=lambda x: abs(x['coefficient']), reverse=True)
    return results


def run_lasso_analysis(model_df, available_features):
    """Performs Lasso regression with cross-validation to select features."""
    X, Y = _prepare_model_matrices(model_df, available_features)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    lasso = LassoCV(cv=5, random_state=42, max_iter=10000).fit(X_scaled, Y)

    results = {"model_type": "Lasso", "selected_factors": [], "eliminated_factors": [], "alpha": lasso.alpha_}
    feature_names = X.columns.tolist()
    for i, coef in enumerate(lasso.coef_):
        factor_name = feature_names[i]
        if _is_day_of_week_feature(factor_name):
            continue

        insight = f"A 1 standard deviation increase is associated with a {'increase' if coef >= 0 else 'decrease'} of {abs(coef):.2f} study minutes."
        factor_data = {"name": _get_display_name(factor_name), "coefficient": coef, "insight": insight}

        if abs(coef) > 1e-6:
            results["selected_factors"].append(factor_data)
        else:
            results["eliminated_factors"].append(factor_data)

    results["selected_factors"].sort(key=lambda x: abs(x['coefficient']), reverse=True)
    return results


def run_pca_analysis(model_df, available_features):
    """Performs Principal Component Analysis before running regression."""
    X, Y = _prepare_model_matrices(model_df, available_features)
    X_numeric = X.select_dtypes(include='number') # Use X which already has dummies

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_numeric)

    pca = PCA(n_components=0.95)
    principal_components = pca.fit_transform(X_scaled)
    pc_names = [f'PC_{i + 1}' for i in range(pca.n_components_)]
    pc_df = pd.DataFrame(data=principal_components, columns=pc_names, index=model_df.index)

    # In PCA, we typically don't add the day dummies back in after creating components,
    # as the components should capture the variance from all numeric features.
    X_final = sm.add_constant(pc_df, has_constant='add')

    model = sm.OLS(Y, X_final.astype(float)).fit()

    loadings = pd.DataFrame(pca.components_.T, columns=pc_names, index=X_numeric.columns)

    automated_analysis = []
    n_top_features = 3
    for pc_name in pc_names:
        p_value = model.pvalues.get(pc_name)
        if p_value is not None and p_value < 0.05:
            coef = model.params[pc_name]
            effect = "positive" if coef >= 0 else "negative"

            top_features = loadings[pc_name].abs().nlargest(n_top_features)
            feature_descriptions = []
            for feature, loading_val in top_features.items():
                original_loading = loadings.loc[feature, pc_name]
                direction = "(+)" if original_loading >= 0 else "(-)"
                feature_descriptions.append(f"{_get_display_name(feature)} {direction}")

            insight = (f"• Component {pc_name} has a significant {effect} impact on study time. "
                       f"It is primarily driven by: {', '.join(feature_descriptions)}.")
            automated_analysis.append(insight)

    results = {
        "model_type": "PCA",
        "model_summary": str(model.summary()),
        "explained_variance": pca.explained_variance_ratio_,
        "component_loadings": "Component Loadings (How features contribute to PCs):\n\n" + loadings.to_string(),
        "automated_analysis": automated_analysis
    }
    return results


def run_analysis(start_date, end_date, data_method='Strict', model_type='Lasso', where_clause=None, params=None):
    """Main router function to select and run the appropriate analysis."""
    # Ensure default where clause if not provided
    if where_clause is None:
        where_clause = "WHERE date(s.start_time) BETWEEN ? AND ?"
    if params is None:
        params = [start_date.isoformat(), end_date.isoformat()]

    df = prepare_daily_features(start_date, end_date, where_clause, params)
    model_df, available_features = _prepare_model_data(df, data_method)

    if available_features is None:
        return model_df

    if model_type == 'Standard':
        return run_standard_ols_analysis(model_df, available_features)
    elif model_type == 'Lasso':
        return run_lasso_analysis(model_df, available_features)
    elif model_type == 'PCA':
        return run_pca_analysis(model_df, available_features)
    else:
        return {"error": "Invalid model type selected."}


def run_weekly_efficiency_analysis(df):
    """Analyzes the relationship between weekly sleep patterns and study efficiency."""
    df.index = pd.to_datetime(df.index)

    weekly_df = df.resample('W-SUN').agg({
        TARGET_VARIABLE: 'sum',
        'sleep_score': 'mean',
        'avg_stress': 'mean',
        'body_battery': 'mean',
        'sleep_duration_hours': 'mean'
    }).copy()

    weekly_df = weekly_df[weekly_df[TARGET_VARIABLE] > 0]

    if len(weekly_df) < 4:
        return {"error": f"Not enough data for a meaningful weekly analysis. Need at least 4 full weeks, but found only {len(weekly_df)}."}

    # Calculate efficiency metrics
    weekly_df['study_per_sleep_hour'] = weekly_df[TARGET_VARIABLE] / weekly_df['sleep_duration_hours']
    weekly_df['efficiency_score'] = weekly_df['sleep_score'] / weekly_df[TARGET_VARIABLE]

    correlation_matrix = weekly_df[[
        'study_per_sleep_hour', 'efficiency_score', 'sleep_score',
        'avg_stress', 'body_battery'
    ]].corr()

    # Generate automated insights
    insights = []
    corr_sleep = correlation_matrix.loc['study_per_sleep_hour', 'sleep_score']
    if corr_sleep > 0.5:
        insights.append(f"• There is a strong positive correlation ({corr_sleep:.2f}) between average sleep score and study minutes achieved per hour of sleep. Better sleep quality is linked to higher study efficiency.")
    elif corr_sleep < -0.5:
        insights.append(f"• There is a strong negative correlation ({corr_sleep:.2f}) between average sleep score and study efficiency. This is unusual and might be worth investigating.")
    else:
        insights.append(f"• The link between sleep score and study efficiency is moderate or weak ({corr_sleep:.2f}).")

    return {
        "model_type": "Weekly Efficiency",
        "correlation_matrix": correlation_matrix.to_string(),
        "weekly_data_preview": weekly_df.to_string(),
        "insights": insights
    }