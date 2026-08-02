/** 指标预览：基于示例收盘价序列计算指标值（供创建器 UI 展示）。 */

export type PreviewSeries = {
  times: number[];
  lines: Array<{ name: string; data: (number | null)[]; color?: string }>;
};

const SAMPLE_CLOSES = [10, 10.2, 9.8, 10.5, 11, 11.5, 12, 11.8, 12.5, 13, 13.2, 12.9, 14, 14.5, 15];

function sma(values: number[], period: number): (number | null)[] {
  return values.map((_, i) => {
    if (i + 1 < period) return null;
    const slice = values.slice(i + 1 - period, i + 1);
    return slice.reduce((a, b) => a + b, 0) / period;
  });
}

function ema(values: number[], period: number): (number | null)[] {
  const k = 2 / (period + 1);
  const out: (number | null)[] = [];
  let prev: number | null = null;
  for (let i = 0; i < values.length; i += 1) {
    if (i + 1 < period) {
      out.push(null);
      continue;
    }
    if (prev === null) {
      const seed = values.slice(0, period).reduce((a, b) => a + b, 0) / period;
      prev = seed;
      out.push(seed);
      continue;
    }
    prev = values[i] * k + prev * (1 - k);
    out.push(prev);
  }
  return out;
}

function rsi(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = [];
  for (let i = 0; i < values.length; i += 1) {
    if (i < period) {
      out.push(null);
      continue;
    }
    let gains = 0;
    let losses = 0;
    for (let j = i - period + 1; j <= i; j += 1) {
      const diff = values[j] - values[j - 1];
      if (diff >= 0) gains += diff;
      else losses -= diff;
    }
    if (losses === 0) out.push(100);
    else {
      const rs = gains / losses;
      out.push(100 - 100 / (1 + rs));
    }
  }
  return out;
}

function macd(
  values: number[],
  fast: number,
  slow: number,
  signal: number,
): { macd: (number | null)[]; signal: (number | null)[]; histogram: (number | null)[] } {
  const fastEma = ema(values, fast);
  const slowEma = ema(values, slow);
  const macdLine = values.map((_, i) => {
    if (fastEma[i] === null || slowEma[i] === null) return null;
    return fastEma[i]! - slowEma[i]!;
  });
  const nonNull = macdLine.map((v) => v ?? 0);
  const signalLine = ema(nonNull, signal);
  const histogram = macdLine.map((v, i) =>
    v === null || signalLine[i] === null ? null : v - signalLine[i]!,
  );
  return { macd: macdLine, signal: signalLine, histogram };
}

function bollinger(
  values: number[],
  period: number,
  stdDev: number,
): { mid: (number | null)[]; upper: (number | null)[]; lower: (number | null)[] } {
  const mid = sma(values, period);
  const upper: (number | null)[] = [];
  const lower: (number | null)[] = [];
  for (let i = 0; i < values.length; i += 1) {
    if (mid[i] === null) {
      upper.push(null);
      lower.push(null);
      continue;
    }
    const slice = values.slice(i + 1 - period, i + 1);
    const mean = mid[i]!;
    const variance = slice.reduce((acc, v) => acc + (v - mean) ** 2, 0) / period;
    const sd = Math.sqrt(variance);
    upper.push(mean + stdDev * sd);
    lower.push(mean - stdDev * sd);
  }
  return { mid, upper, lower };
}

function atr(values: number[], period: number): (number | null)[] {
  const tr: number[] = [];
  for (let i = 0; i < values.length; i += 1) {
    if (i === 0) tr.push(values[i] * 0.02);
    else tr.push(Math.abs(values[i] - values[i - 1]) + values[i] * 0.01);
  }
  return sma(tr, period);
}

function roc(values: number[], period: number): (number | null)[] {
  return values.map((v, i) => {
    if (i < period) return null;
    const prev = values[i - period];
    if (prev === 0) return null;
    return ((v - prev) / prev) * 100;
  });
}

