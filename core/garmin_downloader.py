# file: core/garmin_downloader.py
"""
Garmin sync: downloads wellness data through the official Garmin Health API
(see core/garmin_api.py) and stores one row per day in `health_metrics`.

Compatibility with the previous garth-based version:
* The legacy columns keep their meaning:
    sleep_score            <- sleep overallSleepScore
    sleep_duration_seconds <- sleep durationInSeconds
    resting_hr             <- dailies restingHeartRateInBeatsPerMinute
    body_battery           <- LOWEST body battery of the day (stressDetails)
    pulse_ox               <- average SpO2 during sleep (falls back to all-day pulse ox)
    respiration            <- average breathing rate during sleep (falls back to all-day)
    avg_stress             <- dailies averageStressLevel
    intensity_minutes      <- moderate + 2 x vigorous minutes (Garmin's own definition)
    hydration_ml           <- not provided by the Health API; existing values are preserved
* Sync merges into existing rows (only non-null values are written), so data from CSV
  imports or manual entries is never wiped.
* A CSV export with the legacy column names (plus new ones) is still written to
  ~/garmin_auto_export.csv and can be re-imported with "Import From File".
* `download_health_stats()` and `find_missing_data_window()` keep their signatures.
"""

import json
import os
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from . import garmin_api
from .garmin_api import GarminAPIError, GarminAuthError, GarminConfigError  # re-exported

# Backwards-compatible alias: main_app and older callers caught `GarthException`.
GarthException = GarminAuthError

# --- CSV column names (must match core/data_importer.py) ---
COL_DATE = 'Date'
COL_SCORE = 'Score'
COL_RESTING_HR = 'Resting Heart Rate'
COL_BODY_BATTERY = 'Body Battery'
COL_PULSE_OX = 'Avg. SpO2'
COL_RESPIRATION = 'Avg. Respiration Rate'
COL_AVG_STRESS = 'Avg. Stress'
COL_DURATION = 'Duration'
COL_HYDRATION = 'Hydration (mL)'
COL_INTENSITY_MINUTES = 'Intensity Minutes'

LEGACY_CSV_COLUMNS = {
    'sleep_score': COL_SCORE,
    'resting_hr': COL_RESTING_HR,
    'body_battery': COL_BODY_BATTERY,
    'pulse_ox': COL_PULSE_OX,
    'respiration': COL_RESPIRATION,
    'avg_stress': COL_AVG_STRESS,
    'hydration_ml': COL_HYDRATION,
    'intensity_minutes': COL_INTENSITY_MINUTES,
}

# How far back upload-time pulls go. Older gaps are requested via backfill instead,
# which keeps a 90-day sync from issuing ~800 HTTP requests.
PULL_LOOKBACK_DAYS = 7
# Overlap with the previous sync so summaries uploaded right at the boundary are not missed.
PULL_OVERLAP_SECONDS = 3600


def find_missing_data_window(most_recent_date_in_db, max_days=90):
    """
    Return the number of days to fetch (1..max_days) to fill the gap since the most
    recent date in the DB (None -> max_days). Unchanged from the garth version.
    """
    if most_recent_date_in_db is None:
        return max_days

    today = date.today()
    days_since_last = (today - most_recent_date_in_db).days

    if days_since_last <= 1:
        return 7  # Fetch a week to catch any updates
    if days_since_last >= max_days:
        return max_days
    return min(days_since_last + 3, max_days)


# ---------------------------------------------------------------------------
# Summary -> daily metric mapping (pure functions, unit-tested)
# ---------------------------------------------------------------------------

def _local_date(start_ts, offset):
    """Calendar date of a summary given its UTC start time and the user's UTC offset."""
    if start_ts is None:
        return None
    return datetime.fromtimestamp(int(start_ts) + int(offset or 0), tz=timezone.utc).date().isoformat()


def _summary_date(summary_type, s):
    if s.get('calendarDate'):
        return s['calendarDate']
    if summary_type == 'bodyComps':
        return _local_date(s.get('measurementTimeInSeconds'), s.get('measurementTimeOffsetInSeconds'))
    return _local_date(s.get('startTimeInSeconds'), s.get('startTimeOffsetInSeconds'))


