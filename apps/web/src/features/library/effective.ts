import type { EffectiveSettings } from "@agent-console/contracts";
import type { ProvenanceLayer } from "@agent-console/schema-form";
import type { ProvenanceLayer as UiLayer } from "@agent-console/ui";
import { withoutLayer } from "../../lib/sparse";

/** 서버 유효 설정의 층 목록(낮은 우선순위가 앞)을 폼 층 목록으로. 층 이름은 서버가 정한다. */
export function toFormLayers(eff: EffectiveSettings | undefined): ProvenanceLayer[] {
  return (eff?.layers ?? []).map((l) => ({ id: l.id, label: l.label && l.label !== "" ? l.label : l.id }));
}

/** 가장 높은 우선순위 층(편집 중인 층) id. */
export function editLayerOf(eff: EffectiveSettings | undefined): string | undefined {
  return eff?.layers?.[eff.layers.length - 1]?.id;
}

/** 편집 층이 정한 값을 뺀 출처 표: 폼에서 "상속된 값은 어느 층에서 왔나"만 남긴다. */
export function inheritedProvenance(eff: EffectiveSettings | undefined, editLayerId: string | undefined): Record<string, string> {
  return Object.fromEntries(Object.entries(eff?.provenance ?? {}).filter(([, layer]) => layer !== editLayerId));
}

/** 편집 층 아래 층들이 만든 값(근사: 편집 층이 덮어쓴 잎의 아래 값은 서버가 주지 않아 비운다). */
export function inheritedValue(eff: EffectiveSettings | undefined, editLayerId: string | undefined): unknown {
  return eff === undefined ? undefined : withoutLayer(eff.value, eff.provenance, editLayerId);
}

/** 표시용 층 목록(색 순서용 `index` 포함). 첨부 목록 같은 ui 컴포넌트에 넘긴다. */
export function toUiLayers(eff: EffectiveSettings | undefined): UiLayer[] {
  return toFormLayers(eff).map((l, index) => ({ ...l, index }));
}
