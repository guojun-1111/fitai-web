// ========== V21: Bayesian Changepoint Detector (CUSUM + EWMA) ==========
// Online fatigue detection for pose quality time series.
// Pure JS, no dependencies. Runs per-rep in the browser detection loop.

export class ChangepointDetector {
  constructor(options = {}) {
    this.threshold = options.threshold || 3.0;   // CUSUM alarm threshold
    this.drift = options.drift || 0.5;           // allowable drift k (in σ units)
    this.alpha = options.alpha || 0.2;           // EWMA smoothing factor
    this.warmup = options.warmup || 5;           // min observations before alarming
    this.alarmPersist = options.alarmPersist || 3; // consecutive alarms to go critical

    this.reset();
  }

  reset() {
    this.ewma = null;          // EWMA baseline
    this.mad = 0;              // running MAD (robust σ estimate)
    this.cusumPos = 0;         // CUSUM for downward quality (positive deviation of error)
    this.cusumNeg = 0;         // CUSUM for upward quality
    this.n = 0;                // observation count
    this.alarmCount = 0;       // consecutive alarms
    this.recentErrors = [];    // for MAD computation (last 20)
    this.state = 'normal';     // 'normal' | 'warning' | 'critical'
  }

  // x_t = form quality score (0-100, higher = better)
  // Returns { alarm: bool, state: 'normal'|'warning'|'critical', score: number, cusum: number }
  update(qualityScore) {
    this.n++;

    // Initialize or update EWMA
    if (this.ewma === null) {
      this.ewma = qualityScore;
      return { alarm: false, state: 'normal', score: qualityScore, cusum: 0 };
    }
    this.ewma = this.alpha * qualityScore + (1 - this.alpha) * this.ewma;

    // Track recent errors for MAD
    var error = this.ewma - qualityScore; // positive when quality drops below EWMA
    this.recentErrors.push(Math.abs(error));
    if (this.recentErrors.length > 20) this.recentErrors.shift();

    // Robust σ: 1.4826 * median absolute deviation
    this.mad = this._computeMAD();

    var sigma = Math.max(this.mad, 0.5); // floor to avoid division by zero

    // Standardized error
    var z = error / sigma;

    // CUSUM for quality degradation (error > 0 means quality below baseline)
    if (z > 0) {
      this.cusumPos = Math.max(0, this.cusumPos + z - this.drift);
    } else {
      // Allow recovery when quality improves
      this.cusumPos = Math.max(0, this.cusumPos - 0.3);
    }

    // Track negative CUSUM too (quality improving, for symmetry)
    if (z < 0) {
      this.cusumNeg = Math.max(0, this.cusumNeg + (-z) - this.drift);
    } else {
      this.cusumNeg = Math.max(0, this.cusumNeg - 0.3);
    }

    var alarm = false;
    if (this.n < this.warmup) {
      this.state = 'normal';
    } else if (this.cusumPos > this.threshold) {
      this.alarmCount++;
      if (this.alarmCount >= this.alarmPersist) {
        this.state = 'critical';
      } else {
        this.state = 'warning';
      }
      alarm = true;
    } else {
      // Decay alarm count when back to normal
      if (this.alarmCount > 0) this.alarmCount--;
      if (this.alarmCount === 0) this.state = 'normal';
      alarm = false;
    }

    return {
      alarm: alarm,
      state: this.state,
      score: qualityScore,
      cusum: this.cusumPos,
      ewma: Math.round(this.ewma * 10) / 10
    };
  }

  // Running median for MAD
  _computeMAD() {
    if (this.recentErrors.length < 3) return 1.0;
    var sorted = this.recentErrors.slice().sort(function(a, b) { return a - b; });
    var mid = Math.floor(sorted.length / 2);
    var median = sorted.length % 2 === 0
      ? (sorted[mid - 1] + sorted[mid]) / 2
      : sorted[mid];
    return 1.4826 * median;
  }

  getState() {
    return {
      state: this.state,
      cusumPos: Math.round(this.cusumPos * 100) / 100,
      ewma: Math.round(this.ewma * 10) / 10,
      alarmCount: this.alarmCount,
      n: this.n
    };
  }
}