def _mean(values):
    vals = [float(v) for v in values if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def _int(v):
    return int(round(v)) if v is not None else None


def _minutes(seconds):
    return int(round(seconds / 60)) if seconds is not None else None


def _pick_most_complete(summaries, key='durationInSeconds'):
    """Garmin re-sends updated versions of a day's summary; keep the most complete one."""
    best = None
    for s in summaries:
        if best is None or (s.get(key) or 0) >= (best.get(key) or 0):
            best = s
    return best


def group_by_date(summary_type, summaries):
    grouped = defaultdict(list)
    for s in summaries or []:
        d = _summary_date(summary_type, s)
        if d:
            grouped[d].append(s)
    return grouped


def build_daily_metrics(summaries_by_type):
    """Convert raw Health API summaries into {date: {health_metrics column: value}}.

    `summaries_by_type` maps a summary type (e.g. 'dailies') to a list of summary dicts.
    Only columns with actual data are included for each day.
    """
    grouped = {t: group_by_date(t, lst) for t, lst in summaries_by_type.items()}
    all_dates = set()
    for g in grouped.values():
        all_dates.update(g.keys())

    result = {}
    for d in sorted(all_dates):
        m = {}

        # --- Dailies ---
        daily = _pick_most_complete(grouped.get('dailies', {}).get(d, []))
        if daily:
            m['resting_hr'] = daily.get('restingHeartRateInBeatsPerMinute')
            m['avg_stress'] = daily.get('averageStressLevel')
            m['max_stress'] = daily.get('maxStressLevel')
            m['steps'] = daily.get('steps')
            m['distance_meters'] = daily.get('distanceInMeters')
            m['active_calories'] = daily.get('activeKilocalories')
            m['floors_climbed'] = daily.get('floorsClimbed')
            m['avg_hr'] = daily.get('averageHeartRateInBeatsPerMinute')
            m['min_hr'] = daily.get('minHeartRateInBeatsPerMinute')
            m['max_hr'] = daily.get('maxHeartRateInBeatsPerMinute')
            m['body_battery_charged'] = daily.get('bodyBatteryChargedValue')
            m['body_battery_drained'] = daily.get('bodyBatteryDrainedValue')
            mod = _minutes(daily.get('moderateIntensityDurationInSeconds'))
            vig = _minutes(daily.get('vigorousIntensityDurationInSeconds'))
            m['moderate_intensity_minutes'] = mod
            m['vigorous_intensity_minutes'] = vig
            if mod is not None or vig is not None:
                m['intensity_minutes'] = (mod or 0) + 2 * (vig or 0)
            # Negative stress values (-1/-2) mean "not enough data"
            if m.get('avg_stress') is not None and m['avg_stress'] < 0:
                m['avg_stress'] = None

        # --- Sleep ---
        sleep = _pick_most_complete(grouped.get('sleeps', {}).get(d, []))
        if sleep:
            score = sleep.get('overallSleepScore')
            if isinstance(score, dict):
                score = score.get('value')
            m['sleep_score'] = score
            m['sleep_duration_seconds'] = sleep.get('durationInSeconds')
            m['deep_sleep_seconds'] = sleep.get('deepSleepDurationInSeconds')
            m['light_sleep_seconds'] = sleep.get('lightSleepDurationInSeconds')
            m['rem_sleep_seconds'] = sleep.get('remSleepInSeconds')
            m['awake_seconds'] = sleep.get('awakeDurationInSeconds')
            m['pulse_ox'] = _mean((sleep.get('timeOffsetSleepSpo2') or {}).values())
            m['respiration'] = _mean((sleep.get('timeOffsetSleepRespiration') or {}).values())

        # --- Stress details: body battery lowest/highest, fallback stress ---
        bb_values, stress_values = [], []
        for s in grouped.get('stressDetails', {}).get(d, []):
            bb_values.extend(v for v in (s.get('timeOffsetBodyBatteryValues') or {}).values() if v is not None)
            stress_values.extend(v for v in (s.get('timeOffsetStressLevelValues') or {}).values()
                                 if v is not None and v >= 0)
        if bb_values:
            m['body_battery'] = int(min(bb_values))
            m['body_battery_high'] = int(max(bb_values))
        if m.get('avg_stress') is None and stress_values:
            m['avg_stress'] = _int(_mean(stress_values))

        # --- Fallbacks for SpO2 / respiration from the all-day summaries ---
        if m.get('pulse_ox') is None:
            vals = []
            for s in grouped.get('pulseox', {}).get(d, []):
                vals.extend((s.get('timeOffsetSpo2Values') or {}).values())
            m['pulse_ox'] = _mean(vals)
        if m.get('respiration') is None:
            vals = []
            for s in grouped.get('respiration', {}).get(d, []):
                vals.extend((s.get('timeOffsetEpochToBreaths') or {}).values())
            m['respiration'] = _mean(vals)

        # --- HRV ---
        hrv = _pick_most_complete(grouped.get('hrv', {}).get(d, []))
        if hrv:
            m['hrv_last_night'] = hrv.get('lastNightAvg')
            m['hrv_5min_high'] = hrv.get('lastNight5MinHigh')

        # --- User metrics (VO2 max, fitness age) ---
        um_list = grouped.get('userMetrics', {}).get(d, [])
        if um_list:
            um = um_list[-1]
            m['vo2_max'] = um.get('vo2Max')
            m['fitness_age'] = um.get('fitnessAge')

        # --- Skin temperature ---
        st_list = grouped.get('skinTemp', {}).get(d, [])
        if st_list:
            m['skin_temp_deviation'] = st_list[-1].get('avgDeviationCelsius')

        # --- Body composition (weight) ---
        bc_list = grouped.get('bodyComps', {}).get(d, [])
        if bc_list:
            grams = bc_list[-1].get('weightInGrams')
            m['weight_kg'] = round(grams / 1000.0, 2) if grams else None

        m = {k: v for k, v in m.items() if v is not None}
        if m:
            m['data_source'] = 'garmin_api'
            result[d] = m
    return result


# ---------------------------------------------------------------------------
# Sync orchestration
# ---------------------------------------------------------------------------

def _compute_windows(days, start_date_override, now_ts, log):
    """Return (pull_start_ts, backfill_start_date or None, description)."""
    state = garmin_api.load_state()
    earliest_pull = now_ts - PULL_LOOKBACK_DAYS * 86400
    today = date.today()

    if start_date_override:
        wanted_start = start_date_override
    elif days is not None:
        wanted_start = today - timedelta(days=int(days) - 1)
    else:
        # Smart sync: continue from the last pulled upload window, and backfill any gap
        # between the newest day in the DB and the pull lookback.
        from . import database_manager as db
        most_recent = db.get_most_recent_health_date()
        wanted_start = today - timedelta(days=find_missing_data_window(most_recent) - 1)
        last_end = state.get('last_upload_end')
        if last_end and most_recent:
            pull_start = max(int(last_end) - PULL_OVERLAP_SECONDS, earliest_pull)
            backfill_start = wanted_start if wanted_start < date.fromtimestamp(earliest_pull) else None
            log(f"Smart sync: last data in DB {most_recent}, continuing from last sync")
            return pull_start, backfill_start

    wanted_ts = int(datetime.combine(wanted_start, datetime.min.time()).timestamp())
    pull_start = max(wanted_ts, earliest_pull)
    backfill_start = wanted_start if wanted_ts < earliest_pull else None
    return pull_start, backfill_start


def sync_health_data(days=None, start_date_override=None, log=print, export_csv=True):
    """Pull Garmin Health API data and merge it into `health_metrics`.

    Args:
        days: Sync the last N days (None = smart sync).
        start_date_override: Explicit start date (datetime.date).
        log: callable for progress messages.
        export_csv: also write ~/garmin_auto_export.csv.

    Returns a dict: {'days_updated', 'summaries', 'backfill_requested', 'skipped', 'csv_path'}.
    Raises GarminConfigError / GarminAuthError / GarminAPIError.
    """
    from . import database_manager as db

    if not garmin_api.is_configured():
        raise GarminConfigError(
            "Garmin API is not configured. Use Garmin -> Configure Garmin API first.")
    if garmin_api.uses_api_key():
        return sync_personal_api(days=days, start_date_override=start_date_override, log=log,
                                 export_csv=export_csv)
    if not garmin_api.has_token():
        raise GarminAuthError("Not signed in to Garmin. Use Garmin -> Sign in to Garmin.")

    now_ts = int(time.time())
    pull_start, backfill_start = _compute_windows(days, start_date_override, now_ts, log)
    log(f"Pulling Garmin summaries uploaded {garmin_api._fmt_ts(pull_start)} .. {garmin_api._fmt_ts(now_ts)}")

    summaries_by_type, skipped = {}, []
    for stype in garmin_api.SUMMARY_TYPES:
        log(f" - {stype}")
        try:
            summaries_by_type[stype] = garmin_api.pull_summaries(stype, pull_start, now_ts, log=log)
        except GarminAuthError as e:
            # A single missing permission (e.g. user didn't share HRV) shouldn't abort the sync,
            # but if the core summaries are denied, the authorization itself is broken.
            if stype in ('dailies', 'sleeps'):
                raise
            log(f"   -> skipped ({e})")
            skipped.append(stype)

    # Persist raw payloads so additional metrics can be derived later.
    n_summaries = 0
    for stype, lst in summaries_by_type.items():
        for s in lst:
            n_summaries += 1
            sid = s.get('summaryId') or f"{_summary_date(stype, s)}-{s.get('startTimeInSeconds', '')}"
            db.save_garmin_raw_summary(stype, sid, _summary_date(stype, s), json.dumps(s))

    daily = build_daily_metrics(summaries_by_type)
    for d, metrics in daily.items():
        db.upsert_health_metrics(d, metrics)

    backfill_requested = 0
    if backfill_start is not None:
        bf_start = int(datetime.combine(backfill_start, datetime.min.time()).timestamp())
        bf_end = now_ts - PULL_LOOKBACK_DAYS * 86400 + 86400
        log(f"Requesting Garmin backfill from {backfill_start} (older than {PULL_LOOKBACK_DAYS} days)")
        for stype in garmin_api.SUMMARY_TYPES:
            if stype in skipped:
                continue
            try:
                backfill_requested += garmin_api.request_backfill(stype, bf_start, bf_end)
            except GarminAPIError as e:
                log(f"   -> backfill for {stype} failed: {e}")

    garmin_api.save_state(last_upload_end=now_ts, last_sync=datetime.now().isoformat(timespec='seconds'))

    csv_path = export_csv_snapshot(sorted(daily)) if export_csv and daily else None
    return {
        'days_updated': len(daily),
        'summaries': n_summaries,
        'backfill_requested': backfill_requested,
        'skipped': skipped,
        'csv_path': csv_path,
    }


# ---------------------------------------------------------------------------
# Garmin Connect Personal API (personal API key) - date-based endpoints
# ---------------------------------------------------------------------------

def _get(d, *keys):
    """Nested dict lookup that tolerates missing levels: _get(s, 'stress', 'avgLevel')."""
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _date_chunks(start, end, max_days):
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=max_days - 1), end)
        yield cur, chunk_end
        cur = chunk_end + timedelta(days=1)


