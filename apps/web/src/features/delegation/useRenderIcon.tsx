import { useCallback, type ReactNode } from "react";
import { Icon, useIconRegistry } from "@agent-console/ui";

/**
 * 아이콘 이름 → 그림(편집기·실행 상세 그래프의 `renderIcon`). 레지스트리에 없는 이름은 null을 돌려 편집기가 짧은 문자·제목 첫 글자로 대신하게 한다.
 * 아이콘 이름 목록은 코드에 없고, 앱이 레지스트리에 등록한 것만 그린다.
 */
export function useRenderIcon(size = 14): (name: string) => ReactNode {
  const registry = useIconRegistry();
  return useCallback((name: string): ReactNode => (registry.has(name) ? <Icon name={name} size={size} /> : null), [registry, size]);
}
