import dayjs from "dayjs";

/** 将后端 decimal 字符串格式化为固定小数位 */
export function formatDecimal(
  value: string | number | null | undefined,
  digits = 2,
): string {
  if (value === null || value === undefined || value === "") return "-";
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return n.toFixed(digits);
}

/** 涨跌幅（小数比率）→ 百分比字符串 */
export function formatPercent(
  rate: string | number | null | undefined,
  digits = 2,
): string {
  const n = Number(rate);
  if (Number.isNaN(n)) return "-";
  return `${(n * 100).toFixed(digits)}%`;
}

/** ISO 时间格式化 */
export function formatTime(
  value: string | Date | null | undefined,
  pattern = "HH:mm:ss",
): string {
  if (!value) return "-";
  return dayjs(value).format(pattern);
}

/** A 股涨红跌绿 */
export function formatChangeColor(rate: string | number): string | undefined {
  const n = Number(rate);
  if (n > 0) return "#cf1322";
  if (n < 0) return "#3f8600";
  return undefined;
}
