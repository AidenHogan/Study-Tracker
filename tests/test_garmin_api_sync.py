"""Tests for the official Garmin Health API sync (no network access needed)."""
import json
import os
import sqlite3
import sys
import time
from datetime import date

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core import database_manager as db  # noqa: E402
from core import data_importer, garmin_api, garmin_downloader  # noqa: E402


LEGACY_SCHEMA = """CREATE TABLE health_metrics (date TEXT PRIMARY KEY, sleep_score INTEGER, resting_hr INTEGER,
    body_battery INTEGER, pulse_ox REAL, respiration REAL, sleep_duration_seconds INTEGER, avg_stress INTEGER,
    hydration_ml REAL, intensity_minutes INTEGER)"""


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    path = str(tmp_path / 'test.db')
    monkeypatch.setattr(db, 'DB_PATH', path)
    return path


@pytest.fixture
def tmp_garmin_files(tmp_path, monkeypatch):
    monkeypatch.setattr(garmin_api, 'CONFIG_PATH', str(tmp_path / 'cfg.json'))
    monkeypatch.setattr(garmin_api, 'TOKEN_PATH', str(tmp_path / 'tok.json'))
    monkeypatch.setattr(garmin_api, 'STATE_PATH', str(tmp_path / 'state.json'))
    for env in ('GARMIN_CLIENT_ID', 'GARMIN_CLIENT_SECRET', 'GARMIN_REDIRECT_URI',
                'GARMIN_API_KEY', 'GARMIN_AUTH_MODE'):
        monkeypatch.delenv(env, raising=False)
    return tmp_path


SAMPLE = {
    'dailies': [
        {'summaryId': 'd1', 'calendarDate': '2026-11-10', 'durationInSeconds': 40000, 'steps': 5000},
        {'summaryId': 'd1b', 'calendarDate': '2026-11-10', 'durationInSeconds': 86400, 'steps': 9876,
         'restingHeartRateInBeatsPerMinute': 52, 'averageStressLevel': 31, 'maxStressLevel': 90,
         'moderateIntensityDurationInSeconds': 1200, 'vigorousIntensityDurationInSeconds': 600,
         'activeKilocalories': 450, 'distanceInMeters': 7012.5, 'bodyBatteryChargedValue': 60,
         'bodyBatteryDrainedValue': 55},
    ],
    'sleeps': [
        {'summaryId': 's1', 'calendarDate': '2026-11-10', 'durationInSeconds': 27000,
         'overallSleepScore': {'value': 82, 'qualifierKey': 'GOOD'},
         'deepSleepDurationInSeconds': 5400, 'remSleepInSeconds': 6000,
         'timeOffsetSleepSpo2': {'0': 95, '60': 97}, 'timeOffsetSleepRespiration': {'0': 14.0, '60': 15.0}},
        {'summaryId': 'nap', 'calendarDate': '2026-11-10', 'durationInSeconds': 1800,
         'overallSleepScore': {'value': 40}},
    ],
    'stressDetails': [
        {'summaryId': 'st1', 'calendarDate': '2026-11-10',
         'timeOffsetBodyBatteryValues': {'0': 80, '3600': 25, '7200': 40},
         'timeOffsetStressLevelValues': {'0': 20, '180': -1}},
    ],
    'hrv': [{'summaryId': 'h1', 'calendarDate': '2026-11-10', 'lastNightAvg': 48, 'lastNight5MinHigh': 70}],
    # respiration without calendarDate: date derived from start time + local offset
    'respiration': [{'summaryId': 'r1', 'startTimeInSeconds': 1794441600,  # 2026-11-12 00:00 UTC
                     'startTimeOffsetInSeconds': -18000, 'timeOffsetEpochToBreaths': {'0': 12.0, '60': 13.0}}],
    'userMetrics': [{'summaryId': 'u1', 'calendarDate': '2026-11-10', 'vo2Max': 51.0, 'fitnessAge': 30}],
}


