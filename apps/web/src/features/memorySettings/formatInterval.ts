/** 초 → "1시간 30분"처럼 0인 단위를 뺀 주기 문구. 단위 틀은 부르는 쪽(메시지 표)이 준다. */
export interface IntervalUnits {
  hour: (n: number) => string;
  minute: (n: number) => string;
  second: (n: number) => string;
}

export function formatInterval(totalSeconds: number, units: IntervalUnits): string {
  const total = Math.max(0, Math.round(totalSeconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const parts = [h > 0 ? units.hour(h) : "", m > 0 ? units.minute(m) : "", s > 0 ? units.second(s) : ""].filter((x) => x !== "");
  return parts.length > 0 ? parts.join(" ") : units.second(0);
}
