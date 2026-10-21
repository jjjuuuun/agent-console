import { jsonEqual } from "../../lib/jsonPointer";

/** 설정 문서에서 `a/b` 형태의 키 경로가 가리키는 값(없으면 undefined). */
function valueAt(doc: unknown, key: string): unknown {
  let cur = doc;
  for (const part of key.split("/")) {
    if (typeof cur !== "object" || cur === null) return undefined;
    cur = (cur as Record<string, unknown>)[part];
  }
  return cur;
}

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

/**
 * 섹션이 편집하는 키들(`keys`)에서 저장된 값(`base`)과 초안(`draft`)이 다른 항목 수.
 * 객체면 한 단계 아래 키마다 하나로 센다(섹션 머리의 "저장되지 않은 변경 N"). 순수 함수.
 */
export function countSectionChanges(keys: readonly string[], base: unknown, draft: unknown): number {
  let n = 0;
  for (const key of keys) {
    const a = valueAt(base, key);
    const b = valueAt(draft, key);
    if (jsonEqual(a, b)) continue;
    if (isRecord(a) || isRecord(b)) {
      const names = new Set([...Object.keys(isRecord(a) ? a : {}), ...Object.keys(isRecord(b) ? b : {})]);
      const diff = [...names].filter((name) => !jsonEqual(isRecord(a) ? a[name] : undefined, isRecord(b) ? b[name] : undefined)).length;
      n += Math.max(diff, 1);
    } else {
      n += 1;
    }
  }
  return n;
}

/** 주소 해시(`#logs?source=x`·`#logs/taxonomy`)에서 섹션 id만 뽑는다. 없으면 빈 문자열. */
export function sectionIdFromHash(hash: string): string {
  return (hash.replace(/^#/, "").split("?")[0] ?? "").split("/")[0] ?? "";
}

/** 섹션 목록을 `group` 첫 등장 순서대로 묶는다(묶음 제목 목록은 데이터에서 나온다). */
export function groupSections<T extends { group: string }>(items: readonly T[]): { group: string; items: T[] }[] {
  const out: { group: string; items: T[] }[] = [];
  for (const it of items) {
    const found = out.find((g) => g.group === it.group);
    if (found) found.items.push(it);
    else out.push({ group: it.group, items: [it] });
  }
  return out;
}
