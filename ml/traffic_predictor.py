"""
ml/traffic_predictor.py
========================
Predictive Traffic Signal Optimizer

Two responsibilities:
  1. predict_green_times_by_vehicles()  – instant green-time formula (used by
     compute_green_time in app.py, unchanged API)

  2. TrafficPredictor.tick() + proactive_adjustments() – called every second
     from the simulation loop to:
       a. Record a rolling history of vehicle counts per junction per road
       b. Compute per-road trend (vehicles/sec slope over last HISTORY_WINDOW s)
       c. Predict vehicle count LOOKAHEAD_SECS seconds in the future
       d. If a road is predicted to become congested (> CONGESTION_THRESHOLD)
          and its junction is currently red, pre-extend the upcoming green
          duration so it gets more time before the surge arrives
       e. Expose per-junction "predictions" dict for the dashboard API

Prediction model: linear extrapolation of the recent trend + a time-of-day
multiplier correction. Simple, interpretable, no training data needed, and
accurate enough for a 30-60 second lookahead.
"""

import math
import time
from collections import deque


# ── Tuning knobs ──────────────────────────────────────────────────────────────
HISTORY_WINDOW    = 30    # seconds of rolling history to keep per road
LOOKAHEAD_SECS    = 45    # how many seconds ahead to predict
CONGESTION_THRESH = 60    # predicted vehicles above this → proactive action
PROACTIVE_BONUS   = 8     # extra green seconds added proactively (capped at MAX_GREEN)
MIN_TREND_SAMPLES = 5     # need at least this many history points to trust the trend