def test_build_daily_metrics_maps_legacy_and_new_columns():
    out = garmin_downloader.build_daily_metrics(SAMPLE)
    d = out['2026-11-10']
    # legacy semantics
    assert d['sleep_score'] == 82                 # main sleep, not the nap
    assert d['sleep_duration_seconds'] == 27000
    assert d['resting_hr'] == 52
    assert d['body_battery'] == 25                # lowest of the day
    assert d['pulse_ox'] == 96.0
    assert d['respiration'] == 14.5
    assert d['avg_stress'] == 31
    assert d['intensity_minutes'] == 20 + 2 * 10  # moderate + 2x vigorous
    # new metrics
    assert d['steps'] == 9876                     # most complete daily wins
    assert d['body_battery_high'] == 80
    assert d['hrv_last_night'] == 48
    assert d['vo2_max'] == 51.0
    assert d['deep_sleep_seconds'] == 5400
    assert d['data_source'] == 'garmin_api'
    # all-day respiration fallback on a day without sleep; local date 2026-11-11
    assert out['2026-11-11'] == {'respiration': 12.5, 'data_source': 'garmin_api'}
    # every produced column is a real DB column
    allowed = set(db.LEGACY_HEALTH_COLUMNS) | set(db.EXTENDED_HEALTH_COLUMNS)
    for metrics in out.values():
        assert set(metrics) <= allowed


def test_negative_stress_is_treated_as_missing():
    out = garmin_downloader.build_daily_metrics(
        {'dailies': [{'calendarDate': '2026-11-01', 'averageStressLevel': -1, 'steps': 10}]})
    assert 'avg_stress' not in out['2026-11-01']


def test_legacy_database_is_migrated_without_data_loss(tmp_db):
    with sqlite3.connect(tmp_db) as conn:
        conn.execute(LEGACY_SCHEMA)
        conn.execute("INSERT INTO health_metrics (date, sleep_score, hydration_ml) VALUES ('2025-01-01', 77, 2100)")
    db.setup_database()
    cols = {r[1] for r in db.fetch_all("PRAGMA table_info(health_metrics)")}
    assert set(db.EXTENDED_HEALTH_COLUMNS) <= cols
    assert db.fetch_one("SELECT sleep_score, hydration_ml, steps FROM health_metrics") == (77, 2100.0, None)


def test_api_upsert_preserves_existing_values(tmp_db):
    db.setup_database()
    db.add_or_replace_health_metric('2026-11-10', 70, None, None, None, None, 25000, None, hydration_ml=1800)
    for d, m in garmin_downloader.build_daily_metrics(SAMPLE).items():
        db.upsert_health_metrics(d, m)
    row = db.fetch_one("SELECT sleep_score, hydration_ml, steps FROM health_metrics WHERE date='2026-11-10'")
    assert row == (82, 1800.0, 9876)  # API value wins, hydration from CSV survives


def test_csv_import_does_not_wipe_api_metrics(tmp_db, tmp_path):
    db.setup_database()
    db.upsert_health_metrics('2026-11-10', {'sleep_score': 82, 'steps': 9876, 'hrv_last_night': 48})
    csv = tmp_path / 'garmin.csv'
    csv.write_text("Date,Score,Duration,Resting Heart Rate\n2026-11-10,80,7h 30m,53\n", encoding='utf-8')
    count, msg = data_importer.import_garmin_csv(str(csv))
    assert count == 1, msg
    row = db.fetch_one("SELECT sleep_score, resting_hr, sleep_duration_seconds, steps, hrv_last_night "
                       "FROM health_metrics WHERE date='2026-11-10'")
    assert row == (80, 53, 27000, 9876, 48.0)


def test_export_csv_roundtrips_through_importer(tmp_db, tmp_path, monkeypatch):
    monkeypatch.setattr(garmin_downloader, 'export_csv_path', lambda: str(tmp_path / 'export.csv'))
    db.setup_database()
    for d, m in garmin_downloader.build_daily_metrics(SAMPLE).items():
        db.upsert_health_metrics(d, m)
    path = garmin_downloader.export_csv_snapshot(['2026-11-10'])
    db.execute_query("DELETE FROM health_metrics")
    count, msg = data_importer.import_garmin_csv(path)
    assert count == 1, msg
    row = db.fetch_one("SELECT sleep_score, sleep_duration_seconds, body_battery, steps, vo2_max "
                       "FROM health_metrics WHERE date='2026-11-10'")
    assert row == (82, 27000, 25, 9876, 51.0)


