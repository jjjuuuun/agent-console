import { getContractSchema, type UsageIndicatorColorRule, type UsageIndicatorSettings } from "@agent-console/contracts";
import { getDefaultValue } from "@agent-console/schema-form";
import { FALLBACK_PLACEMENT, INDICATOR_FIELDS, INDICATOR_PLACEMENTS, type IndicatorPlacement } from "./usageConfig";

/** 기본값이 채워진 표시기 설정(계약 `UsageIndicatorSettings`의 모든 키가 있다). */
export interface ResolvedIndicatorSettings {
  enabled: boolean;
  placement: string;
  windows: string[];
  max_items: number;
  fields: string[];
  value_mode: "remaining" | "used";
  color_rules: UsageIndicatorColorRule[];
  hide_when_empty: boolean;
  also_in_title: boolean;
}

let defaultsCache: ResolvedIndicatorSettings | undefined;

/** 계약 스키마의 `default`에서 읽은 기본값(코드에 복사하지 않는다). */
export function indicatorDefaults(): ResolvedIndicatorSettings {
  defaultsCache ??= getDefaultValue(getContractSchema("UsageIndicatorSettings")) as ResolvedIndicatorSettings;
  return defaultsCache;
}

/** 저장된 값(생략 = 상속) 위에 스키마 기본값을 깔아 모든 키가 채워진 설정을 만든다. */
export function resolveIndicatorSettings(stored: UsageIndicatorSettings | null | undefined): ResolvedIndicatorSettings {
  return { ...indicatorDefaults(), ...(stored ?? {}) } as unknown as ResolvedIndicatorSettings;
}

/** 배치 id → 배치. 모르는 id면 `known=false`와 대체 배치. */
export function resolvePlacement(id: string): { placement: IndicatorPlacement; known: boolean } {
  const hit = INDICATOR_PLACEMENTS.find((p) => p.id === id);
  return hit === undefined ? { placement: FALLBACK_PLACEMENT, known: false } : { placement: hit, known: true };
}

/** `fields`에서 알려진 요소만(순서 유지, 중복 제거). 모르는 값은 `unknown`으로 따로 돌려준다. */
export function splitFields(fields: readonly string[]): { known: string[]; unknown: string[] } {
  const known: string[] = [];
  const unknown: string[] = [];
  for (const f of fields) {
    if (INDICATOR_FIELDS.includes(f)) {
      if (!known.includes(f)) known.push(f);
    } else if (!unknown.includes(f)) unknown.push(f);
  }
  return { known, unknown };
}
