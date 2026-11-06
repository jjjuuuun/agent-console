import { useCallback, useState, type ReactNode } from "react";
import { Banner, Button } from "@agent-console/ui";
import { messages as m } from "./messages";
import type { SafeStorage } from "./storage";
import { useStorage } from "./StorageContext";

/** "이미 봤다" 표시를 저장하는 localStorage 키 접두어(`ac.hint.<id>`). */
export const HINT_KEY_PREFIX = "ac.hint.";

export function hintKey(id: string): string {
  return `${HINT_KEY_PREFIX}${id}`;
}

/** 저장된 안내 닫힘 표시를 모두 지운다(도움말의 "안내 다시 보기"). 지운 키 수를 돌려준다. */
export function resetHints(storage: SafeStorage): number {
  const keys = storage.keys().filter((k) => k.startsWith(HINT_KEY_PREFIX));
  keys.forEach((k) => storage.remove(k));
  return keys.length;
}

/** 안내 하나의 표시 여부와 닫기. 닫으면 저장된다(저장 실패해도 이 세션에서는 숨김). */
export function useHint(id: string): { visible: boolean; dismiss: () => void } {
  const storage = useStorage();
  const [hidden, setHidden] = useState(() => storage.get(hintKey(id)) !== null);
  const dismiss = useCallback(() => {
    storage.set(hintKey(id), "1");
    setHidden(true);
  }, [storage, id]);
  return { visible: !hidden, dismiss };
}

/**
 * 화면 첫 방문 안내 배너(닫기 가능, 키 `ac.hint.<id>`).
 * `satisfied`가 true면(안내가 요구하는 조건을 이미 채움) 보이지 않는다. 저장된 닫힘 표시는 건드리지 않는다.
 */
export function HintBanner({ id, children, satisfied = false }: { id: string; children: ReactNode; satisfied?: boolean }) {
  const { visible, dismiss } = useHint(id);
  if (!visible || satisfied) return null;
  return (
    <Banner tone="info" data-hint={id} actions={<Button size="sm" onClick={dismiss}>{m.hints.dismiss}</Button>}>
      {children}
    </Banner>
  );
}
