/**
 * 캔버스 안의 연결선이 편집 기능을 쓰기 위한 연결 고리(React Flow가 엣지 컴포넌트에 props를 줄 수 없어 컨텍스트로 넘긴다).
 * 값이 없으면(Provider 밖·읽기 전용) 엣지는 편집 요소 없이 그려진다.
 */
import { createContext } from "react";
import type { EdgeLayoutPatch } from "../logic/edgeLayoutOps";
import type { Point } from "../logic/ops";
import type { GraphEditorMessages } from "../messages";

export interface EdgeEditApi {
  /** 편집 가능(읽기 전용이 아님) */
  editable: boolean;
  /** 경로 편집 모드(키보드)인 엣지 id */
  pathEditEdgeId: string | null;
  messages: GraphEditorMessages;
  snapGrid: number | false;
  /** 화면 좌표(clientX/Y) → 캔버스(플로우) 좌표 */
  screenToFlow: (p: Point) => Point;
  /** `layout` 패치 1회 = `onChange`(reason `layout`) 1회 */
  commit: (edgeId: string, patch: EdgeLayoutPatch) => void;
  /** 보조기술 알림(aria-live) */
  announce: (text: string) => void;
  /** 눈에 보이는 안내(토스트) */
  notify: (text: string) => void;
  /** 줌이 작아 조작 점이 숨겨질 때의 안내(편집기당 1회는 제공자가 보장) */
  zoomHint: () => void;
  /** 경로 편집 모드 종료(포커스는 엣지로) */
  exitPathEdit: (edgeId: string) => void;
}

export const EdgeEditContext = createContext<EdgeEditApi | null>(null);