class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload
        self.content = b'x' if payload is not None else b''
        self.text = json.dumps(payload) if payload is not None else ''
        self.ok = 200 <= status < 300

    def json(self):
        return self._payload


def _configure(tmp_garmin_files):
    garmin_api.save_config('cid', 'secret')
    garmin_api._write_json(garmin_api.TOKEN_PATH, {
        'access_token': 'AT', 'refresh_token': 'RT', 'expires_at': time.time() + 3600})


def test_pull_is_chunked_into_24h_windows(tmp_garmin_files, monkeypatch):
    _configure(tmp_garmin_files)
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(params)
        assert headers['Authorization'] == 'Bearer AT'
        return _Resp(200, [{'summaryId': str(len(calls))}])

    monkeypatch.setattr(garmin_api.requests, 'get', fake_get)
    res = garmin_api.pull_summaries('dailies', 0, 86400 * 2 + 10)
    assert len(res) == 3
    assert all(p['uploadEndTimeInSeconds'] - p['uploadStartTimeInSeconds'] <= 86400 for p in calls)


def test_expired_access_token_is_refreshed(tmp_garmin_files, monkeypatch):
    _configure(tmp_garmin_files)
    garmin_api._write_json(garmin_api.TOKEN_PATH, {
        'access_token': 'OLD', 'refresh_token': 'RT', 'expires_at': time.time() - 10})
    posted = {}

    def fake_post(url, data=None, timeout=None, headers=None):
        posted.update(data)
        return _Resp(200, {'access_token': 'NEW', 'refresh_token': 'RT2', 'expires_in': 86400})

    monkeypatch.setattr(garmin_api.requests, 'post', fake_post)
    assert garmin_api.get_access_token() == 'NEW'
    assert posted['grant_type'] == 'refresh_token' and posted['refresh_token'] == 'RT'
    assert garmin_api.load_token()['refresh_token'] == 'RT2'


def test_personal_key_is_exchanged_for_cached_token(tmp_garmin_files, monkeypatch):
    garmin_api.save_api_key('  MYKEY ')
    assert garmin_api.uses_api_key() and garmin_api.is_configured() and garmin_api.has_token()
    posts, gets = [], []

    def fake_post(url, timeout=None, headers=None, data=None):
        posts.append((url, headers))
        return _Resp(200, {'access_token': 'TOKEN1', 'expires_in': 86400})

    def fake_get(url, params=None, headers=None, timeout=None):
        gets.append((url, headers))
        return _Resp(200, {'data': []})

    monkeypatch.setattr(garmin_api.requests, 'post', fake_post)
    monkeypatch.setattr(garmin_api.requests, 'get', fake_get)
    garmin_api.personal_get('usersummary-service/v2/dailysummaries')
    garmin_api.personal_get('usersummary-service/v2/dailysummaries')
    assert len(posts) == 1                                      # token cached between calls
    assert posts[0][0] == garmin_api.PERSONAL_TOKEN_URL
    assert posts[0][1]['Authorization'] == 'ApiKey MYKEY'       # documented header format
    assert gets[0][0].startswith('https://personal.connectapi.garmin.com/usersummary-service/')
    assert gets[0][1]['Authorization'] == 'Bearer TOKEN1'
    with pytest.raises(garmin_api.GarminConfigError):
        garmin_api.authorize_interactive(open_browser=False, timeout=1)


@pytest.mark.parametrize('payload', [{'accessToken': 'T'}, {'token': 'T'}, 'T'])
def test_personal_token_response_variants(tmp_garmin_files, monkeypatch, payload):
    garmin_api.save_api_key('K')
    monkeypatch.setattr(garmin_api.requests, 'post', lambda *a, **k: _Resp(200, payload))
    assert garmin_api.get_personal_access_token() == 'T'


