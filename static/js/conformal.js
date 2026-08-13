// ========== V21: Adaptive Conformal Predictor ==========
// Online confidence estimation for pose form assessments.
// Each prediction (e.g. "knee valgus = 12%") comes with a confidence interval.

export class AdaptiveConformalPredictor {
  constructor(options = {}) {
    this.alpha = options.alpha || 0.1;       // target miscoverage rate (90% confidence)
    this.gamma = options.gamma || 0.005;     // adaptation rate
    this.maxScores = options.maxScores || 50; // sliding window size

    this.reset();
  }

  reset() {
    this.scores = [];       // sliding window of nonconformity scores
    this.qValue = 1.0;      // calibrated quantile
    this.coverage = 1.0;    // recent coverage rate (EMA)
    this.n = 0;             // total predictions
    this.covered = 0;       // total covered predictions
  }

  // error = |prediction - ground_truth| (or any nonconformity measure)
  // prediction = the model's point estimate
  // Returns { lo: number, hi: number, confidence: number, covered: boolean }
  updateAndPredict(prediction, error) {
    this.n++;

    // Store score in sliding window
    this.scores.push(error);
    if (this.scores.length > this.maxScores) this.scores.shift();

    // Re-calibrate quantile
    if (this.scores.length >= 10) {
      var sorted = this.scores.slice().sort(function(a, b) { return a - b; });
      // Target: (1 - alpha) coverage, with (1 - gamma) adaptation toward target
      var targetIdx = Math.ceil(sorted.length * (1 - this.alpha)) - 1;
      targetIdx = Math.max(0, Math.min(targetIdx, sorted.length - 1));
      var targetQ = sorted[targetIdx];

      // Adapt q-value toward target
      this.qValue = (1 - this.gamma) * this.qValue + this.gamma * targetQ;
    } else {
      // Fallback: use max score as conservative estimate
      this.qValue = Math.max.apply(null, this.scores.concat([1.0]));
    }

    // Prediction interval (asymmetric for fitness: wider above, tighter below)
    var lo = prediction - this.qValue * 0.8;
    var hi = prediction + this.qValue * 1.2;

    // Check coverage
    var covered = (error <= this.qValue);
    if (covered) this.covered++;
    this.coverage = this.covered / this.n;

    // Confidence (inverse of interval width, capped at 0-100)
    var intervalWidth = hi - lo;
    var confidence = Math.max(0, Math.min(100, Math.round((1 - intervalWidth / 50) * 100)));

    return {
      lo: Math.round(lo),
      hi: Math.round(hi),
      confidence: confidence,
      covered: covered
    };
  }

  // For when you just want the current confidence without updating
  getConfidence(prediction) {
    if (this.qValue === null) return 50; // default: uncertain
    var intervalWidth = this.qValue * 2;
    return Math.max(0, Math.min(100, Math.round((1 - intervalWidth / 50) * 100)));
  }

  getState() {
    return {
      qValue: Math.round(this.qValue * 1000) / 1000,
      coverage: Math.round(this.coverage * 1000) / 1000,
      n: this.n,
      windowSize: this.scores.length
    };
  }
}
