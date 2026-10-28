/**
 * 테스트·목(mock)용 예제 `ArchitectureView`.
 * `defaultProfileView()`는 docs/design/screen-architecture.md §9의 기본 프로필(칸 16·연결 21·영역 3) 좌표를 그대로 옮긴 것이다.
 * 지표 값은 임시 숫자이고 서버 응답이 아니다. 컴포넌트는 이 파일을 import하지 않는다(앱·테스트가 쓴다).
 */
import type {
  ArchitectureCellView,
  ArchitectureEdgeView,
  ArchitectureMetric,
  ArchitectureView,
  ArchitectureZone,
} from "@agent-console/contracts/architecture";

const obs = (value: number): ArchitectureMetric => ({ status: "observed", value });
export const notCollected = (): ArchitectureMetric => ({ status: "not_collected", value: null });

type CellRow = [id: string, label: string, description: string, x: number, y: number, zone: string, tone: string, metrics: string[], extra?: Partial<ArchitectureCellView>];
const CELLS: CellRow[] = [
  ["input", "Task input", "최초 과제 · 실행 지시", 130, 130, "local", "blue", ["count"]],
  ["sdk", "SDK / CLI", "실행 진입점", 470, 130, "local", "blue", ["count", "errors"]],
  ["api", "에이전트 제어", "세션 · 실행 제어", 810, 130, "local", "teal", ["count", "errors"]],
  ["rules", "Rules", "CLAUDE.md · rules", 130, 280, "local", "gold", ["count"], { status: "partial", partial_reason: "도구로 연 문서만 보임(자동 로드는 기록 없음)" }],
  ["instructions", "Instructions · Skills", "SPEC · AGENTS.md · Skill", 470, 280, "runtime", "gold", ["count"]],
  ["context", "Context builder", "모델 입력 준비", 810, 280, "runtime", "teal", ["count"]],
  ["llm", "LLM", "원격 모델 API", 1400, 280, "remote", "purple", ["count", "errors", "tokens", "inferred_duration"]],
  ["dispatch", "Dispatcher", "모델 출력 처리 · 도구 선택", 1150, 580, "runtime", "teal", ["count"]],
  ["hook", "Hook", "도구 전후 검사", 810, 580, "runtime", "pink", ["count", "errors", "duration"], { status: "not_collected" }],
  ["tools", "Tool handler", "내장 도구", 470, 580, "runtime", "orange", ["count", "errors", "duration"]],
  ["mcp", "MCP 서버", "외부 도구 연동 (위치는 설정에 따름)", 1150, 430, "runtime", "orange", ["count", "errors", "duration"]],
  ["result", "Tool result", "호출 ID에 대응하는 결과", 810, 430, "runtime", "teal", ["count", "errors"]],
  ["workspace", "Workspace", "로컬 파일 · 명령 실행", 470, 430, "runtime", "blue", ["count"]],
  ["delegation", "Delegation · Merge", "위임 · 결과 통합", 130, 580, "local", "gold", ["count", "errors"]],
  ["subagents", "서브에이전트", "위임받아 실행 (누르면 하위 구조도)", 130, 430, "local", "gold", ["count", "errors", "tokens"], { drillable: true }],
  ["response", "Agent response", "중간 메시지 · 최종 응답", 1150, 730, "runtime", "blue", ["count"]],
];

const metricValues: Record<string, ArchitectureMetric> = {
  count: obs(12),
  errors: obs(0),
  tokens: obs(41203),
  duration: { status: "observed", value: 1200, detail: { samples: 4, total_ms: 4800, avg_ms: 1200, max_ms: 2100 } },
  inferred_duration: { status: "inferred", value: 1200 },
};

export function sampleCell(id: string, over: Partial<ArchitectureCellView> = {}): ArchitectureCellView {
  return {
    id,
    label: id,
    w: 180,
    h: 68,
    status: "observed",
    metrics: { count: obs(1) },
    selector: { arch: `p:cell:${id}` },
    ...over,
  };
}

export function sampleEdge(id: string, from: string, to: string, over: Partial<ArchitectureEdgeView> = {}): ArchitectureEdgeView {
  return { id, from, to, label: id, kind: "observed", style: "request", status: "observed", metrics: { count: obs(1) }, selector: { arch: `p:edge:${id}` }, ...over };
}

