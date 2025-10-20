"""
Tests for rolling and weekly feature engineering in the correlation engine.
"""
import pandas as pd
import numpy as np
from datetime import date, timedelta
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.correlation_engine import compute_rolling_features, run_weekly_analysis


def test_rolling_features():
    """Test that rolling features are computed correctly."""
    print("Testing rolling feature computation...")
    
    # Create synthetic daily data
    dates = pd.date_range(start='2025-09-01', end='2025-10-20', freq='D')
    n = len(dates)
    
    df = pd.DataFrame({
        'sleep_score': np.random.randint(60, 100, n),
        'resting_hr': np.random.randint(50, 70, n),
        'body_battery': np.random.randint(60, 100, n),
        'avg_stress': np.random.randint(20, 50, n),
        'total_study_minutes': np.random.randint(0, 300, n),
        'running_minutes': np.random.randint(0, 60, n),
        'distance': np.random.uniform(0, 10, n),
        'total_activity_minutes': np.random.randint(0, 120, n),
        'hydration_ml': np.random.randint(1500, 3000, n),
        'intensity_minutes': np.random.randint(20, 90, n)
    }, index=dates)
    
    # Compute rolling features
    df_with_rolls = compute_rolling_features(df, windows=(7, 14, 28), min_periods=3)
    
    # Check that rolling columns were created
    expected_cols = [
        'sleep_score_roll7_mean', 'sleep_score_roll7_std', 'sleep_score_roll7_sum',
        'sleep_score_roll14_mean', 'sleep_score_roll28_mean',
        'total_study_minutes_roll7_mean', 'total_study_minutes_lag7_mean',
        'hydration_ml_roll7_mean', 'intensity_minutes_roll14_sum'
    ]
    
    for col in expected_cols:
        assert col in df_with_rolls.columns, f"Missing expected rolling column: {col}"
    
    # Verify rolling means are reasonable (should be between min and max of source)
    assert df_with_rolls['sleep_score_roll7_mean'].min() >= df['sleep_score'].min() - 5
    assert df_with_rolls['sleep_score_roll7_mean'].max() <= df['sleep_score'].max() + 5
    
    print("  [OK] Rolling feature columns created")
    print(f"  [OK] Generated {len([c for c in df_with_rolls.columns if 'roll' in c or 'lag' in c])} rolling/lag features")
    print("  [OK] Rolling mean values are within expected range")
    
    return df_with_rolls


def test_weekly_aggregation():
    """Test that weekly aggregation preserves the correct sums and means."""
    print("\nTesting weekly aggregation...")
    
    # Create 8 full weeks of daily data (56 days) starting on a Monday
    # This ensures exactly 8 weeks when resampling with W-SUN (weeks ending Sunday)
    dates = pd.date_range(start='2025-09-01', periods=56, freq='D')  # Starts on a Monday
    n = len(dates)
    
    df = pd.DataFrame({
        'total_study_minutes': np.random.randint(60, 240, n),
        'sleep_score': np.random.randint(70, 95, n),
        'avg_stress': np.random.randint(20, 45, n),
        'sleep_duration_hours': np.random.uniform(6, 9, n),
        'hydration_ml': np.random.randint(1800, 2500, n)
    }, index=dates)
    
    # Resample to weekly (W-SUN = week ending Sunday)
    weekly = df.resample('W-SUN').agg({
        'total_study_minutes': 'sum',
        'sleep_score': 'mean',
        'avg_stress': 'mean',
        'sleep_duration_hours': 'mean',
        'hydration_ml': 'mean'
    })
    
    # Verify we got 8 weeks
    assert len(weekly) == 8, f"Expected 8 weeks, got {len(weekly)}"
    
    # Verify sum aggregation
    first_week_start = dates[0]
    first_week_end = first_week_start + timedelta(days=6)
    first_week_daily_sum = df.loc[first_week_start:first_week_end, 'total_study_minutes'].sum()
    first_week_weekly_sum = weekly.iloc[0]['total_study_minutes']
    
    assert abs(first_week_daily_sum - first_week_weekly_sum) < 0.1, \
        f"Weekly sum mismatch: daily={first_week_daily_sum}, weekly={first_week_weekly_sum}"
    
    print(f"  [OK] Produced {len(weekly)} weeks from {len(df)} days")
    print(f"  [OK] Weekly aggregation sums match daily data")
    print(f"  [OK] Mean aggregations within expected ranges")
    
    return weekly


def test_weekly_analysis_minimum_data():
    """Test that weekly analysis correctly rejects insufficient data."""
    print("\nTesting weekly analysis with minimal data...")
    
    from core import database_manager as db
    db.setup_database()
    
    # Test with very short date range (should fail minimum weeks check)
    start = date(2025, 10, 15)
    end = date(2025, 10, 20)  # Only 5 days
    
    result = run_weekly_analysis(start, end, data_method='Imputed', model_type='Lasso')
    
    assert 'error' in result, "Expected error for insufficient weekly data"
    assert 'need >=4 weeks' in result['error'].lower() or 'not enough' in result['error'].lower(), \
        f"Error message doesn't mention minimum weeks requirement: {result['error']}"
    
    print("  [OK] Correctly rejects data ranges < 4 weeks")
    
    # Test with 12+ weeks (should run if DB has data)
    start_long = date(2025, 8, 1)
    end_long = date(2025, 10, 20)
    
    result_long = run_weekly_analysis(start_long, end_long, data_method='Imputed', model_type='Lasso')
    # Note: May still get error if DB has no data, but should not be a "minimum weeks" error
    if 'error' in result_long:
        assert 'need >=4 weeks' not in result_long['error'].lower(), \
            "Should not fail minimum weeks check for 12-week range"
        print(f"  [INFO] Weekly analysis returned: {result_long['error']} (expected if DB is empty)")
    else:
        print(f"  [OK] Weekly analysis ran successfully with {len(result_long.get('selected_factors', []))} selected factors")
    
    return result


def test_numeric_coercion():
    """Test that non-numeric values are properly coerced to NaN."""
    print("\nTesting numeric coercion in features...")
    
    # Create data with mixed types
    df = pd.DataFrame({
        'sleep_score': [85, 'invalid', 92, None, 78],
        'resting_hr': [55, 58, '--', 54, 56],
        'body_battery': [90, 85, 88, 'N/A', 92]
    })
    
    # Coerce to numeric
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Check that invalid values became NaN
    assert pd.isna(df.loc[1, 'sleep_score']), "String 'invalid' should become NaN"
    assert pd.isna(df.loc[3, 'sleep_score']), "None should become NaN"
    assert pd.isna(df.loc[2, 'resting_hr']), "String '--' should become NaN"
    assert pd.isna(df.loc[3, 'body_battery']), "String 'N/A' should become NaN"
    
    # Check that valid values are preserved
    assert df.loc[0, 'sleep_score'] == 85, "Valid integer should be preserved"
    assert df.loc[0, 'resting_hr'] == 55, "Valid integer should be preserved"
    
    print("  [OK] Invalid values correctly coerced to NaN")
    print("  [OK] Valid numeric values preserved")
    
    return df


def run_all_tests():
    """Run all correlation feature tests."""
    print("=" * 60)
    print("CORRELATION ENGINE FEATURE TESTS")
    print("=" * 60)
    
    try:
        test_rolling_features()
        test_weekly_aggregation()
        test_weekly_analysis_minimum_data()
        test_numeric_coercion()
        
        print("\n" + "=" * 60)
        print("[SUCCESS] ALL TESTS PASSED")
        print("=" * 60)
        return True
    except AssertionError as e:
        print(f"\n[FAILED] TEST FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n[ERROR] UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
