import { createContext, useContext } from "react";
import type { KeyPlatform } from "@agent-console/ui";

export interface ShortcutEnvironment {
  /** 셸이 가진 기본 키 표(동작 id → 키). 화면이 등록한 단축키의 기본값은 포함하지 않는다 */
  defaultKeys: Readonly<Record<string, string>>;
  platform: KeyPlatform;
}

/** 설정 화면의 단축키 표가 "기본값" 열과 플랫폼 표기를 알기 위한 컨텍스트(셸이 공급). */
export const ShortcutEnvironmentContext = createContext<ShortcutEnvironment>({ defaultKeys: {}, platform: "other" });

export function useShortcutEnvironment(): ShortcutEnvironment {
  return useContext(ShortcutEnvironmentContext);
}