def build_personal_daily_metrics(daily_summaries=(), sleeps=(), hrv_summaries=(), weights=(),
                                 fitness_age=None):
    """Map Personal API responses to {date: {health_metrics column: value}}.

    daily_summaries: UserDailySummaryV2DTO list   (usersummary-service/v2/dailysummaries)
    sleeps:          DailySleepDTO list            (sleep-service/sleep/dailySleepSummariesByDate)
    hrv_summaries:   HrvSummaryDTO list            (hrv-service/hrv/daily/{from}/{to})
    weights:         DailyWeightSummary list       (weight-service/weight/range/{start}/{end})
    fitness_age:     (date, FitnessAgeDTO) or None (fitnessage-service/fitnessage/v2/{date})
    """
    days = defaultdict(dict)

    for s in daily_summaries or []:
        d = s.get('calendarDate')
        if not d:
            continue
        m = days[d]
        m['steps'] = _get(s, 'movement', 'steps', 'value')
        m['distance_meters'] = _get(s, 'movement', 'steps', 'distanceInMeters')
        m['floors_climbed'] = _get(s, 'movement', 'floorsAscended', 'value')
        m['active_calories'] = _get(s, 'calories', 'burnedActive')
        m['resting_hr'] = _get(s, 'heartRate', 'restingValue')
        m['min_hr'] = _get(s, 'heartRate', 'minValue')
        m['max_hr'] = _get(s, 'heartRate', 'maxValue')
        stress = _get(s, 'stress', 'avgLevel')
        m['avg_stress'] = stress if stress is not None and stress >= 0 else None
        max_stress = _get(s, 'stress', 'maxLevel')
        m['max_stress'] = max_stress if max_stress is not None and max_stress >= 0 else None
        mod = _get(s, 'intensityMinutes', 'moderate')
        vig = _get(s, 'intensityMinutes', 'vigorous')
        m['moderate_intensity_minutes'] = mod
        m['vigorous_intensity_minutes'] = vig
        if mod is not None or vig is not None:
            m['intensity_minutes'] = (mod or 0) + 2 * (vig or 0)
        m['body_battery'] = _get(s, 'bodyBattery', 'minValue')   # legacy: lowest of the day
        m['body_battery_high'] = _get(s, 'bodyBattery', 'maxValue')
        m['body_battery_charged'] = _get(s, 'bodyBattery', 'chargedValue')
        m['body_battery_drained'] = _get(s, 'bodyBattery', 'drainedValue')
        hyd = _get(s, 'hydration', 'consumedInFractionalMl')
        m['hydration_ml'] = hyd if hyd else None  # 0 usually means "not logged"
        # All-day values; overridden below by the overnight averages when sleep data exists
        m['respiration'] = _get(s, 'respiration', 'avgValue')
        m['pulse_ox'] = _get(s, 'pulseOx', 'avgValue')

    for s in sleeps or []:
        d = s.get('calendarDate')
        if not d or not s.get('sleepTimeSeconds'):
            continue
        m = days[d]
        m['sleep_score'] = _get(s, 'sleepScores', 'overall', 'value')
        m['sleep_duration_seconds'] = s.get('sleepTimeSeconds')
        m['deep_sleep_seconds'] = s.get('deepSleepSeconds')
        m['light_sleep_seconds'] = s.get('lightSleepSeconds')
        m['rem_sleep_seconds'] = s.get('remSleepSeconds')
        m['awake_seconds'] = s.get('awakeSleepSeconds')
        if s.get('averageSpO2Value') is not None:
            m['pulse_ox'] = round(float(s['averageSpO2Value']), 1)
        if s.get('averageRespirationValue') is not None:
            m['respiration'] = round(float(s['averageRespirationValue']), 1)

    for h in hrv_summaries or []:
        d = h.get('calendarDate')
        if d:
            days[d]['hrv_last_night'] = h.get('lastNightAvg')
            days[d]['hrv_5min_high'] = h.get('lastNight5MinHigh')

    for w in weights or []:
        d = w.get('summaryDate')
        kg = _get(w, 'latestWeight', 'weight')
        if d and kg:
            # The spec says kilograms; Garmin Connect has historically used grams, so guard against it.
            days[d]['weight_kg'] = round(kg / 1000.0 if kg > 1000 else kg, 2)

    if fitness_age and fitness_age[1]:
        fa = fitness_age[1][0] if isinstance(fitness_age[1], list) and fitness_age[1] else fitness_age[1]
        if isinstance(fa, dict) and fa.get('fitnessAge') is not None:
            days[fitness_age[0]]['fitness_age'] = int(round(fa['fitnessAge']))

    result = {}
    for d, m in sorted(days.items()):
        m = {k: v for k, v in m.items() if v is not None}
        if m:
            m['data_source'] = 'garmin_personal_api'
            result[d] = m
    return result


