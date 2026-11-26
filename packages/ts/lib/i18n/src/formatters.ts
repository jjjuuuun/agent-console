import { createParticleFormatters } from "./particles";
import type { Formatter, FormatterRegistry } from "./types";

type DateInput = Date | number | string;

function toDate(value: unknown): Date | null {
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  if (typeof value === "number" || typeof value === "string") {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  return null;
}

function toNumber(value: unknown): number | null {
  const n = typeof value === "number" ? value : typeof value === "string" && value.trim() !== "" ? Number(value) : NaN;
  return Number.isFinite(n) ? n : null;
}

/** Caches `Intl` objects per (kind, language, options) inside one registry. */
function createIntlCache() {
  const cache = new Map<string, unknown>();
  return function get<T>(kind: string, language: string | undefined, options: unknown, make: () => T): T {
    const key = `${kind}|${language ?? ""}|${JSON.stringify(options)}`;
    let hit = cache.get(key) as T | undefined;
    if (hit === undefined) {
      hit = make();
      cache.set(key, hit);
    }
    return hit;
  };
}

function numberOptions(options: Record<string, unknown>, extra: Intl.NumberFormatOptions = {}): Intl.NumberFormatOptions {
  const out: Intl.NumberFormatOptions = { ...extra };
  for (const key of ["maximumFractionDigits", "minimumFractionDigits"] as const) {
    const n = toNumber(options[key]);
    if (n !== null) out[key] = n;
  }
  return out;
}

const TIME_OPTIONS: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" };
const MINUTE = 60;
const HOUR = 3600;
const DAY = 86400;

/**
 * The formats the screen spec names (`{value, name}` in a message): time, datetime, datetime-full, date,
 * time-local, relative, duration, number, number-compact, percent, bytes, currency, list, and the Korean
 * `particle.*` / `particle.*.only` set. Every one passes the current language to `Intl`; option values are data
 * in this table. Replace or add entries through `createI18n({ formatters })`.
 */
export function createDefaultFormatters(): FormatterRegistry {
  const intl = createIntlCache();
  const dateFormat = (language: string | undefined, options: Intl.DateTimeFormatOptions) =>
    intl("date", language, options, () => new Intl.DateTimeFormat(language, options));
  const numberFormat = (language: string | undefined, options: Intl.NumberFormatOptions) =>
    intl("number", language, options, () => new Intl.NumberFormat(language, options));

  const onDate =
    (make: (date: Date, options: Record<string, unknown>) => Intl.DateTimeFormatOptions): Formatter =>
    (value, language, options) => {
      const date = toDate(value as DateInput);
      return date === null ? String(value ?? "") : dateFormat(language, make(date, options)).format(date);
    };

  const date: Formatter = onDate(() => ({ dateStyle: "medium" }));

  const relative: Formatter = (value, language, options) => {
    const target = toDate(value);
    if (target === null) return String(value ?? "");
    const now = toDate(options.now) ?? new Date();
    const seconds = Math.round((target.getTime() - now.getTime()) / 1000);
    const abs = Math.abs(seconds);
    if (abs >= 7 * DAY) return date(target, language, options);
    const rtf = intl("rtf", language, "short", () => new Intl.RelativeTimeFormat(language, { numeric: "auto", style: "short" }));
    // Under 10 seconds reads "now" through numeric: "auto" (0 seconds).
    if (abs < 10) return rtf.format(0, "second");
    if (abs < MINUTE) return rtf.format(seconds, "second");
    if (abs < HOUR) return rtf.format(Math.round(seconds / MINUTE), "minute");
    if (abs < DAY) return rtf.format(Math.round(seconds / HOUR), "hour");
    return rtf.format(Math.round(seconds / DAY), "day");
  };

  const duration: Formatter = (value, language, options) => {
    const raw = toNumber(value);
    if (raw === null) return String(value ?? "");
    const seconds = options.unit === "s" ? raw : raw / 1000;
    if (seconds < MINUTE) {
      return numberFormat(language, { style: "unit", unit: "second", unitDisplay: "narrow", maximumFractionDigits: 1 }).format(seconds);
    }
    const total = Math.floor(seconds);
    const hours = Math.floor(total / HOUR);
    const minutes = Math.floor((total % HOUR) / MINUTE);
    const rest = total % MINUTE;
    const parts = hours > 0 ? { hours, minutes } : { minutes, seconds: rest };
    const DurationFormat = (Intl as unknown as { DurationFormat?: new (l?: string, o?: object) => { format(d: object): string } })
      .DurationFormat;
    if (DurationFormat) return intl("duration", language, "narrow", () => new DurationFormat(language, { style: "narrow" })).format(parts);
    return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m ${rest}s`;
  };

  const number: Formatter = (value, language, options) => {
    const n = toNumber(value);
    return n === null ? String(value ?? "") : numberFormat(language, numberOptions(options)).format(n);
  };

  return {
    time: onDate(() => TIME_OPTIONS),
    datetime: onDate((d) => {
      const base: Intl.DateTimeFormatOptions = { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" };
      return d.getFullYear() === new Date().getFullYear() ? base : { ...base, year: "numeric" };
    }),
    "datetime-full": onDate(() => ({ dateStyle: "medium", timeStyle: "medium", hourCycle: "h23" })),
    date,
    "time-local": onDate(() => ({ timeStyle: "short" })),
    relative,
    duration,
    number,
    "number-compact": (value, language, options) => {
      const n = toNumber(value);
      return n === null
        ? String(value ?? "")
        : numberFormat(language, numberOptions(options, { notation: "compact", compactDisplay: "short" })).format(n);
    },
    percent: (value, language, options) => {
      const n = toNumber(value);
      return n === null
        ? String(value ?? "")
        : numberFormat(language, numberOptions(options, { style: "percent", maximumFractionDigits: 0 })).format(n);
    },
    bytes: (value, language, options) => {
      const n = toNumber(value);
      if (n === null) return String(value ?? "");
      const unit = typeof options.unit === "string" ? options.unit : "byte";
      try {
        return numberFormat(language, numberOptions(options, { style: "unit", unit, unitDisplay: "narrow", maximumFractionDigits: 1 })).format(n);
      } catch {
        return numberFormat(language, {}).format(n);
      }
    },
    currency: (value, language, options) => {
      const n = toNumber(value);
      if (n === null) return String(value ?? "");
      if (typeof options.currency !== "string" || options.currency === "") return number(n, language, options);
      try {
        return numberFormat(language, { style: "currency", currency: options.currency }).format(n);
      } catch {
        return number(n, language, options);
      }
    },
    list: (value, language) => {
      if (!Array.isArray(value)) return String(value ?? "");
      const lf = intl("list", language, "short", () => new Intl.ListFormat(language, { type: "conjunction", style: "short" }));
      return lf.format(value.map(String));
    },
    ...createParticleFormatters(),
  };
}

/** The default registry, built once. Do not mutate; pass your own entries to `createI18n({ formatters })`. */
export const defaultFormatters: Readonly<FormatterRegistry> = createDefaultFormatters();