class TrafficPredictor:
    """
    Stateful predictor — one instance shared across the app.
    app.py calls  predictor.tick(junction_state, hour, mult)  every second.
    """

    # ── Static green-time formula constants (unchanged) ───────────────────────
    BASE_GREEN     = 12.0
    VEH_SCALE      = 0.45
    PEAK_AM_BONUS  = 0.12
    PEAK_PM_BONUS  = 0.15
    MIN_GREEN      = 10
    MAX_GREEN      = 60

    def __init__(self):
        # history[jid][road_jid] = deque of (timestamp, vehicle_count)
        self._history = {}
        # predictions[jid] = {road_jid: {"current": int, "predicted": int,
        #                                 "trend": float, "action": str}}
        self.predictions = {}
        self._last_tick  = 0.0

    # ── Public: called every simulation second ────────────────────────────────
    def tick(self, junction_state: dict, hour: int, mult: float):
        """
        Record current vehicle counts, compute trends, and return a dict of
        proactive green-time adjustments:
          { jid: { road_jid: extra_seconds_to_add } }
        """
        now = time.time()
        if now - self._last_tick < 0.9:   # guard against double-calls
            return {}
        self._last_tick = now

        adjustments  = {}
        predictions  = {}

        for jid, st in junction_state.items():
            roads = st.get("roads", [])
            if not roads:
                continue

            jid_hist = self._history.setdefault(jid, {})
            jid_pred = {}

            for road in roads:
                v = st["road_vehicles"].get(road, 0)

                # 1. Record history
                hist = jid_hist.setdefault(road, deque(maxlen=HISTORY_WINDOW * 2))
                hist.append((now, v))

                # 2. Compute trend
                trend    = self._compute_trend(hist, now)
                predicted = self._predict(v, trend, LOOKAHEAD_SECS, hour, mult)

                # 3. Classify action
                is_active = (roads.index(road) == st["active_idx"])
                phase     = st["phase"]

                action = "normal"
                if predicted >= CONGESTION_THRESH and not is_active and phase != "red":
                    action = "predicted_congestion"
                elif predicted >= CONGESTION_THRESH and is_active:
                    action = "currently_heavy"
                elif predicted < 20:
                    action = "clearing"

                jid_pred[road] = {
                    "current":   v,
                    "predicted": predicted,
                    "trend":     round(trend, 2),
                    "action":    action,
                }

                # 4. Proactive adjustment:
                # If a non-active road is predicted to hit CONGESTION_THRESH
                # within LOOKAHEAD_SECS and we can still adjust the next
                # green phase, add extra seconds to the upcoming green.
                if (action == "predicted_congestion"
                        and jid not in adjustments):
                    adjustments[jid] = {
                        "road": road,
                        "predicted_vehicles": predicted,
                        "extra_green_secs": PROACTIVE_BONUS,
                    }

            predictions[jid] = jid_pred

        self.predictions = predictions
        return adjustments

    # ── Public: instant green-time formula (used by compute_green_time) ───────
    def predict_green_times_by_vehicles(self, vehicles: int, hour: int) -> tuple:
        """
        Returns (green_primary, green_secondary) in seconds.
        Same formula as before — kept for API compatibility.
        """
        peak_am = 1.0 if 8  <= hour <= 10 else 0.0
        peak_pm = 1.0 if 17 <= hour <= 20 else 0.0

        score = (
            self.BASE_GREEN
            + self.VEH_SCALE      * vehicles
            + self.PEAK_AM_BONUS  * peak_am * vehicles
            + self.PEAK_PM_BONUS  * peak_pm * vehicles
        )
        green_primary = int(self._clamp(score, self.MIN_GREEN, self.MAX_GREEN))

        # Secondary gets the remaining capacity
        opposite_veh    = max(0, 80 - vehicles)
        score_sec       = self.BASE_GREEN + self.VEH_SCALE * opposite_veh
        green_secondary = int(self._clamp(score_sec, self.MIN_GREEN, self.MAX_GREEN))

        return green_primary, green_secondary

    def predict_green_times(self, density: int, hour: int) -> tuple:
        """Legacy alias."""
        return self.predict_green_times_by_vehicles(round(density * 1.2), hour)

    def batch_predict(self, junction_vehicles: dict, hour: int) -> dict:
        return {jid: self.predict_green_times_by_vehicles(veh, hour)
                for jid, veh in junction_vehicles.items()}

    # ── Prediction API for dashboard ─────────────────────────────────────────
    def get_junction_prediction(self, jid: str) -> dict:
        """Return latest prediction data for a junction (for /api/state)."""
        return self.predictions.get(jid, {})

    # ── Internal helpers ──────────────────────────────────────────────────────
    def _compute_trend(self, hist: deque, now: float) -> float:
        """
        vehicles/second slope over the last HISTORY_WINDOW seconds.
        Positive = queue growing, negative = queue shrinking.
        Returns 0.0 if not enough data.
        """
        cutoff = now - HISTORY_WINDOW
        pts = [(t, v) for t, v in hist if t >= cutoff]
        if len(pts) < MIN_TREND_SAMPLES:
            return 0.0
        # Simple linear regression slope
        n   = len(pts)
        sx  = sum(t for t, _ in pts)
        sy  = sum(v for _, v in pts)
        sxy = sum(t * v for t, v in pts)
        sxx = sum(t * t for t, _ in pts)
        denom = n * sxx - sx * sx
        if abs(denom) < 1e-9:
            return 0.0
        return (n * sxy - sx * sy) / denom

    def _predict(self, current: int, trend: float, lookahead: int,
                 hour: int, mult: float) -> int:
        """
        Predict vehicle count `lookahead` seconds from now.
        Linear extrapolation from current count + trend,
        adjusted slightly by time-of-day multiplier.
        """
        raw = current + trend * lookahead
        # Time-of-day correction: during peak hours queues grow faster
        # during off-peak they decay faster. Moderate the raw prediction.
        correction_factor = 0.85 + 0.30 * mult   # 0.85 (night) → 1.15 (peak)
        predicted = raw * correction_factor
        return max(0, int(predicted))

    @staticmethod
    def _clamp(val, lo, hi):
        return max(lo, min(hi, val))
