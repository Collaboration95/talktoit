#!/usr/bin/env python3
"""
Stream the reduced Apple Health export and produce one compact chart_data.json
with representative datasets for the chart-library comparison gallery.

Usage:
    python3 extract_data.py

Input  : ../../personal-assets/test-data/export_last6mo.xml  (~597 MB)
Output : ./chart_data.json  (gitignored)
"""
import json
import os
from collections import defaultdict
from datetime import datetime, date

from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
XML_PATH = os.path.normpath(
    os.path.join(HERE, "..", "..", "personal-assets", "test-data", "export_last6mo.xml")
)
OUT_PATH = os.path.join(HERE, "chart_data.json")

# ---- accumulators ----------------------------------------------------------
resting_hr = {}                      # date -> value (last wins; one per day)
hrv = {}                             # date -> value
steps_by_day = defaultdict(float)    # date -> summed steps
workouts = []                        # list of dicts
sport_counts = defaultdict(int)      # activity type -> count
weekly_sport = defaultdict(lambda: defaultdict(float))  # week -> sport -> minutes
activity_summaries = []              # list of dicts (pick one later)


def day_of(attr):
    """Extract YYYY-MM-DD from an Apple Health datetime attribute."""
    if not attr:
        return None
    return attr[:10]


def iso_week(d):
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def clean_sport(raw):
    return raw.replace("HKWorkoutActivityType", "") if raw else "Other"


# ---- workout child-stat helpers --------------------------------------------
DIST_TYPES = {
    "HKQuantityTypeIdentifierDistanceWalkingRunning",
    "HKQuantityTypeIdentifierDistanceCycling",
    "HKQuantityTypeIdentifierDistanceSwimming",
    "HKQuantityTypeIdentifierDistancePaddleSports",
}

context = etree.iterparse(XML_PATH, events=("end",), tag=("Record", "Workout", "ActivitySummary"))

n_records = 0
for _, elem in context:
    tag = elem.tag

    if tag == "Record":
        n_records += 1
        rtype = elem.get("type")
        if rtype == "HKQuantityTypeIdentifierRestingHeartRate":
            d = day_of(elem.get("startDate"))
            if d:
                resting_hr[d] = round(float(elem.get("value")), 1)
        elif rtype == "HKQuantityTypeIdentifierHeartRateVariabilitySDNN":
            d = day_of(elem.get("startDate"))
            if d:
                hrv[d] = round(float(elem.get("value")), 1)
        elif rtype == "HKQuantityTypeIdentifierStepCount":
            d = day_of(elem.get("startDate"))
            if d:
                try:
                    steps_by_day[d] += float(elem.get("value"))
                except (TypeError, ValueError):
                    pass

    elif tag == "Workout":
        sport = clean_sport(elem.get("workoutActivityType"))
        start = elem.get("startDate")
        d = day_of(start)
        try:
            duration = float(elem.get("duration"))
        except (TypeError, ValueError):
            duration = 0.0

        avg_hr = None
        distance_km = None
        for stat in elem.iterchildren("WorkoutStatistics"):
            stype = stat.get("type")
            if stype == "HKQuantityTypeIdentifierHeartRate" and stat.get("average"):
                avg_hr = round(float(stat.get("average")), 1)
            elif stype in DIST_TYPES and stat.get("sum"):
                val = float(stat.get("sum"))
                # swimming distance is in meters; convert to km
                if stype == "HKQuantityTypeIdentifierDistanceSwimming":
                    val = val / 1000.0
                distance_km = round(val, 2)

        workouts.append({
            "date": d,
            "type": sport,
            "durationMin": round(duration, 1),
            "avgHr": avg_hr,
            "distanceKm": distance_km,
        })
        sport_counts[sport] += 1
        if d:
            try:
                wk = iso_week(date.fromisoformat(d))
                weekly_sport[wk][sport] += duration
            except ValueError:
                pass

    elif tag == "ActivitySummary":
        activity_summaries.append({
            "date": elem.get("dateComponents"),
            "move": float(elem.get("activeEnergyBurned") or 0),
            "moveGoal": float(elem.get("activeEnergyBurnedGoal") or 0),
            "exercise": float(elem.get("appleExerciseTime") or 0),
            "exerciseGoal": float(elem.get("appleExerciseTimeGoal") or 0),
            "stand": float(elem.get("appleStandHours") or 0),
            "standGoal": float(elem.get("appleStandHoursGoal") or 0),
        })

    # free memory
    elem.clear()
    while elem.getprevious() is not None:
        del elem.getparent()[0]

