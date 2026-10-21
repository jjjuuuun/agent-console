import { categoryColorSlot } from "@agent-console/graph-editor";
import type { SlotFor } from "@agent-console/log-view";

/**
 * 범주·레인·세션 색 슬롯(0~7). 노드 카테고리와 같은 해시 규칙(`tokens.md` 1.5)을 그대로 쓴다 — 해시를 복사하지 않고 기존 함수를 주입한다.
 * 빈 키는 슬롯 0.
 */
export const slotFor: SlotFor = (key) => {
  const slot = categoryColorSlot(key);
  return slot === "neutral" ? 0 : slot - 1;
};
