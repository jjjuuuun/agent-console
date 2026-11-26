import { slugify } from "../../lib/format";

/**
 * 이름에서 id 후보를 만든다(소문자 영숫자·하이픈). 한글뿐이라 비면 `fallback`을 쓴다.
 * 이미 있는 id와 겹치면 `-2`, `-3` … 을 붙인다.
 */
export function suggestId(name: string, existing: ReadonlySet<string>, fallback: string): string {
  const slug = slugify(name);
  // 한글 이름에서 숫자만 남으면("흐름 2" -> "2") 뜻을 알 수 없으므로 기본 이름을 앞에 붙인다
  const base = /[a-z]/.test(slug) ? slug : slug === "" ? fallback : `${fallback}-${slug}`;
  if (!existing.has(base)) return base;
  for (let n = 2; n < 10_000; n += 1) {
    const candidate = `${base}-${n}`;
    if (!existing.has(candidate)) return candidate;
  }
  return `${base}-${existing.size + 1}`;
}

/** id 규칙(서버 저장 파일 이름이 된다): 영숫자로 시작, 영숫자·`_`·`-`·`.`. */
export const ID_PATTERN = /^[a-z0-9][a-z0-9._-]*$/i;

/** `id`가 서버가 준 예약어 목록에 있는가(양쪽 trim, 대소문자 무시 — 서버 `casefold` 비교와 같은 규칙. 로캘 비교는 쓰지 않는다). */
export function isReservedId(id: string, reserved: Iterable<string>): boolean {
  const folded = id.trim().toLowerCase();
  if (folded === "") return false;
  for (const r of reserved) if (r.trim().toLowerCase() === folded) return true;
  return false;
}

/** 입력한 id를 검사해 문제 종류를 돌려준다(없으면 undefined). `reserved` = 서버가 준 예약어(대소문자 무시). */
export function idProblem(id: string, existing: ReadonlySet<string>, reserved: Iterable<string> = []): "empty" | "pattern" | "duplicate" | "reserved" | undefined {
  if (id.trim() === "") return "empty";
  if (!ID_PATTERN.test(id)) return "pattern";
  if (existing.has(id)) return "duplicate";
  if (isReservedId(id, reserved)) return "reserved";
  return undefined;
}