# ---- post-process ----------------------------------------------------------
restingHrDaily = [{"date": d, "value": v} for d, v in sorted(resting_hr.items())]
hrvDaily = [{"date": d, "value": v} for d, v in sorted(hrv.items())]
stepsDaily = [{"date": d, "steps": round(v)} for d, v in sorted(steps_by_day.items())]

sportBreakdown = sorted(
    [{"type": t, "count": c} for t, c in sport_counts.items()],
    key=lambda x: x["count"], reverse=True,
)

# top ~5 sports by total minutes for the stacked weekly volume
total_min = defaultdict(float)
for wk, sports in weekly_sport.items():
    for s, m in sports.items():
        total_min[s] += m
top_sports = [s for s, _ in sorted(total_min.items(), key=lambda x: x[1], reverse=True)[:5]]

weeklyVolumeBySport = []
for wk in sorted(weekly_sport.keys()):
    row = {"week": wk}
    for s in top_sports:
        row[s] = round(weekly_sport[wk].get(s, 0.0), 1)
    weeklyVolumeBySport.append(row)

# pick a representative recent day with non-zero rings
activity_summaries = [a for a in activity_summaries if a["date"]]
activity_summaries.sort(key=lambda a: a["date"])
ring = None
for a in reversed(activity_summaries):
    if a["move"] > 0 and a["exercise"] > 0:
        ring = a
        break
if ring is None and activity_summaries:
    ring = activity_summaries[-1]

activityRings = None
if ring:
    activityRings = {
        "date": ring["date"],
        "move": round(ring["move"]),
        "moveGoal": round(ring["moveGoal"]),
        "exercise": round(ring["exercise"]),
        "exerciseGoal": round(ring["exerciseGoal"]),
        "stand": round(ring["stand"]),
        "standGoal": round(ring["standGoal"]),
    }

# trim workouts to those with a date; keep order by date
workouts = [w for w in workouts if w["date"]]
workouts.sort(key=lambda w: w["date"])

data = {
    "meta": {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "source": "Apple Health export_last6mo.xml",
        "range": "2025-12-17 .. 2026-06-17",
        "topSports": top_sports,
    },
    "restingHrDaily": restingHrDaily,
    "stepsDaily": stepsDaily,
    "hrvDaily": hrvDaily,
    "workouts": workouts,
    "sportBreakdown": sportBreakdown,
    "weeklyVolumeBySport": weeklyVolumeBySport,
    "activityRings": activityRings,
}

with open(OUT_PATH, "w") as f:
    json.dump(data, f, separators=(",", ":"))

# ---- summary ---------------------------------------------------------------
print(f"Parsed {n_records:,} <Record> elements")
print("Dataset summary:")
print(f"  restingHrDaily      : {len(restingHrDaily)} days")
print(f"  stepsDaily          : {len(stepsDaily)} days")
print(f"  hrvDaily            : {len(hrvDaily)} days")
print(f"  workouts            : {len(workouts)}")
print(f"  sportBreakdown      : {len(sportBreakdown)} sports")
print(f"  weeklyVolumeBySport : {len(weeklyVolumeBySport)} weeks, top sports={top_sports}")
print(f"  activityRings       : {activityRings['date'] if activityRings else None}")
size = os.path.getsize(OUT_PATH)
print(f"Wrote {OUT_PATH} ({size/1024:.1f} KB)")