def test_rejected_personal_key_and_expired_token(tmp_garmin_files, monkeypatch):
    garmin_api.save_api_key('BAD')
    monkeypatch.setattr(garmin_api.requests, 'post', lambda *a, **k: _Resp(401, {'errorMessage': 'Unauthorized'}))
    with pytest.raises(garmin_api.GarminAuthError, match='personal API key'):
        garmin_api.verify_credentials()

    # a 401 on a data call fetches a fresh token once and retries
    tokens = iter(['OLD', 'NEW'])
    monkeypatch.setattr(garmin_api.requests, 'post', lambda *a, **k: _Resp(200, {'access_token': next(tokens)}))
    seen = []

    def fake_get(url, params=None, headers=None, timeout=None):
        seen.append(headers['Authorization'])
        return _Resp(401, {}) if headers['Authorization'] == 'Bearer OLD' else _Resp(200, {'ok': 1})

    monkeypatch.setattr(garmin_api.requests, 'get', fake_get)
    assert garmin_api.personal_get('x') == {'ok': 1}
    assert seen == ['Bearer OLD', 'Bearer NEW']


PERSONAL_DAILY = {
    'calendarDate': '2026-11-10',
    'movement': {'steps': {'value': 9876, 'distanceInMeters': 7012.5}, 'floorsAscended': {'value': 8}},
    'calories': {'burnedActive': 450},
    'heartRate': {'restingValue': 52, 'minValue': 48, 'maxValue': 160},
    'intensityMinutes': {'moderate': 20, 'vigorous': 10},
    'stress': {'avgLevel': 31, 'maxLevel': 90},
    'bodyBattery': {'minValue': 25, 'maxValue': 80, 'chargedValue': 60, 'drainedValue': 55},
    'hydration': {'consumedInFractionalMl': 2250.0},
    'respiration': {'avgValue': 13},
    'pulseOx': {'avgValue': 94},
}
PERSONAL_SLEEP = {'calendarDate': '2026-11-10', 'sleepTimeSeconds': 27000, 'deepSleepSeconds': 5400,
                  'remSleepSeconds': 6000, 'awakeSleepSeconds': 600, 'averageSpO2Value': 96.0,
                  'averageRespirationValue': 14.5, 'sleepScores': {'overall': {'value': 82}}}


def test_build_personal_daily_metrics():
    out = garmin_downloader.build_personal_daily_metrics(
        [PERSONAL_DAILY, {'calendarDate': '2026-11-11', 'stress': {'avgLevel': -1}}],
        [PERSONAL_SLEEP],
        [{'calendarDate': '2026-11-10', 'lastNightAvg': 48, 'lastNight5MinHigh': 70}],
        [{'summaryDate': '2026-11-10', 'latestWeight': {'weight': 72500.0}}],
        ('2026-11-10', [{'fitnessAge': 29.6}]))
    d = out['2026-11-10']
    assert (d['sleep_score'], d['sleep_duration_seconds'], d['resting_hr'], d['body_battery']) == (82, 27000, 52, 25)
    assert (d['pulse_ox'], d['respiration']) == (96.0, 14.5)   # overnight values win over all-day
    assert (d['avg_stress'], d['intensity_minutes'], d['hydration_ml']) == (31, 40, 2250.0)
    assert (d['steps'], d['hrv_last_night'], d['weight_kg'], d['fitness_age']) == (9876, 48, 72.5, 30)
    assert d['data_source'] == 'garmin_personal_api'
    assert '2026-11-11' not in out                               # -1 stress = no data
    allowed = set(db.LEGACY_HEALTH_COLUMNS) | set(db.EXTENDED_HEALTH_COLUMNS)
    assert set(d) <= allowed


