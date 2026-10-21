/**
 * 비교 표에서 배열 원소의 표시 이름으로 쓸 키 후보(앞에서부터 처음 있는 문자열 값)의 **기본값**.
 * 사용자는 설정 `ui.versions.item_label_keys`로 바꾼다(비우면 이 기본값). 화면은 이 순서를 모른다.
 */
export const DEFAULT_DIFF_LABEL_KEYS: readonly string[] = ["label", "name", "title", "id"];

/** 설정 값(생략·빈 목록 = 상속)을 쓸 키 목록으로 바꾼다. 공백 키는 버린다. */
export function resolveLabelKeys(configured: readonly string[] | null | undefined): readonly string[] {
  const keys = (configured ?? []).filter((k) => k.trim() !== "");
  return keys.length > 0 ? keys : DEFAULT_DIFF_LABEL_KEYS;
}
