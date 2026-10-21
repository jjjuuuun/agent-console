import type { ChatSettings } from "@agent-console/contracts";
import { contractsSchema } from "@agent-console/contracts";
import { getDefaultValue } from "@agent-console/schema-form";

/** 스키마가 정한 채팅 설정 기본값(없으면 빈 객체). 기본값은 서버 계약이 소유한다. */
export function chatSettingDefaults(): ChatSettings {
  const def = contractsSchema.$defs["ChatSettings"];
  if (def === undefined) return {};
  try {
    const value = getDefaultValue({ ...(def as object), $defs: contractsSchema.$defs });
    return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as ChatSettings) : {};
  } catch {
    return {};
  }
}

/**
 * 공통 설정 위에 팀 구성 층을 덮어 채팅 동작을 정한다(키 단위, 팀 층의 null/undefined는 "상속").
 * 화면이 쓰는 값은 모두 이 결과에서 읽는다(`busy_policy`·`reply_display`·`send_key`·`list_sort`·`answer_with_composer`).
 */
export function resolveChatSettings(workspace: ChatSettings | null | undefined, team: ChatSettings | null | undefined, defaults: ChatSettings = chatSettingDefaults()): ChatSettings {
  const out: ChatSettings = { ...defaults };
  for (const layer of [workspace, team]) {
    if (!layer) continue;
    for (const [key, value] of Object.entries(layer)) if (value !== undefined && value !== null) out[key] = value;
  }
  return out;
}
