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

/** 입력한 id를 검사해 문제 종류를 돌려준다(없으면 undefined). */
export function idProblem(id: string, existing: ReadonlySet<string>): "empty" | "pattern" | "duplicate" | undefined {
  if (id.trim() === "") return "empty";
  if (!ID_PATTERN.test(id)) return "pattern";
  if (existing.has(id)) return "duplicate";
  return undefined;
}

/** 이름이 겹치지 않는 "{이름} 2" 형태(노드 label 기본값 등). */
export function uniqueName(name: string, existing: Iterable<string>): string {
  const used = new Set(existing);
  if (!used.has(name)) return name;
  for (let n = 2; n < 10_000; n += 1) if (!used.has(`${name} ${n}`)) return `${name} ${n}`;
  return `${name} ${used.size + 1}`;
}
