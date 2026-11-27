import { useMemo } from "react";
import { defaultFormatters, useT } from "@agent-console/i18n";

/** 화면에 보이는 시각·기간·숫자 서식(screen-i18n §6). 모든 값은 현재 화면 언어로 `Intl`에 넘긴다. */
export interface Format {
  /** 현재 화면 언어 코드 */
  language: string;
  /** 목록의 시각(`datetime`: 월·일·시·분, 올해가 아니면 연도). 입력은 Unix epoch 초(서버 계약). 값이 없으면 "–". */
  dateTime(epochSeconds: number | null | undefined): string;
  /** 툴팁·상세의 전체 시각(`datetime-full`). */
  dateTimeFull(epochSeconds: number | null | undefined): string;
  /** 표의 시각(`time`, 24시간). */
  time(epochSeconds: number | null | undefined): string;
  /** 날짜만(`date`). */
  date(epochSeconds: number | null | undefined): string;
  /** 읽는 곳의 시각(`time-local`, 언어 기본 시간제). */
  timeLocal(epochSeconds: number | null | undefined): string;
  /** 상대 시각(`relative`: 방금·분·시간·일, 7일 넘으면 날짜). */
  relative(epochSeconds: number | null | undefined, nowMs: number): string;
  /** 소요 시간(`duration`, 밀리초). 값이 없으면 "–". */
  duration(ms: number | null | undefined): string;
  /** 개수·토큰(`number`). 소수 자릿수는 `maximumFractionDigits`로. 값이 없으면 "–". */
  number(n: number | null | undefined, maximumFractionDigits?: number): string;
  /** 좁은 곳의 짧은 수(`number-compact`). */
  compact(n: number | null | undefined): string;
  /** 사용률 등(`percent`, 0~1). */
  percent(ratio: number): string;
  /** 남은 시간("3일 4시간" / "3d 4h"). 단위는 `Intl.NumberFormat`의 좁은 단위. 1분 미만이면 `underMinute`를 돌려준다. */
  remaining(seconds: number, underMinute: string): string;
}

const NONE = "–";
const missing = (v: number | null | undefined): v is null | undefined => v === null || v === undefined || !Number.isFinite(v);

/** 서식 만들기(순수 함수, 언어만 받는다). 테스트·다른 화면에서도 호출할 수 있다. */
export function createFormat(language: string): Format {
  const f = defaultFormatters;
  const at = (fmt: string, sec: number | null | undefined, options: Record<string, unknown> = {}): string =>
    missing(sec) ? NONE : String(f[fmt]!(new Date(sec * 1000), language, options));
  const unit = (unitName: string, n: number) => new Intl.NumberFormat(language, { style: "unit", unit: unitName, unitDisplay: "narrow" }).format(n);
  return {
    language,
    dateTime: (s) => at("datetime", s),
    dateTimeFull: (s) => at("datetime-full", s),
    time: (s) => at("time", s),
    date: (s) => at("date", s),
    timeLocal: (s) => at("time-local", s),
    relative: (s, nowMs) => at("relative", s, { now: new Date(nowMs) }),
    duration: (ms) => (missing(ms) || ms < 0 ? NONE : String(f["duration"]!(ms, language, {}))),
    number: (n, digits) => (missing(n) ? NONE : String(f["number"]!(n, language, digits === undefined ? {} : { maximumFractionDigits: digits }))),
    compact: (n) => (missing(n) ? NONE : String(f["number-compact"]!(n, language, {}))),
    percent: (r) => String(f["percent"]!(r, language, {})),
    remaining: (seconds, underMinute) => {
      const s = Math.max(0, Math.floor(seconds));
      const days = Math.floor(s / 86400);
      const hours = Math.floor((s % 86400) / 3600);
      const minutes = Math.floor((s % 3600) / 60);
      const join = (a: string, b: string) => `${a} ${b}`;
      if (days > 0) return hours > 0 ? join(unit("day", days), unit("hour", hours)) : unit("day", days);
      if (hours > 0) return minutes > 0 ? join(unit("hour", hours), unit("minute", minutes)) : unit("hour", hours);
      return minutes > 0 ? unit("minute", minutes) : underMinute;
    },
  };
}

/** 현재 화면 언어의 서식. 언어가 바뀌면 다시 그려진다. */
export function useFormat(): Format {
  const { language } = useT("boot");
  return useMemo(() => createFormat(language), [language]);
}