function kdj(
  values: number[],
  period: number,
): { k: (number | null)[]; d: (number | null)[]; j: (number | null)[] } {
  const highs = values.map((c) => c * 1.01);
  const lows = values.map((c) => c * 0.99);
  const kOut: (number | null)[] = [];
  const dOut: (number | null)[] = [];
  const jOut: (number | null)[] = [];
  let k = 50;
  let d = 50;
  for (let i = 0; i < values.length; i += 1) {
    if (i + 1 < period) {
      kOut.push(null);
      dOut.push(null);
      jOut.push(null);
      continue;
    }
    const hSlice = highs.slice(i + 1 - period, i + 1);
    const lSlice = lows.slice(i + 1 - period, i + 1);
    const highest = Math.max(...hSlice);
    const lowest = Math.min(...lSlice);
    const rsv =
      highest === lowest ? 50 : ((values[i] - lowest) / (highest - lowest)) * 100;
    k = (2 / 3) * k + (1 / 3) * rsv;
    d = (2 / 3) * d + (1 / 3) * k;
    jOut.push(3 * k - 2 * d);
    kOut.push(k);
    dOut.push(d);
  }
  return { k: kOut, d: dOut, j: jOut };
}

export function buildIndicatorPreview(
  type: string,
  options: {
    period?: number;
    params?: Record<string, unknown>;
  },
): PreviewSeries {
  const closes = SAMPLE_CLOSES;
  const times = closes.map((_, i) => i);
  const period = options.period ?? 5;

  switch (type) {
    case "sma":
      return {
        times,
        lines: [{ name: "SMA", data: sma(closes, period), color: "#3b82f6" }],
      };
    case "ema":
      return {
        times,
        lines: [{ name: "EMA", data: ema(closes, period), color: "#8b5cf6" }],
      };
    case "rsi":
      return {
        times,
        lines: [{ name: "RSI", data: rsi(closes, period), color: "#f59e0b" }],
      };
    case "macd": {
      const p = options.params ?? {};
      const fast = Number(p.fast ?? 12);
      const slow = Number(p.slow ?? 26);
      const sig = Number(p.signal ?? 9);
      const { macd: m, signal: s, histogram: h } = macd(closes, fast, slow, sig);
      return {
        times,
        lines: [
          { name: "MACD", data: m, color: "#3b82f6" },
          { name: "Signal", data: s, color: "#f59e0b" },
          { name: "Histogram", data: h, color: "#10b981" },
        ],
      };
    }
    case "bollinger": {
      const stdDev = Number(options.params?.std_dev ?? 2);
      const { mid, upper, lower } = bollinger(closes, period, stdDev);
      return {
        times,
        lines: [
          { name: "Upper", data: upper, color: "#ef4444" },
          { name: "Mid", data: mid, color: "#3b82f6" },
          { name: "Lower", data: lower, color: "#10b981" },
        ],
      };
    }
    case "atr":
      return {
        times,
        lines: [{ name: "ATR", data: atr(closes, period), color: "#6366f1" }],
      };
    case "roc":
      return {
        times,
        lines: [{ name: "ROC", data: roc(closes, period), color: "#14b8a6" }],
      };
    case "volume_sma":
      return {
        times,
        lines: [
          {
            name: "Vol SMA",
            data: sma(closes.map((c) => c * 1000), period),
            color: "#64748b",
          },
        ],
      };
    case "kdj": {
      const { k, d, j } = kdj(closes, period);
      return {
        times,
        lines: [
          { name: "K", data: k, color: "#3b82f6" },
          { name: "D", data: d, color: "#f59e0b" },
          { name: "J", data: j, color: "#ec4899" },
        ],
      };
    }
    default:
      return { times, lines: [] };
  }
}

export function latestPreviewValue(series: PreviewSeries): string {
  for (const line of series.lines) {
    for (let i = line.data.length - 1; i >= 0; i -= 1) {
      const v = line.data[i];
      if (v !== null && Number.isFinite(v)) {
        return `${line.name}: ${v.toFixed(2)}`;
      }
    }
  }
  return "—";
}