def test_personal_sync_end_to_end(tmp_db, tmp_garmin_files, monkeypatch):
    garmin_api.save_api_key('K')
    monkeypatch.setattr(garmin_downloader, 'export_csv_path', lambda: str(tmp_garmin_files / 'export.csv'))
    db.setup_database()
    monkeypatch.setattr(garmin_api.requests, 'post', lambda *a, **k: _Resp(200, {'access_token': 'T'}))
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        path = url.split('garmin.com/', 1)[1]
        calls.append((path, params))
        if path.startswith('usersummary-service/v2/dailysummaries'):
            return _Resp(200, {'data': [PERSONAL_DAILY]})
        if path.startswith('sleep-service'):
            return _Resp(200, [PERSONAL_SLEEP])
        if path.startswith('hrv-service'):
            return _Resp(200, {'hrvSummaries': [{'calendarDate': '2026-11-10', 'lastNightAvg': 48}]})
        return _Resp(404, {})

    monkeypatch.setattr(garmin_api.requests, 'get', fake_get)
    result = garmin_downloader.sync_health_data(days=60, log=lambda *a: None)
    assert result['days_updated'] == 1 and result['backfill_requested'] == 0
    assert db.fetch_one("SELECT sleep_score, steps, hydration_ml, hrv_last_night FROM health_metrics "
                        "WHERE date='2026-11-10'") == (82, 9876, 2250.0, 48.0)
    sleep_calls = [p for path, p in calls if path.startswith('sleep-service')]
    assert len(sleep_calls) == 2                                 # 60 days split into <=31-day requests
    assert all(not path.startswith('wellness-api') for path, _ in calls)


def test_api_key_from_env_and_switching_modes(tmp_garmin_files, monkeypatch):
    monkeypatch.setenv('GARMIN_API_KEY', 'ENVKEY')
    assert garmin_api.uses_api_key() and garmin_api.load_config()['api_key'] == 'ENVKEY'
    monkeypatch.delenv('GARMIN_API_KEY')
    garmin_api.save_api_key('K')
    garmin_api.save_config('cid', 'sec')       # switching to OAuth keeps the key but stops using it
    assert not garmin_api.uses_api_key()
    garmin_api.save_api_key('K')
    garmin_api.deregister_user()               # disconnect in key mode just forgets the key
    assert not garmin_api.uses_api_key() and 'api_key' not in garmin_api.load_config()


def test_sync_requires_configuration(tmp_garmin_files):
    with pytest.raises(garmin_api.GarminConfigError):
        garmin_downloader.sync_health_data(days=7)


def test_full_sync_writes_db_and_requests_backfill(tmp_db, tmp_garmin_files, monkeypatch):
    _configure(tmp_garmin_files)
    monkeypatch.setattr(garmin_downloader, 'export_csv_path', lambda: str(tmp_garmin_files / 'export.csv'))
    db.setup_database()
    backfills = []

    def fake_get(url, params=None, headers=None, timeout=None):
        stype = url.rsplit('/', 1)[-1]
        if '/backfill/' in url:
            backfills.append(stype)
            return _Resp(202)
        # return the sample only for the first window to avoid duplicates
        if params['uploadEndTimeInSeconds'] - params['uploadStartTimeInSeconds'] < 86400 or not hasattr(fake_get, stype):
            setattr(fake_get, stype, True)
            return _Resp(200, SAMPLE.get(stype, []))
        return _Resp(200, [])

    monkeypatch.setattr(garmin_api.requests, 'get', fake_get)
    result = garmin_downloader.sync_health_data(days=30, log=lambda *a: None)
    assert result['days_updated'] == 2
    assert set(backfills) == set(garmin_api.SUMMARY_TYPES)  # 30 days > 7-day pull lookback
    assert db.fetch_one("SELECT steps FROM health_metrics WHERE date='2026-11-10'") == (9876,)
    assert db.fetch_one("SELECT COUNT(*) FROM garmin_api_raw")[0] >= 7
    assert garmin_api.load_state()['last_upload_end'] > 0
    assert os.path.exists(result['csv_path'])


def test_find_missing_data_window_unchanged():
    assert garmin_downloader.find_missing_data_window(None) == 90
    assert garmin_downloader.find_missing_data_window(date.today()) == 7
