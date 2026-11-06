/** 시각·크기 표시 순수 함수. 시각은 Unix epoch 초. */

/** 상대 시각 문구 틀 키. 값은 messages 표가 준다(`{n}`을 숫자로 바꾼다). */
const UNITS: ReadonlyArray<readonly [number, string]> = [
  [86_400, "time.days"],
  [3_600, "time.hours"],
  [60, "time.minutes"],
];

/** 상대 시각. 1분 미만·미래는 `time.now` 문구. 문구 표는 호출자 messages. */
export function formatRelative(at: number, now: number, text: Readonly<Record<string, string>>): string {
  const diff = now - at;
  if (Number.isFinite(diff) && diff >= 60) {
    for (const [size, key] of UNITS) if (diff >= size) return (text[key] ?? key).replace("{n}", String(Math.floor(diff / size)));
  }
  return text["time.now"] ?? "time.now";
}

/** 절대 시각(툴팁). 지역 시간대 `YYYY-MM-DD HH:mm`. */
export function formatAbsolute(at: number): string {
  const d = new Date(at * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** 폴더 마지막 조각(경로 구분은 `/`). */
export function lastSegment(path: string): string {
  const i = path.lastIndexOf("/");
  return i < 0 ? path : path.slice(i + 1);
}
