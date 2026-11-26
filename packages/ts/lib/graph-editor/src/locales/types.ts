import type { GraphEditorMessages } from "../messages";

/** 문구 한 덩어리: 내장 연결선 모양 하나의 이름·설명. */
export interface ShapeText {
  title: string;
  description: string;
}

/** 그래프 편집기 문구 묶음 한 언어분. */
export interface GraphEditorLocale {
  /** `GraphEditor`의 `messages` prop */
  messages: GraphEditorMessages;
  /** 내장 연결선 모양 id → 이름·설명(`localizeEdgeShapes`로 모양 목록에 입힌다) */
  shapes: Readonly<Record<string, ShapeText>>;
  /** 자동 배치 엔진 문구(`createElkEngine({ title, optionTitles })`에 넘긴다) */
  layout: {
    engineTitle: string;
    /** 옵션 키 → 이름 */
    options: Readonly<Record<string, string>>;
  };
}
