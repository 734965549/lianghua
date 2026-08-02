import dayjs from "dayjs";
import timezone from "dayjs/plugin/timezone";
import utc from "dayjs/plugin/utc";

dayjs.extend(utc);
dayjs.extend(timezone);

const DISPLAY_TIMEZONE = "Asia/Shanghai";

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

/** UTC ISO 时间统一转换为上海时区；无偏移字符串按数据库 UTC 兼容处理。 */
export function formatTime(
  value: string | Date | null | undefined,
  pattern = "HH:mm:ss",
): string {
  if (!value) return "-";
  const normalized =
    typeof value === "string" && !/(?:Z|[+-]\d{2}:\d{2})$/i.test(value)
      ? `${value}Z`
      : value;
  return dayjs(normalized).tz(DISPLAY_TIMEZONE).format(pattern);
}

/** A 股涨红跌绿 */
export function formatChangeColor(rate: string | number): string | undefined {
  const n = Number(rate);
  if (n > 0) return "#ff4d57";
  if (n < 0) return "#18c78c";
  return undefined;
}
