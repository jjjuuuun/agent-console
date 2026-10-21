/** tokens.md 1.5: 카테고리 문자열의 안정 해시로 8칸 팔레트에서 분류색 슬롯을 고른다. */

/** FNV-1a 32비트 해시(UTF-8 바이트 기준). */
export function fnv1a32(text: string): number {
  const bytes = new TextEncoder().encode(text);
  let hash = 0x811c9dc5;
  for (const byte of bytes) {
    hash ^= byte;
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash >>> 0;
}

export type CategoryColorSlot = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | "neutral";

/**
 * 카테고리 문자열 → 분류색 슬롯. 빈 값/없음은 `neutral`.
 * CSS 변수 `--ac-cat-<slot>`(또는 `--ac-cat-neutral`)에 대응한다.
 */
export function categoryColorSlot(category: string | null | undefined): CategoryColorSlot {
  const normalized = (category ?? "").normalize("NFC");
  if (normalized.trim() === "") return "neutral";
  return ((fnv1a32(normalized) % 8) + 1) as CategoryColorSlot;
}

/** 슬롯에 대응하는 CSS 변수 참조. */
export function categoryColorVar(category: string | null | undefined): string {
  return `var(--ac-cat-${categoryColorSlot(category)})`;
}