def sync_personal_api(days=None, start_date_override=None, log=print, export_csv=True):
    """Sync using a personal API key (Garmin Connect Personal API). Same return shape as
    sync_health_data. Data is requested by calendar date, so no backfill is needed."""
    from . import database_manager as db

    end = date.today()
    if start_date_override:
        start = start_date_override
    elif days is not None:
        start = end - timedelta(days=int(days) - 1)
    else:
        most_recent = db.get_most_recent_health_date()
        n = find_missing_data_window(most_recent)
        start = end - timedelta(days=n - 1)
        log(f"Smart sync: last data in DB {most_recent}, fetching {n} days")
    log(f"Fetching Garmin Personal API data {start} .. {end}")

    raw, skipped = defaultdict(list), []

    def fetch(name, fn):
        try:
            fn()
        except GarminAuthError as e:
            if name in ('dailysummaries', 'sleep'):
                raise
            log(f"   -> {name} skipped ({e})")
            skipped.append(name)
        except GarminAPIError as e:
            log(f"   -> {name} failed ({e})")
            skipped.append(name)

    def daily():
        for a, b in _date_chunks(start, end, 365):
            data = garmin_api.personal_get('usersummary-service/v2/dailysummaries',
                                           {'startDate': a.isoformat(), 'endDate': b.isoformat()})
            raw['dailysummaries'].extend(_get(data, 'data') or [])

    def sleep():
        for a, b in _date_chunks(start, end, 31):
            data = garmin_api.personal_get('sleep-service/sleep/dailySleepSummariesByDate',
                                           {'startDate': a.isoformat(), 'endDate': b.isoformat()})
            raw['sleep'].extend(data or [])

    def hrv():
        for a, b in _date_chunks(start, end, 28):
            data = garmin_api.personal_get(f'hrv-service/hrv/daily/{a.isoformat()}/{b.isoformat()}')
            raw['hrv'].extend(_get(data, 'hrvSummaries') or [])

    def weight():
        for a, b in _date_chunks(start, end, 31):
            data = garmin_api.personal_get(f'weight-service/weight/range/{a.isoformat()}/{b.isoformat()}')
            raw['weight'].extend(_get(data, 'dailyWeightSummaries') or [])

    def fitness():
        data = garmin_api.personal_get(f'fitnessage-service/fitnessage/v2/{end.isoformat()}')
        if data:
            raw['fitnessage'].append(data)

    for name, fn in (('dailysummaries', daily), ('sleep', sleep), ('hrv', hrv),
                     ('weight', weight), ('fitnessage', fitness)):
        log(f" - {name}")
        fetch(name, fn)

    n_summaries = 0
    for name, items in raw.items():
        for i, item in enumerate(items):
            n_summaries += 1
            d = (item.get('calendarDate') or item.get('summaryDate') or end.isoformat()) \
                if isinstance(item, dict) else end.isoformat()
            db.save_garmin_raw_summary(f'personal_{name}', f'{d}#{i}' if name == 'fitnessage' else d,
                                       d, json.dumps(item))

    daily_metrics = build_personal_daily_metrics(
        raw['dailysummaries'], raw['sleep'], raw['hrv'], raw['weight'],
        (end.isoformat(), raw['fitnessage'][0]) if raw['fitnessage'] else None)
    for d, metrics in daily_metrics.items():
        db.upsert_health_metrics(d, metrics)

    garmin_api.save_state(last_sync=datetime.now().isoformat(timespec='seconds'))
    csv_path = export_csv_snapshot(sorted(daily_metrics)) if export_csv and daily_metrics else None
    return {
        'days_updated': len(daily_metrics),
        'summaries': n_summaries,
        'backfill_requested': 0,
        'skipped': skipped,
        'csv_path': csv_path,
    }


