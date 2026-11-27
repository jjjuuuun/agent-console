import { useMemo } from "react";
import { BUILTIN_EDGE_SHAPES, createElkEngine, localizeEdgeShapes, type GraphEditorLocale, type GraphEditorMessages, type LayoutEngineDescriptor } from "@agent-console/graph-editor";
import { useLibMessages, type MessageTree } from "@agent-console/i18n";
// 문구의 모양(키 목록)을 얻으려는 기본 묶음. 화면에 보이는 값은 현재 언어 묶음이 덮어쓴다.
import baseLocale from "@agent-console/graph-editor/locales/ko";

/** 현재 화면 언어의 그래프 편집기 문구 묶음(`messages`·`shapes`·`layout`). */
export function useGraphEditorLocale(): GraphEditorLocale {
  return useLibMessages("graph-editor", baseLocale as unknown as MessageTree) as unknown as GraphEditorLocale;
}

/** 편집기에 넘길 현재 언어의 값 묶음: 문구, 연결선 모양 이름, 자동 배치 엔진(옵션 기본값은 호출자가 준다). */
export function useGraphEditorProps(optionDefaults: Readonly<Record<string, number>>): {
  messages: GraphEditorMessages;
  edgeShapes: ReturnType<typeof localizeEdgeShapes>;
  layoutEngines: readonly LayoutEngineDescriptor[];
} {
  const locale = useGraphEditorLocale();
  const edgeShapes = useMemo(() => localizeEdgeShapes(BUILTIN_EDGE_SHAPES, locale.shapes), [locale.shapes]);
  const layoutEngines = useMemo(
    () => [createElkEngine({ optionDefaults, title: locale.layout.engineTitle, optionTitles: locale.layout.options })],
    [optionDefaults, locale.layout],
  );
  return { messages: locale.messages, edgeShapes, layoutEngines };
}
