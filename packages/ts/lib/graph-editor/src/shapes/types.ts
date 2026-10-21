/**
 * 연결선 모양 레지스트리의 타입(graph-edges §1.1, §2.1). React Flow에 의존하지 않는다.
 */
import type { Point } from "../logic/ops";

/** 핸들이 붙은 노드의 면. 경로 계산은 이 4값만 안다(포트 면 `auto`는 호출자가 풀어서 넘긴다). */
export type Side = "left" | "right" | "top" | "bottom";

/** 선의 끝점: 좌표와, 그 점이 놓인 노드 면(바깥 법선 방향을 정한다). */
export interface EdgeEndpoint extends Point {
  side: Side;
}

/** 모양 `build`가 받는 입력. `source`/`target`은 이미 `arrowGap`만큼 면 바깥으로 옮긴 선의 시작·끝이다. */
export interface EdgePathInput {
  /** 선의 시작(핸들에서 면 바깥으로 arrowGap 떨어진 점) */
  source: EdgeEndpoint;
  /** 선의 끝(화살촉 끝) */
  target: EdgeEndpoint;
  /** 경유점(캔버스 절대 좌표, 소스 → 타깃 순서). 모양이 경유점을 지원하지 않으면 빈 배열 */
  waypoints: readonly Point[];
  /** 모서리 반경 px(0 이상, 이미 보정됨) */
  radius: number;
  /** 꺾임 위치 0~1(이미 보정됨) */
  bend: number;
  /** 선의 시작·끝에서 면 바깥쪽으로 먼저 내는 직선 길이 px(핸들 기준 스텁에서 arrowGap을 뺀 값) */
  stub: number;
}

/** 경로를 펴서 만든 선분. 라벨 위치·교차 검사·점 투영에 쓴다. */
export interface EdgeSegment {
  from: Point;
  to: Point;
}

/** 경로 위의 한 점과 그 지점의 진행 각도(라디안). */
export interface PathPointAt extends Point {
  angle: number;
}

/** 모양 `build`의 결과. */
export interface EdgePathResult {
  /** SVG path d */
  d: string;
  /**
   * 라벨 위치 t(0~1)의 점. 범위를 벗어나면 0~1로 자른다.
   * t는 보통 경로 길이의 비율이다. 예외: 경유점 없는 `bezier`는 3차 베지어 매개변수 t(0.5 = 기존 라벨 위치, graph-edges §2.3).
   */
  labelAt(t: number): PathPointAt;
  /** 경로를 편 선분들(곡선은 잘게 나눈 근사) */
  segments: readonly EdgeSegment[];
  /** 편 경로의 길이 px */
  length: number;
}

/**
 * 연결선 모양 하나. 모양 선택 UI·저장값 검증·경로 계산은 이 목록만 본다.
 * 화면 코드는 모양 id를 비교하지 말고 `supports*` 속성으로 분기한다.
 */
export interface EdgeShapeDescriptor {
  /** 저장값. 예 "smoothstep" */
  id: string;
  /** 목록 표시 이름 */
  title: string;
  description?: string;
  /** 24x10 SVG path d(목록 아이콘) */
  preview: string;
  supportsWaypoints: boolean;
  supportsBend: boolean;
  supportsRadius: boolean;
  /** 있으면 노드 회피 라우터를 쓸 수 있는 모양(§4.2). 라우터가 없으면 `build` 결과를 그대로 쓴다. */
  route?: "obstacle-avoiding";
  /** 순수 함수. */
  build(input: EdgePathInput): EdgePathResult;
}
