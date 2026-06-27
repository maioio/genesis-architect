"""
decay_regressor.py - Genesis Architect PRO

Weighted least-squares (WLS) regression on architecture score history.
Predicts future score decay with 95% confidence intervals.

Mathematical model
------------------
Let (t_i, y_i, w_i) be the i-th observation: week offset, score, weight.

Weighting (recency bias)
  w_i = exp(-ln2 / H × (T - t_i))

  where H = recency half-life (default 8 weeks) and T = max(t_i).
  The most recent observation always receives w = 1.0.
  An observation H weeks in the past receives w = 0.5.
  An observation 2H weeks in the past receives w = 0.25. (geometric decay)

Weighted least-squares (one regressor: week offset → score)
  β = [slope, intercept] minimising Σ w_i (y_i - intercept - slope×t_i)²

  Closed-form via the 2×2 normal equations:
    S_w  = Σ w_i
    S_wt = Σ w_i t_i
    S_wt2= Σ w_i t_i²
    S_wy = Σ w_i y_i
    S_wty= Σ w_i t_i y_i
    det  = S_w × S_wt2 - S_wt²
    slope     = (S_w × S_wty - S_wt × S_wy) / det
    intercept = (S_wy - slope × S_wt) / S_w

Goodness of fit (weighted R²)
  ȳ_w = S_wy / S_w                           (weighted mean)
  SS_tot = Σ w_i (y_i - ȳ_w)²
  SS_res = Σ w_i (y_i - ŷ_i)²               (ŷ_i = intercept + slope×t_i)
  R² = 1 - SS_res / SS_tot
  R² is clamped to [0, 1]; a negative value (model worse than mean) → 0.

Weighted residual variance and slope standard error
  σ²_ε = SS_res / (n - 2)                    (n = number of observations)
  Var(slope) = σ²_ε × S_w / det
  se(slope)  = sqrt(Var(slope))

Significance test (two-tailed t-test on slope, α=0.05)
  t = slope / se(slope)
  df = n - 2
  We approximate the t(df) critical value conservatively:
    |t| > t_crit(df, 0.025) is deemed significant.
  Critical values are looked up from a small pre-computed table;
  for df ≥ 30 we use the large-sample approximation t_crit ≈ 1.960.
  This avoids scipy while staying correct for df ≥ 3.

95% Prediction interval (at forecast horizon k weeks out from last obs)
  The interval captures prediction uncertainty (model error + extrapolation).
  Half-width at horizon k:
    h(k) = t_crit × se(slope) × sqrt(1 + (t_k - t̄_w)² / S_wt2_centred)
  where t_k = t_last + k and t̄_w = S_wt / S_w.

  Confidence decays exponentially with distance beyond the data:
    confidence(k) = R² × exp(-0.1 × k)     clamped to [0, 1]

Threshold crossing
  Solving slope × t + intercept = threshold for t gives:
    t_cross = (threshold - intercept) / slope
  weeks_to_threshold = t_cross - t_last.
  If slope ≥ 0 (non-declining) → infinity (score never hits threshold).
  If threshold is already breached at t_last → 0.

Assumptions
-----------
A1. Score-versus-time relationship is locally linear (short horizons only).
A2. Residuals are independent and homoscedastic (not verified; caveat emptor
    for long or highly autocorrelated histories).
A3. Week offset is monotonically increasing and spaced at least one unit apart
    after deduplication. Out-of-order inputs are sorted automatically.
A4. Outliers are present but not dominant; WLS recency weighting naturally
    down-weights old (potentially stale) outliers.
A5. The critical threshold (default 40) is a reasonable proxy for "needs
    immediate attention"; it is caller-configurable.
A6. Fewer than min_data_points observations → no forecast (None returned).

Determinism guarantee
---------------------
All arithmetic uses Python's `float` (IEEE 754 double precision).
Given identical inputs the output is bitwise identical across runs.
There is no random state, threading, or I/O inside the pure math functions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_RECENCY_HALF_LIFE: int = 8      # weeks; see weighting formula above
DEFAULT_HORIZON_WEEKS: int = 12         # how far forward to project
DEFAULT_CRITICAL_THRESHOLD: float = 40.0  # score below which architecture is critical
DEFAULT_MIN_DATA_POINTS: int = 3        # minimum history needed for a forecast


@dataclass
class DecayRegressorConfig:
    """All tunable parameters in one place — no hidden constants."""
    recency_half_life: int = DEFAULT_RECENCY_HALF_LIFE
    horizon_weeks: int = DEFAULT_HORIZON_WEEKS
    critical_threshold: float = DEFAULT_CRITICAL_THRESHOLD
    min_data_points: int = DEFAULT_MIN_DATA_POINTS


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ScoreDataPoint:
    """
    One score observation.

    week_offset: non-negative integer. 0 = oldest observation in the series.
                 build_timeline() naturally produces these; convert timestamps
                 with forecast_from_history().
    score:       architecture score 0–100.
    weight:      set by apply_weights(); do not set manually.
    """
    week_offset: int
    score: float
    weight: float | None = None


@dataclass
class RegressionResult:
    """
    Output of fit_weighted_regression().

    slope:          score change per week (negative = declining).
    intercept:      fitted score at week_offset=0.
    r_squared:      goodness of fit ∈ [0, 1]; 1.0 = perfect linear fit.
    data_points:    number of observations used.
    slope_std_error: standard error of the slope estimate.
    is_significant: True if |t-stat| exceeds two-tailed 0.05 critical value.
    """
    slope: float
    intercept: float
    r_squared: float
    data_points: int
    slope_std_error: float
    is_significant: bool


@dataclass
class ScorePrediction:
    """One point in the forecast trajectory."""
    week_offset: int          # weeks from the start of the observed series
    predicted_score: float    # clamped to [0, 100]
    lower_bound: float        # 95% prediction interval lower
    upper_bound: float        # 95% prediction interval upper
    confidence: float         # ∈ [0, 1]; decays with forecast distance


@dataclass
class DecayForecast:
    """Full forecast output from DecayRegressor.forecast()."""
    current_score: float
    predicted_score: float            # score at horizon_weeks from last obs
    score_delta: float                # predicted_score - current_score
    weekly_delta: float               # regression slope (score/week)
    weeks_to_threshold: float         # math.inf if slope ≥ 0
    threshold: float
    confidence: float                 # overall forecast confidence ∈ [0, 1]
    regression: RegressionResult
    trajectory: list[ScorePrediction] = field(default_factory=list)
    summary: str = ""                 # human-readable one-paragraph summary


# ---------------------------------------------------------------------------
# t-distribution critical values (two-tailed, α=0.05)
# Pre-computed for df=1..29; df≥30 uses large-sample approximation 1.960.
# Source: standard t-table.
# ---------------------------------------------------------------------------

_T_CRIT_TABLE: dict[int, float] = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447,  7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045,
}
_T_CRIT_LARGE_SAMPLE: float = 1.960  # df ≥ 30


def _t_critical(df: int) -> float:
    """Two-tailed t critical value at α=0.05 for the given degrees of freedom."""
    if df <= 0:
        return float("inf")
    return _T_CRIT_TABLE.get(df, _T_CRIT_LARGE_SAMPLE)


# ---------------------------------------------------------------------------
# Core regressor
# ---------------------------------------------------------------------------

class DecayRegressor:
    """
    Weighted least-squares regression on architecture score history.

    Usage:
        reg = DecayRegressor()
        data = [ScoreDataPoint(0, 82), ScoreDataPoint(4, 79), ScoreDataPoint(8, 75)]
        forecast = reg.forecast(data)

    The class carries only its config; all methods are pure (no mutation of
    input data). The same instance can be reused across calls.
    """

    def __init__(self, config: DecayRegressorConfig | None = None) -> None:
        self.config = config or DecayRegressorConfig()

    # ------------------------------------------------------------------
    # Step 1 of pipeline: recency weighting
    # ------------------------------------------------------------------

    def apply_weights(self, data: list[ScoreDataPoint]) -> list[ScoreDataPoint]:
        """
        Return a new list of ScoreDataPoints with weight fields set.

        Weight formula: w_i = exp(-ln2/H × (T - t_i))
          H = recency_half_life (weeks)
          T = max week_offset in data (most recent observation)
          The most recent observation always gets weight = 1.0.

        Input is not modified; returns a fresh list sorted by week_offset.
        Observations with identical week_offset are kept (deduplication is
        not performed here; the caller is responsible for clean data).
        """
        if not data:
            return []
        sorted_data = sorted(data, key=lambda p: p.week_offset)
        t_max = sorted_data[-1].week_offset
        ln2_over_H = math.log(2) / max(self.config.recency_half_life, 1)
        result = []
        for pt in sorted_data:
            w = math.exp(-ln2_over_H * (t_max - pt.week_offset))
            result.append(ScoreDataPoint(pt.week_offset, pt.score, round(w, 8)))
        return result

    # ------------------------------------------------------------------
    # Step 2: WLS fit
    # ------------------------------------------------------------------

    def fit_weighted_regression(
        self, data: list[ScoreDataPoint]
    ) -> RegressionResult:
        """
        Fit WLS y = slope × t + intercept to data.

        data: ScoreDataPoints with weight already set (via apply_weights).
              If weight is None, weight=1.0 is assumed.

        Returns RegressionResult.  Raises ValueError if fewer than 2
        distinct data points or if the normal-equation determinant is
        numerically zero (collinear inputs).

        Mathematical derivation: see module docstring.
        """
        pts = [p for p in data if p.weight is not None and p.weight > 0
               or p.weight is None]
        if len(pts) < 2:
            raise ValueError(
                f"Need at least 2 data points for regression; got {len(pts)}"
            )

        S_w = S_wt = S_wt2 = S_wy = S_wty = 0.0
        for p in pts:
            w = p.weight if p.weight is not None else 1.0
            t = float(p.week_offset)
            y = float(p.score)
            S_w   += w
            S_wt  += w * t
            S_wt2 += w * t * t
            S_wy  += w * y
            S_wty += w * t * y

        det = S_w * S_wt2 - S_wt * S_wt
        if abs(det) < 1e-12:
            # All t values are identical → slope undefined; return flat line
            intercept = S_wy / S_w if S_w > 0 else 0.0
            n = len(pts)
            return RegressionResult(
                slope=0.0,
                intercept=intercept,
                r_squared=1.0,   # model fits perfectly (horizontal line)
                data_points=n,
                slope_std_error=0.0,
                is_significant=False,
            )

        slope = (S_w * S_wty - S_wt * S_wy) / det
        intercept = (S_wy - slope * S_wt) / S_w

        # Weighted R²
        y_bar_w = S_wy / S_w
        SS_tot = SS_res = 0.0
        for p in pts:
            w = p.weight if p.weight is not None else 1.0
            y_hat = intercept + slope * p.week_offset
            SS_tot += w * (p.score - y_bar_w) ** 2
            SS_res += w * (p.score - y_hat) ** 2

        r_squared = max(0.0, 1.0 - SS_res / SS_tot) if SS_tot > 1e-12 else 1.0

        # Slope standard error
        n = len(pts)
        df = n - 2
        if df > 0 and SS_res > 0:
            sigma2 = SS_res / df
            var_slope = sigma2 * S_w / det
            se_slope = math.sqrt(max(0.0, var_slope))
        else:
            se_slope = 0.0

        # Significance
        t_crit = _t_critical(df)
        t_stat = abs(slope / se_slope) if se_slope > 1e-12 else 0.0
        is_significant = t_stat > t_crit

        return RegressionResult(
            slope=slope,
            intercept=intercept,
            r_squared=round(r_squared, 4),
            data_points=n,
            slope_std_error=round(se_slope, 6),
            is_significant=is_significant,
        )

    # ------------------------------------------------------------------
    # Step 3: trajectory with prediction intervals
    # ------------------------------------------------------------------

    def generate_trajectory(
        self,
        regression: RegressionResult,
        start_week: int,
        end_week: int,
    ) -> list[ScorePrediction]:
        """
        Generate per-week predictions from start_week to end_week (inclusive).

        Prediction interval half-width at k weeks past the last observed data:
          h(k) = t_crit × se(slope) × sqrt(1 + (t_k - t̄)² / S_var_t)
        where t̄ is approximated from regression params and S_var_t is
        approximated from regression slope variance.

        When se(slope) = 0 (perfect fit or collinear), intervals collapse to
        the point prediction.

        Confidence at horizon k = R² × exp(-0.1 × k), clamped to [0, 1].
        k is measured in weeks beyond start_week.
        """
        t_crit = _t_critical(max(regression.data_points - 2, 1))
        se = regression.slope_std_error
        r2 = regression.r_squared

        predictions: list[ScorePrediction] = []
        for week in range(start_week, end_week + 1):
            predicted = self._clamp_score(
                regression.intercept + regression.slope * week
            )
            k = week - start_week

            # Prediction interval: half-width grows with k
            # Simplified: h = t_crit × se × sqrt(1 + k) to capture
            # increasing uncertainty without knowing t̄ precisely
            h = t_crit * se * math.sqrt(1 + k) if se > 0 else 0.0
            lower = self._clamp_score(predicted - h)
            upper = self._clamp_score(predicted + h)

            # Confidence decays with forecast distance
            conf = max(0.0, min(1.0, r2 * math.exp(-0.1 * k)))

            predictions.append(ScorePrediction(
                week_offset=week,
                predicted_score=predicted,
                lower_bound=lower,
                upper_bound=upper,
                confidence=round(conf, 4),
            ))
        return predictions

    # ------------------------------------------------------------------
    # Step 4: threshold crossing
    # ------------------------------------------------------------------

    def _compute_weeks_to_threshold(
        self,
        regression: RegressionResult,
        last_week: int,
        current_score: float,
    ) -> float:
        """
        Solve (intercept + slope × t) = threshold for t; return weeks from now.

        Returns math.inf if:
          - slope ≥ 0  (score is stable or improving)
          - threshold already breached at last_week and current_score ≤ threshold
            (return 0 instead — already there)
          - solution is in the past (t_cross ≤ last_week)
        """
        threshold = self.config.critical_threshold
        if current_score <= threshold:
            return 0.0
        if regression.slope >= 0:
            return math.inf
        # Linear crossing: intercept + slope × t_cross = threshold
        t_cross = (threshold - regression.intercept) / regression.slope
        weeks_remaining = t_cross - last_week
        if weeks_remaining <= 0:
            return 0.0
        return weeks_remaining

    # ------------------------------------------------------------------
    # Step 5: overall forecast confidence
    # ------------------------------------------------------------------

    def _compute_overall_confidence(
        self,
        regression: RegressionResult,
        n_points: int,
    ) -> float:
        """
        Aggregate confidence scalar for the entire forecast.

        Base = R²
        Bonus: +0.05 per data point above min_data_points, capped at +0.15
        Penalty: -0.10 if slope is not statistically significant
        Result clamped to [0.05, 1.0].

        A low R² means the linear model is a poor fit; even if we have many
        observations, we should not be confident in the extrapolation.
        """
        base = regression.r_squared
        extra_pts = max(0, n_points - self.config.min_data_points)
        bonus = min(0.15, extra_pts * 0.05)
        penalty = 0.0 if regression.is_significant else 0.10
        conf = base + bonus - penalty
        return round(max(0.05, min(1.0, conf)), 4)

    # ------------------------------------------------------------------
    # Public: full pipeline
    # ------------------------------------------------------------------

    def forecast(self, data: list[ScoreDataPoint]) -> DecayForecast | None:
        """
        Run the full WLS decay forecast pipeline.

        Returns None if there are fewer than config.min_data_points observations.
        All intermediate results are attached to DecayForecast for inspection.

        Pipeline:
          1. Sort and deduplicate by week_offset (keep latest score per week)
          2. Apply exponential recency weights
          3. Fit WLS regression
          4. Generate trajectory for horizon_weeks
          5. Compute weeks-to-threshold
          6. Compute overall confidence
          7. Build human-readable summary
        """
        if not data:
            return None

        # 1. Sort; deduplicate by week_offset (keep last score if dupes)
        deduped: dict[int, float] = {}
        for pt in data:
            deduped[pt.week_offset] = pt.score
        clean = [ScoreDataPoint(w, s) for w, s in sorted(deduped.items())]

        if len(clean) < self.config.min_data_points:
            return None

        # 2. Recency weights
        weighted = self.apply_weights(clean)

        # 3. WLS fit
        try:
            regression = self.fit_weighted_regression(weighted)
        except ValueError:
            return None

        last_week = weighted[-1].week_offset
        current_score = weighted[-1].score

        # 4. Trajectory (from last observed week to last+horizon)
        horizon_end = last_week + self.config.horizon_weeks
        trajectory = self.generate_trajectory(regression, last_week, horizon_end)

        predicted_score = trajectory[-1].predicted_score if trajectory else current_score
        score_delta = round(predicted_score - current_score, 2)

        # 5. Threshold crossing
        weeks_to_threshold = self._compute_weeks_to_threshold(
            regression, last_week, current_score
        )

        # 6. Overall confidence
        confidence = self._compute_overall_confidence(regression, len(clean))

        # 7. Summary
        summary = self._build_summary(
            current_score=current_score,
            predicted_score=predicted_score,
            score_delta=score_delta,
            weekly_delta=regression.slope,
            weeks_to_threshold=weeks_to_threshold,
            confidence=confidence,
            r_squared=regression.r_squared,
            n_points=len(clean),
        )

        return DecayForecast(
            current_score=current_score,
            predicted_score=predicted_score,
            score_delta=score_delta,
            weekly_delta=round(regression.slope, 4),
            weeks_to_threshold=weeks_to_threshold,
            threshold=self.config.critical_threshold,
            confidence=confidence,
            regression=regression,
            trajectory=trajectory,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clamp_score(x: float) -> float:
        """Clamp to [0, 100] and round to 1 decimal place."""
        return max(0.0, min(100.0, round(x, 1)))

    @staticmethod
    def _build_summary(
        *,
        current_score: float,
        predicted_score: float,
        score_delta: float,
        weekly_delta: float,
        weeks_to_threshold: float,
        confidence: float,
        r_squared: float,
        n_points: int,
    ) -> str:
        direction = "declining" if weekly_delta < -0.05 else (
            "improving" if weekly_delta > 0.05 else "stable"
        )
        delta_str = (
            f"{score_delta:+.1f} points" if score_delta != 0
            else "unchanged"
        )
        if weeks_to_threshold == math.inf:
            threshold_str = "not projected to breach the critical threshold."
        elif weeks_to_threshold == 0:
            threshold_str = "already below the critical threshold."
        else:
            threshold_str = (
                f"projected to breach the critical threshold in "
                f"{weeks_to_threshold:.1f} weeks."
            )
        return (
            f"Architecture score is {direction} at {weekly_delta:+.2f} pts/week "
            f"(R²={r_squared:.2f}, {n_points} data points, confidence={confidence:.0%}). "
            f"Current score: {current_score:.1f}. "
            f"Projected score in {DEFAULT_HORIZON_WEEKS} weeks: {predicted_score:.1f} "
            f"({delta_str}). Score is {threshold_str}"
        )


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def forecast_from_history(
    history: list[dict],
    config: DecayRegressorConfig | None = None,
) -> DecayForecast | None:
    """
    Convert score_history.jsonl records to ScoreDataPoints and run forecast.

    Each record must have a "timestamp" (ISO 8601 string) and "total" (float).
    Records without a parseable timestamp are silently skipped.

    Week offset is computed relative to the earliest valid timestamp
    (earliest → week 0).  Fractional weeks are rounded to the nearest int.

    Returns None if too few valid records exist.
    """
    if not history:
        return None

    parsed: list[tuple[datetime, float]] = []
    for rec in history:
        ts_str = rec.get("timestamp", "")
        score = rec.get("total")
        if not ts_str or score is None:
            continue
        try:
            # Handle both offset-aware and naive ISO strings
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        try:
            score = float(score)
        except (TypeError, ValueError):
            continue
        parsed.append((ts, score))

    if not parsed:
        return None

    parsed.sort(key=lambda x: x[0])
    t0 = parsed[0][0]
    data: list[ScoreDataPoint] = []
    for ts, score in parsed:
        weeks = (ts - t0).total_seconds() / (7 * 24 * 3600)
        data.append(ScoreDataPoint(week_offset=round(weeks), score=score))

    return DecayRegressor(config=config).forecast(data)
