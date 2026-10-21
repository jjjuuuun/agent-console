/**
 * 자동 배치 엔진의 공개 계약(graph-edges §4.1, §4.4). 특정 배치 라이브러리(ELK 등)의 타입은 여기 나오지 않는다.
 * 엔진 목록·옵션은 이 선언에서 그리므로 새 엔진은 `LayoutEngineDescriptor` 하나를 더하면 팝오버에 나타난다.
 */
import type { Side } from "../shapes/types";

/** 옵션 선언 하나(JSON Schema 부분집합). 팝오버가 `type`에 맞는 소형 컨트롤로 그린다. */
export interface OptionDecl {
  key: string;
  title: string;
  type: "enum" | "number" | "boolean";
  default: string | number | boolean;
  /** `enum`일 때 선택지 */
  choices?: readonly { value: string; title: string }[];
  /** `number`일 때 범위·간격 */
  min?: number;
  max?: number;
  step?: number;
  description?: string;
}

/** 옵션 값 묶음(키 = `OptionDecl.key`). */
export type OptionValues = Readonly<Record<string, string | number | boolean>>;

/** 엔진에 넘기는 포트 하나: 어느 면에 붙는가. */
export interface LayoutPortInput {
  /** 핸들 id(노드 안에서 유일) */
  id: string;
  io: "in" | "out";
  side: Side;
}

export interface LayoutNodeInput {
  id: string;
  /** 현재 좌표(엔진이 필요하면 쓴다. 대부분 무시) */
  x: number;
  y: number;
  width: number;
  height: number;
  ports: readonly LayoutPortInput[];
}

export interface LayoutEdgeInput {
  id: string;
  kind: string;
  source: { node: string; /** 소스 포트의 핸들 id */ port: string };
  target: { node: string; port: string };
  /**
   * 되돌아가는 연결(디스크립터 `cycle`을 가진 종류). 엔진은 층 계산에서 이 연결이 흐름을 거스르는 연결로 다루고,
   * 도착 노드가 출발 노드보다 앞 층에 놓이게 한다. 생략 = 일반 연결.
   */
  back?: boolean;
}

/** 배치 요청. 엔진은 입력을 바꾸지 않는다. */
export interface LayoutRequest {
  nodes: readonly LayoutNodeInput[];
  edges: readonly LayoutEdgeInput[];
  /** 흐름이 나아가는 방향 = 출력 포트가 있는 면(예: 오른쪽 흐름이면 `right`). 방향 어휘 표에서 온 값 */
  flow: Side;
  options: OptionValues;
}

/** 배치 결과: 노드 id → 좌상단 좌표(경유점은 가져오지 않는다. 경로는 라우터 몫). */
export interface LayoutResult {
  positions: Readonly<Record<string, { x: number; y: number }>>;
}

/**
 * 엔진이 결과 좌표에 어울리는 연결선 모양을 권장할 때의 선언. 노드 위치만 바꾸는 엔진은 곡선이 노드를 가로지르게 둘 수 있어서,
 * [정리] 팝오버가 "연결선도 자동 경로로" 체크를 보여 준다(켜면 기본 모양 = `shapeId`). 모양 목록에 `shapeId`가 없으면 체크를 숨긴다.
 */
export interface EdgeShapeOption {
  /** 권장 모양 id (예: 노드를 피하는 자동 경로) */
  shapeId: string;
  /** 처음 열 때(기억한 값이 없을 때) 체크 여부 */
  default: boolean;
  /** 체크 문구(생략하면 메시지 `tidyAutoRoutes`) */
  title?: string;
}

export interface LayoutEngineDescriptor {
  id: string;
  title: string;
  options: readonly OptionDecl[];
  edgeShapeOption?: EdgeShapeOption;
  /**
   * 배치를 계산한다. `signal`이 중단되면 계산을 멈추고(워커 종료) `AbortError`로 거부한다.
   * 로드·계산 오류는 `Error`로 거부한다.
   */
  run(request: LayoutRequest, signal?: AbortSignal): Promise<LayoutResult>;
}

/** 옵션 선언의 기본값 묶음. */
export function defaultOptionValues(options: readonly OptionDecl[]): Record<string, string | number | boolean> {
  return Object.fromEntries(options.map((o) => [o.key, o.default]));
}

/** 저장되어 있던 값을 선언에 맞게 걸러 낸다: 선언에 없는 키·형식이 다른 값·범위 밖 숫자는 기본값으로 돌아간다. */
export function coerceOptionValues(options: readonly OptionDecl[], raw: unknown): Record<string, string | number | boolean> {
  const src = raw !== null && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  const out: Record<string, string | number | boolean> = {};
  for (const o of options) {
    const v = src[o.key];
    let ok: boolean;
    if (o.type === "number") ok = typeof v === "number" && Number.isFinite(v) && (o.min === undefined || v >= o.min) && (o.max === undefined || v <= o.max);
    else if (o.type === "boolean") ok = typeof v === "boolean";
    else ok = typeof v === "string" && (o.choices === undefined || o.choices.some((c) => c.value === v));
    out[o.key] = ok ? (v as string | number | boolean) : o.default;
  }
  return out;
}
