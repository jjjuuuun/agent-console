/** 언어와 무관한 표시용 함수 모음(순수 함수). 시각·숫자·기간처럼 화면 언어를 따르는 서식은 `i18n`의 `useFormat()`을 쓴다. */

/** 밀리초 → "00:12" (1시간 이상이면 "1:02:03"). 실행 중 경과 표시용. */
export function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const s = total % 60;
  const m = Math.floor(total / 60) % 60;
  const h = Math.floor(total / 3600);
  const two = (n: number) => n.toString().padStart(2, "0");
  return h > 0 ? `${h}:${two(m)}:${two(s)}` : `${two(m)}:${two(s)}`;
}

/** 이름에서 id 후보(소문자, 영숫자·하이픈)를 만든다. 한글만 있으면 빈 문자열. */
export function slugify(name: string): string {
  return name
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
}

/** 앞 8자만(표시용 id 축약). */
export function shortId(id: string): string {
  return id.length > 8 ? id.slice(0, 8) : id;
}

/** 값을 화면용 문자열로. 문자열은 그대로, 나머지는 들여쓴 JSON. */
export function stringifyValue(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2) ?? String(value);
  } catch {
    return String(value);
  }
}