type EdgeRow = [id: string, from: string, to: string, label: string, kind: "observed" | "structural", style: string, points: [number, number][], at: [number, number], maxW: number | null, metrics: string[]];
const EDGES: EdgeRow[] = [
  ["task_submit", "input", "sdk", "과제 전달", "observed", "request", [[226, 130], [374, 130]], [300, 130], null, ["count"]],
  ["control_request", "sdk", "api", "제어 요청", "observed", "request", [[566, 112], [714, 112]], [640, 112], null, ["count", "errors"]],
  ["control_response", "api", "sdk", "ID / 응답", "structural", "inferred", [[714, 148], [566, 148]], [640, 148], null, []],
  ["context_prepare", "api", "context", "문맥 준비", "structural", "inferred", [[810, 170], [810, 240]], [810, 191], null, []],
  ["instructions_apply", "instructions", "context", "지침 반영", "structural", "inferred", [[566, 280], [714, 280]], [640, 280], null, []],
  ["model_request", "context", "llm", "모델 요청", "structural", "inferred", [[906, 280], [1304, 280]], [1105, 280], null, []],
  ["model_output", "llm", "dispatch", "모델 출력", "observed", "return", [[1400, 320], [1400, 580], [1246, 580]], [1400, 450], null, ["count", "errors"]],
  ["tool_call", "dispatch", "tools", "도구 호출", "observed", "request", [[1110, 620], [1110, 655], [440, 655], [440, 620]], [775, 655], null, ["count", "errors", "duration"]],
  ["delegation_tools", "delegation", "tools", "위임/통합", "structural", "inferred", [[226, 580], [374, 580]], [300, 580], null, []],
  ["local_work", "tools", "workspace", "로컬 작업", "structural", "inferred", [[440, 540], [440, 470]], [440, 505], null, []],
  ["work_result", "workspace", "result", "작업 결과", "observed", "return", [[566, 430], [714, 430]], [640, 430], null, ["count"]],
  ["tool_result", "tools", "result", "도구 결과", "observed", "return", [[510, 540], [510, 505], [780, 505], [780, 470]], [645, 505], null, ["count", "errors"]],
  ["next_context", "result", "context", "다음 요청에 반영", "structural", "inferred", [[810, 390], [810, 320]], [810, 355], null, []],
  ["final_response", "dispatch", "response", "메시지 전달", "observed", "return", [[1190, 620], [1190, 690]], [1190, 655], null, ["count"]],
  ["rule_load", "rules", "instructions", "규칙 로드", "structural", "inferred", [[226, 280], [374, 280]], [300, 280], null, []],
  ["hook_run", "dispatch", "hook", "hook 실행", "observed", "request", [[1054, 580], [906, 580]], [980, 580], null, ["count", "errors", "duration"]],
  ["hook_verdict", "hook", "tools", "허용·차단", "observed", "request", [[714, 580], [566, 580]], [640, 580], null, ["count", "errors"]],
  ["mcp_call", "dispatch", "mcp", "MCP 호출", "observed", "request", [[1150, 540], [1150, 470]], [1150, 505], null, ["count", "errors", "duration"]],
  ["mcp_result", "mcp", "result", "MCP 결과", "observed", "return", [[1054, 430], [906, 430]], [980, 430], null, ["count", "errors"]],
  ["delegate", "delegation", "subagents", "위임", "observed", "request", [[80, 540], [80, 470]], [80, 505], 92, ["count", "errors"]],
  ["merge", "subagents", "delegation", "결과 통합", "observed", "return", [[180, 470], [180, 540]], [180, 505], 92, ["count", "errors"]],
];

const ZONES: ArchitectureZone[] = [
  { id: "local", label: "LOCAL · 사용자 PC", description: "하네스 · SDK / CLI · 에이전트 런타임 · 작업 파일", x: 10, y: 16, w: 1260, h: 780, style: "boundary" },
  { id: "remote", label: "REMOTE · 모델 서버", description: "네트워크로 모델 요청 / 응답", x: 1290, y: 16, w: 220, h: 780, style: "service" },
  { id: "runtime", label: "모델 입력 준비 · 출력 처리 · 도구 순환", x: 370, y: 212, w: 880, h: 572, style: "runtime" },
];

/** 기본 프로필의 좌표를 그대로 옮긴 구조도(칸 16·연결 21·영역 3, 캔버스 1520×812). 지표는 임시 값이다. */
export function defaultProfileView(): ArchitectureView {
  const cells = CELLS.map(([id, label, description, x, y, zone, tone, metrics, extra]) =>
    sampleCell(id, {
      label, description, x, y, zone, tone,
      status: "observed",
      metrics: Object.fromEntries(metrics.map((m) => [m, extra?.status === "not_collected" ? notCollected() : (metricValues[m] as ArchitectureMetric)])),
      ...extra,
    }),
  );
  const edges = EDGES.map(([id, from, to, label, kind, style, points, at, maxW, metrics]) =>
    sampleEdge(id, from, to, {
      label, kind, style, points, label_at: at, label_max_w: maxW,
      metrics: Object.fromEntries(metrics.map((m) => [m, metricValues[m] as ArchitectureMetric])),
      selector: kind === "observed" ? { arch: `agent-architecture:edge:${id}` } : null,
    }),
  );
  return {
    profile: "agent-architecture",
    title: "에이전트 아키텍처",
    canvas: { width: 1520, height: 812 },
    zones: ZONES,
    cells,
    edges,
    unassigned: null,
    unavailable: [{ cell: "llm", item: "LLM 요청 본문", reason: "로그에 남지 않음" }],
    sources: [],
    event_total: 1204,
    max_seq: 1204,
    notes: [],
  };
}
