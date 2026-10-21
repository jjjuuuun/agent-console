/**
 * 연결선 모양 레지스트리와 내장 5종(graph-edges §1). 모양 종류는 목록에 항목을 더해 늘린다.
 * 화면·저장값 검증 코드는 `has`/`get`/`list`와 `supports*` 속성만 본다.
 */
import { bezierPath, orthogonalPath, straightPath } from "../logic/edgePath";
import { autoPath } from "../logic/route";
import type { EdgePathInput, EdgeShapeDescriptor } from "./types";

/** 내장 모양 5종. 순서가 목록·`S` 키 순환 순서다. */
export const BUILTIN_EDGE_SHAPES: readonly EdgeShapeDescriptor[] = [
  {
    id: "bezier",
    title: "곡선",
    description: "부드러운 곡선. 경유점을 지나는 스플라인",
    preview: "M1,8 C10,8 14,2 23,2",
    supportsWaypoints: true,
    supportsBend: false,
    supportsRadius: false,
    build: bezierPath,
  },
  {
    id: "smoothstep",
    title: "직각(둥근 모서리)",
    description: "가로·세로 선분과 둥근 모서리",
    preview: "M1,8 H8 Q12,8 12,5 Q12,2 16,2 H23",
    supportsWaypoints: true,
    supportsBend: true,
    supportsRadius: true,
    build: orthogonalPath,
  },
  {
    id: "step",
    title: "직각(각진 모서리)",
    description: "가로·세로 선분, 모서리를 둥글리지 않음",
    preview: "M1,8 H12 V2 H23",
    supportsWaypoints: true,
    supportsBend: true,
    supportsRadius: false,
    build: (input: EdgePathInput) => orthogonalPath({ ...input, radius: 0 }),
  },
  {
    id: "straight",
    title: "직선",
    description: "시작에서 끝까지 직선(경유점을 순서대로 지남)",
    preview: "M1,8 L23,2",
    supportsWaypoints: true,
    supportsBend: false,
    supportsRadius: false,
    build: straightPath,
  },
  {
    id: "auto",
    title: "자동 경로",
    description: "직각 경로. 렌더 시 노드를 피하도록 다시 계산",
    preview: "M1,8 H6 V2 H18 V8 H23",
    supportsWaypoints: true,
    supportsBend: false,
    supportsRadius: true,
    route: "obstacle-avoiding",
    // 노드를 모르는 단독 계산(A*, 장애물 없음). 노드 회피는 EdgeRouter(logic/route.ts)가 장애물을 받아 계산한다.
    build: autoPath,
  },
];

/** 모양 목록을 id로 찾는 읽기 전용 색인. */
export interface EdgeShapeRegistry {
  /** 등록 순서 */
  readonly list: readonly EdgeShapeDescriptor[];
  has(id: string): boolean;
  get(id: string): EdgeShapeDescriptor | undefined;
}

/**
 * 모양 레지스트리를 만든다. 같은 id가 여럿이면 뒤의 것이 앞의 것을 대신한다(위치는 처음 등장한 자리).
 * 인자를 생략하면 내장 5종.
 */
export function createEdgeShapeRegistry(shapes: readonly EdgeShapeDescriptor[] = BUILTIN_EDGE_SHAPES): EdgeShapeRegistry {
  const byId = new Map<string, EdgeShapeDescriptor>();
  for (const s of shapes) byId.set(s.id, s);
  const list = [...byId.values()];
  return { list, has: (id) => byId.has(id), get: (id) => byId.get(id) };
}