def export_csv_path():
    """Location of the CSV copy written after each sync (same file as the garth version)."""
    return os.path.join(os.path.expanduser("~"), "garmin_auto_export.csv")


def export_csv_snapshot(dates):
    """Write the given days from the DB to ~/garmin_auto_export.csv (legacy + new columns)."""
    from . import database_manager as db

    if not dates:
        return None
    cols = list(db.LEGACY_HEALTH_COLUMNS) + list(db.EXTENDED_HEALTH_COLUMNS)
    placeholders = ','.join('?' * len(dates))
    with db.db_connection() as conn:
        df = pd.read_sql_query(
            f"SELECT date, {', '.join(cols)} FROM health_metrics WHERE date IN ({placeholders}) ORDER BY date",
            conn, params=list(dates))

    def fmt_duration(sec):
        if pd.isna(sec):
            return None
        sec = int(sec)
        return f"{sec // 3600}h {(sec % 3600) // 60}m"

    df[COL_DURATION] = df['sleep_duration_seconds'].map(fmt_duration)
    df = df.drop(columns=['sleep_duration_seconds']).rename(columns={'date': COL_DATE, **LEGACY_CSV_COLUMNS})
    front = [COL_DATE, COL_SCORE, COL_DURATION]
    df = df[front + [c for c in df.columns if c not in front]]

    output_path = export_csv_path()
    df.to_csv(output_path, index=False)
    return output_path


def download_health_stats(days=None, start_date_override=None):
    """Backwards-compatible entry point: sync into the DB and return the CSV export path.

    Note: the data is already stored in the database when this returns; re-importing the
    CSV is not necessary.
    """
    result = sync_health_data(days=days, start_date_override=start_date_override, export_csv=True)
    return result['csv_path']


def ensure_oauth_session(on_tick=None):
    """Make sure an authorized Garmin API session exists, starting browser sign-in if needed.
    Returns True on success, False otherwise."""
    if garmin_api.uses_api_key():
        return garmin_api.is_configured()  # a personal API key needs no sign-in
    try:
        if garmin_api.has_token():
            garmin_api.get_access_token()  # refreshes if needed
            return True
    except GarminAPIError:
        pass
    try:
        garmin_api.authorize_interactive(on_tick=on_tick)
        return True
    except GarminAPIError as e:
        print("Garmin sign-in failed:", e)
        return False


if __name__ == "__main__":
    # CLI helper: python -m core.garmin_downloader [days]
    import sys
    from . import database_manager as _db
    _db.setup_database()
    if not garmin_api.has_token():
        garmin_api.authorize_interactive()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else None
    print(sync_health_data(days=n))
