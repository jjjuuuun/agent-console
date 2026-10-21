/**
 * 캔버스 안의 노드 핸들이 포트 면 이동을 쓰기 위한 연결 고리(React Flow가 노드 컴포넌트에 props를 줄 수 없어 컨텍스트로 넘긴다).
 * 값이 없으면(Provider 밖) 핸들은 이동 기능 없이 그려진다.
 */
import { createContext } from "react";
import type { GraphEditorMessages } from "../messages";
import type { Side } from "../shapes/types";

export interface PortEditApi {
  /** 편집 가능(읽기 전용이 아님) */
  editable: boolean;
  messages: GraphEditorMessages;
  /** 포트 면을 정한다. 1회 = `onChange`(reason `layout`) 1회 */
  setPortSide: (nodeId: string, io: "in" | "out", portId: string, label: string, side: Side) => void;
  /** 보조기술 알림(aria-live) */
  announce: (text: string) => void;
}

export const PortEditContext = createContext<PortEditApi | null>(null);
