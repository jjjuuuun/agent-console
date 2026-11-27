import { useMemo } from "react";
import type { EdgeTypeDescriptor, NodeTypeDescriptor, PortDef, PortSpec, UiHints } from "@agent-console/contracts";
import { useServerTranslate } from "./useServerTranslate";

type Translate = (text: string) => string;

const portOf = (tr: Translate) => (port: PortDef): PortDef => ({
  ...port,
  ...(typeof port.label === "string" ? { label: tr(port.label) } : {}),
  ...(typeof port.description === "string" ? { description: tr(port.description) } : {}),
});

/** 포트 명세의 라벨·설명(서버 원문)을 화면 언어로 옮긴다. 이름(`name`)은 식별자라 그대로 둔다. */
export function localizePortSpec(spec: PortSpec, tr: Translate): PortSpec {
  const map = portOf(tr);
  return {
    ...spec,
    ...(spec.inputs ? { inputs: spec.inputs.map(map) } : {}),
    ...(spec.outputs ? { outputs: spec.outputs.map(map) } : {}),
  };
}

/** 배지·아바타 글자(서버 원문일 수 있다)를 옮긴다. 이모지 같은 글자는 묶음에 없어 그대로다. */
function localizeHints(hints: UiHints, tr: Translate): UiHints {
  // 선언형 배지·칩(`badges`·`chips`)의 label 폴백 문구도 서버 원문이다
  const declared = (key: "badges" | "chips"): Record<string, unknown> => {
    const list = hints[key];
    if (!Array.isArray(list)) return {};
    return { [key]: list.map((item: unknown) => (typeof item === "object" && item !== null && typeof (item as { label?: unknown }).label === "string" ? { ...item, label: tr((item as { label: string }).label) } : item)) };
  };
  return {
    ...hints,
    ...(typeof hints.badge === "string" ? { badge: tr(hints.badge) } : {}),
    ...(typeof hints.icon === "string" ? { icon: tr(hints.icon) } : {}),
    ...declared("badges"),
    ...declared("chips"),
  };
}

/** 노드 타입 서술자의 보이는 글자(제목·설명·포트 라벨·배지)를 옮긴다. 아이디·스키마·카테고리(그룹 키·색 기준)는 그대로. */
export function localizeNodeType(d: NodeTypeDescriptor, tr: Translate): NodeTypeDescriptor {
  return {
    ...d,
    title: tr(d.title),
    // 카테고리는 일부러 옮기지 않는다: 그룹 묶음·분류색은 원래 카테고리 글자(서버 원문)로 정해지므로, 옮기면 언어마다 색이 달라진다.
    // 보이는 이름만 편집기의 `categoryLabel`(서버 번역 함수)로 옮긴다.
    ...(d.description !== undefined ? { description: tr(d.description) } : {}),
    ...(d.static_ports ? { static_ports: localizePortSpec(d.static_ports, tr) } : {}),
    ...(d.ui_hints ? { ui_hints: localizeHints(d.ui_hints, tr) } : {}),
  };
}

/** 연결 타입 서술자의 보이는 글자(제목·설명)를 옮긴다. */
export function localizeEdgeType(d: EdgeTypeDescriptor, tr: Translate): EdgeTypeDescriptor {
  return {
    ...d,
    title: tr(d.title),
    ...(d.description !== undefined ? { description: tr(d.description) } : {}),
    ...(d.ui_hints ? { ui_hints: localizeHints(d.ui_hints, tr) } : {}),
  };
}

/** 서버가 준 노드·연결 타입 서술자 목록을 현재 화면 언어로 옮긴 목록(입력이 같고 언어가 같으면 같은 배열). */
export function useLocalizedTypes<T extends NodeTypeDescriptor | EdgeTypeDescriptor>(list: readonly T[], kind: "node" | "edge"): readonly T[] {
  const tr = useServerTranslate();
  return useMemo(
    () => list.map((d) => (kind === "node" ? (localizeNodeType(d as NodeTypeDescriptor, tr) as T) : (localizeEdgeType(d as EdgeTypeDescriptor, tr) as T))),
    [list, kind, tr],
  );
}

/** `resolvePorts`가 돌려주는 포트 명세(동적 포트)도 같은 방식으로 옮기는 감싸개. */
export function useLocalizedResolvePorts(
  resolve: ((typeId: string, config: unknown) => Promise<PortSpec>) | undefined,
): ((typeId: string, config: unknown) => Promise<PortSpec>) | undefined {
  const tr = useServerTranslate();
  return useMemo(() => (resolve ? async (typeId, config) => localizePortSpec(await resolve(typeId, config), tr) : undefined), [resolve, tr]);
}
