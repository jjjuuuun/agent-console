/** 표시용 포맷 함수 모음(순수 함수). 시각 입력은 Unix epoch 초(서버 계약). */

/** 밀리초 → "0.8초" / "1.2초" / "1분 3.2초" / "1시간 2분". */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms) || ms < 0) return "–";
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds).toString()}초`;
  const totalMin = Math.floor(seconds / 60);
  if (totalMin < 60) {
    const rest = seconds - totalMin * 60;
    return `${totalMin}분 ${rest.toFixed(1)}초`;
  }
  const hours = Math.floor(totalMin / 60);
  return `${hours}시간 ${totalMin % 60}분`;
}

/** 밀리초 → "00:12" (1시간 이상이면 "1:02:03"). 실행 중 경과 표시용. */
export function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const s = total % 60;
  const m = Math.floor(total / 60) % 60;
  const h = Math.floor(total / 3600);
  const two = (n: number) => n.toString().padStart(2, "0");
  return h > 0 ? `${h}:${two(m)}:${two(s)}` : `${two(m)}:${two(s)}`;
}

export function formatCount(n: number | null | undefined): string {
  return n === null || n === undefined || !Number.isFinite(n) ? "–" : n.toLocaleString("ko-KR");
}

/** 절대 시각(툴팁용). */
export function formatDateTime(epochSeconds: number | null | undefined): string {
  if (epochSeconds === null || epochSeconds === undefined || !Number.isFinite(epochSeconds)) return "–";
  return new Date(epochSeconds * 1000).toLocaleString("ko-KR");
}

/** 시각만(`14:01:02`, 24시간). 같은 날의 기록 표에서 쓴다. */
export function formatClockTime(epochSeconds: number | null | undefined): string {
  if (epochSeconds === null || epochSeconds === undefined || !Number.isFinite(epochSeconds)) return "–";
  const d = new Date(epochSeconds * 1000);
  const two = (n: number) => String(n).padStart(2, "0");
  return `${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}`;
}

/** 상대 시각 "방금 전" / "2분 전" / "3시간 전" / "5일 전". */
export function formatRelative(epochSeconds: number | null | undefined, nowMs: number): string {
  if (epochSeconds === null || epochSeconds === undefined || !Number.isFinite(epochSeconds)) return "–";
  const diff = Math.max(0, nowMs / 1000 - epochSeconds);
  if (diff < 45) return "방금 전";
  if (diff < 3600) return `${Math.round(diff / 60)}분 전`;
  if (diff < 86400) return `${Math.round(diff / 3600)}시간 전`;
  return `${Math.round(diff / 86400)}일 전`;
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

/**
 * 주격 조사: 마지막 글자가 받침으로 끝나면 "이", 아니면 "가". 한글이 아닌 끝 글자(영문·숫자 등)는
 * 발음을 알 수 없으므로 "이(가)"로 쓴다.
 * @param word 조사를 붙일 낱말(비어 있으면 그대로)
 */
export function withSubjectParticle(word: string): string {
  const last = word.trimEnd().slice(-1);
  if (last === "") return word;
  const code = last.charCodeAt(0);
  if (code < 0xac00 || code > 0xd7a3) return `${word}이(가)`;
  return `${word}${(code - 0xac00) % 28 === 0 ? "가" : "이"}`;
}
