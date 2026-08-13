// ========== Chart Utilities — V14.0 ==========
// LTTB downsampling, moving average, adaptive point radius, zoom/pan config

/**
 * Largest Triangle Three Buckets (LTTB) downsampling.
 * Preserves visual shape while reducing data points to `threshold`.
 * O(n) single-pass. Returns array of {x: index, y: value}.
 */
export function lttbDownsample(data, threshold) {
  if (!data || data.length <= threshold) return data;
  const dataLength = data.length;
  if (threshold < 3) threshold = 3;
  if (threshold >= dataLength) return data;

  // Convert to point array with indices
  const points = data.map((y, i) => ({ x: i, y }));
  const sampled = [];
  sampled.push(points[0]); // always keep first

  const bucketSize = (dataLength - 2) / (threshold - 2);
  let prev = points[0];

  for (let i = 1; i < threshold - 1; i++) {
    const bucketStart = Math.floor(i * bucketSize) + 1;
    const bucketEnd = Math.min(Math.floor((i + 1) * bucketSize) + 1, dataLength - 1);
    const bucketLen = bucketEnd - bucketStart;
    if (bucketLen <= 0) { sampled.push(points[bucketStart]); prev = points[bucketStart]; continue; }

    // Average of next bucket (used for triangle area calculation)
    const nextBucketStart = bucketEnd;
    const nextBucketEnd = Math.min(Math.floor((i + 2) * bucketSize) + 1, dataLength - 1);
    let avgX = 0, avgY = 0;
    const nextLen = Math.max(1, nextBucketEnd - nextBucketStart);
    for (let j = nextBucketStart; j < nextBucketEnd; j++) {
      avgX += points[j].x;
      avgY += points[j].y;
    }
    avgX /= nextLen;
    avgY /= nextLen;

    // Find point in current bucket with largest triangle area
    let maxArea = -1;
    let maxPoint = points[bucketStart];
    for (let j = bucketStart; j < bucketEnd; j++) {
      const area = Math.abs(
        (prev.x - avgX) * (points[j].y - prev.y) -
        (prev.x - points[j].x) * (avgY - prev.y)
      );
      if (area > maxArea) { maxArea = area; maxPoint = points[j]; }
    }
    sampled.push(maxPoint);
    prev = maxPoint;
  }

  sampled.push(points[dataLength - 1]); // always keep last
  return sampled;
}

/**
 * Compute centered moving average (same-length output, no None at edges).
 * Edge handling: truncated window at boundaries.
 */
export function computeMovingAverage(values, window) {
  if (!window) window = 7;
  if (values.length <= window) return values.slice(); // too few points
  const half = Math.floor(window / 2);
  const result = new Array(values.length);
  for (let i = 0; i < values.length; i++) {
    const start = Math.max(0, i - half);
    const end = Math.min(values.length, i + half + 1);
    let sum = 0;
    for (let j = start; j < end; j++) sum += values[j];
    result[i] = sum / (end - start);
  }
  return result;
}

/**
 * Return appropriate point radius based on data density.
 */
export function adaptivePointRadius(count) {
  if (count <= 7) return 5;
  if (count <= 14) return 4;
  if (count <= 30) return 2;
  if (count <= 60) return 1;
  return 0; // >60 points: hide dots, show line only
}

/**
 * Determine min chart width (px) based on data point count.
 */
export function chartMinWidth(count) {
  if (count <= 14) return 0; // no scroll needed
  return Math.max(count * 55, 600);
}

/**
 * Read theme-aware chart colors from CSS custom properties.
 * Falls back to dark-theme values when variables are unavailable.
 */
export function chartTheme() {
  const cs = getComputedStyle(document.documentElement);
  const v = (name, fallback) => cs.getPropertyValue(name).trim() || fallback;
  return {
    tick: v('--text3', '#63637a'),
    grid: v('--ring-track', '#1e1e28'),
    green: v('--green', '#3dd68c'),
    blue: v('--blue', '#5e9eff'),
    orange: v('--orange', '#f59e4b'),
    red: v('--red', '#f87171'),
    purple: v('--purple', '#8a2be2'),
    surface: v('--surface', '#18181f'),
  };
}

/**
 * Show a skeleton placeholder in place of a chart while data loads.
 * Removed automatically by setChartEmpty(canvas, false) on render.
 */
export function setChartSkeleton(canvas) {
  if (!canvas) return;
  const wrap = canvas.closest('.chart-wrap') || canvas.parentElement;
  const host = wrap.parentElement;
  if (host.querySelector('.chart-empty')) return;
  wrap.style.display = 'none';
  const el = document.createElement('div');
  el.className = 'chart-empty';
  el.innerHTML = '<div class="skeleton" style="width:100%;height:140px"></div>';
  wrap.after(el);
}

/**
 * Toggle an empty-state placeholder in place of a chart canvas.
 * Pass isEmpty=false to restore the canvas (e.g. after data arrives).
 */
export function setChartEmpty(canvas, isEmpty, html) {
  const wrap = canvas.closest('.chart-wrap') || canvas.parentElement;
  const host = wrap.parentElement;
  let el = host.querySelector('.chart-empty');
  if (isEmpty) {
    wrap.style.display = 'none';
    if (!el) {
      el = document.createElement('div');
      el.className = 'chart-empty';
      wrap.after(el);
    }
    el.innerHTML = html;
  } else {
    wrap.style.display = '';
    canvas.style.display = '';
    if (el) el.remove();
  }
}

/**
 * Build a base Chart.js options object with zoom/pan + consistent styling.
 * @param {object} overrides - Chart.js options overrides (merged onto base)
 * @returns {object} complete Chart.js options
 */
export function createChartOptions(overrides) {
  const theme = chartTheme();
  const base = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: false },
      zoom: {
        pan: { enabled: true, mode: 'x' },
        zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' },
      },
    },
    scales: {
      x: {
        ticks: { color: theme.tick, maxTicksLimit: 14, maxRotation: 45 },
        grid: { color: theme.grid },
      },
      y: {
        ticks: { color: theme.tick },
        grid: { color: theme.grid },
        beginAtZero: true,
      },
    },
  };

  if (overrides) {
    // Deep merge scales
    if (overrides.scales) {
      for (const axis of ['x', 'y', 'y1']) {
        if (overrides.scales[axis]) {
          base.scales[axis] = { ...base.scales[axis], ...overrides.scales[axis] };
        }
      }
      delete overrides.scales;
    }
    // Merge remaining top-level keys
    Object.assign(base, overrides);
  }
  return base;
}

/**
 * Process chart data: apply downsampling if needed, return {labels, values}.
 */
export function prepareChartData(data, groupFn, threshold) {
  const byDate = groupFn(data);
  let labels = Object.keys(byDate).sort();
  let values = labels.map(d => byDate[d]);

  if (threshold && values.length > threshold) {
    const downsampled = lttbDownsample(values, threshold);
    // Rebuild labels from sampled indices
    const newLabels = [];
    const newValues = [];
    for (const p of downsampled) {
      if (p.x < labels.length) {
        newLabels.push(labels[p.x]);
        newValues.push(p.y);
      }
    }
    return { labels: newLabels, values: newValues, originalCount: values.length };
  }
  return { labels, values, originalCount: values.length };
}
