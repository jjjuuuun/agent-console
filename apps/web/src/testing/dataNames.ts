/**
 * 서버 데이터인 이름(연결 종류·리소스 종류·상호작용 종류·사용량 창·모델). 앱 코드와 문구 표에 따옴표 문자열로 나오면 안 된다.
 * 하드코딩 점검 테스트가 함께 쓰는 단일 목록이다(예시 이름일 뿐이며 서버 쪽 데이터가 늘어도 앱은 이 값을 몰라야 한다).
 */
export const DATA_NAMES: readonly string[] = [
  // 연결 종류
  "subagent", "handoff", "uses", "ask_user",
  // 리소스 종류
  "instruction", "mcp_server", "permission", "claude_md",
  // 상호작용 종류
  "question", "tool_permission",
  // 사용량 창
  "five_hour", "seven_day", "weekly", "primary_window",
  // 모델
  "opus", "sonnet", "haiku",
  // 로그 출처·수집기·지표(서버 데이터. 4R.17: 로그 화면은 이 이름을 코드에 두지 않는다)
  "claude-code-jsonl", "platform-runs", "hook-probe-jsonl", "normalized-v1", "mapped-jsonl", "local-logs",
  "tokens.total", "tokens.input", "tokens.output", "tokens.cache_read", "tokens.cache_creation",
  // 로그 범주·이벤트 종류(분류 체계 기본 프리셋의 예. 범주는 사용자가 정하는 데이터다)
  "hook", "mcp", "tool_use", "tool_result", "prompt", "assistant", "thinking", "pretooluse", "posttooluse", "userpromptsubmit", "sessionstart", "sessionend",
];

const SEP = "[:._/-]";
const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * 따옴표 문자열 리터럴이 데이터 이름인지 찾는 정규식(5R.21). 정확히 같은 이름뿐 아니라
 * 대소문자 변형(`Hook`·`MCP`)과 접두·접미 변형(`hook:pre`·`mcp.call`·`log_hook`)도 같은 이름으로 본다.
 * `hooked`처럼 구분자 없이 붙은 낱말은 다른 낱말이다.
 */
export function dataNameLiteral(name: string): RegExp {
  const n = escapeRe(name);
  return new RegExp(`(["'\`])(?:${n}|${n}${SEP}[^"'\`\\n]*|[^"'\`\\n]*${SEP}${n})\\1`, "i");
}

/** 한 줄에서 `name`(변형 포함)에 해당하는 따옴표 문자열 리터럴 내용을 모두 돌려준다. */
export function findDataNameLiterals(line: string, name: string): string[] {
  const re = new RegExp(dataNameLiteral(name).source, "gi");
  return [...line.matchAll(re)].map((m) => m[0].slice(1, -1));
}

/**
 * 변형 검사(접두·접미·대소문자)에서 알고 허용하는 리터럴. 새 항목은 이유와 함께만 더한다(기본은 금지).
 * `file`은 `apps/web/src` 기준 경로, 이유는 "계약 필드 이름"(값이 아니라 서버가 정한 필드 이름) 또는 부채.
 */
export const ALLOWED_VARIANT_LITERALS: readonly { file: string; literal: string; reason: string }[] = [
  { file: "features/chat/lib/liveRun.ts", literal: "subagent_id", reason: "계약 이벤트 payload 필드 이름" },
  { file: "features/runs/ObserveTab.tsx", literal: "tool_use_id", reason: "계약 이벤트 payload 필드 이름" },
  { file: "features/runs/messages.ts", literal: "tool_use_id", reason: "payload 필드 이름을 보이는 문구" },
  { file: "features/runs/runsConfig.ts", literal: "hook.", reason: "부채: 관측 탭 이벤트 type 접두 표(서버 데이터화 후보, 5R.21 보고)" },
  { file: "features/runs/runsConfig.ts", literal: "mcp.", reason: "부채: 관측 탭 이벤트 type 접두 표(서버 데이터화 후보, 5R.21 보고)" },
];

/** 리터럴 변형 검사에서 허용된 항목인지. */
export function isAllowedVariant(file: string, literal: string): boolean {
  const f = file.replaceAll("\\", "/");
  return ALLOWED_VARIANT_LITERALS.some((a) => a.file === f && a.literal === literal);
}

/**
 * 정확히 같은 이름의 따옴표 리터럴 검사(노드 타입 id 같은 일반 낱말)에서 알고 허용하는 항목. 새 항목은 이유와 함께만 더한다(기본은 금지).
 * 노드 타입과 우연히 같은 낱말이지만 다른 데이터(예: 설정 층 id)를 가리키는 경우다.
 */
export const ALLOWED_EXACT_LITERALS: readonly { file: string; name: string; reason: string }[] = [
  { file: "features/teams/TeamPanel.tsx", name: "team", reason: "설정 층 id: 서버 TeamConventions.team_layer 기본값(출처 표시 키). 노드 타입 id가 아니다" },
  { file: "features/delegation/eventSummaryMap.ts", name: "condition", reason: "계약 RunEvent payload 키(조건 판정 근거). 이벤트 매핑 표 한 파일의 예외" },
  { file: "features/settings/sections/ServerSection.tsx", name: "host", reason: "서버 바인딩 호스트(설정 키). 위임 방식 id가 아니다" },
  { file: "features/usage/usageConfig.ts", name: "host", reason: "사용량 표시기를 꽂는 셸 자리 이름. 위임 방식 id가 아니다" },
  { file: "features/delegation/eventSummaryMap.ts", name: "max_iterations", reason: "계약 RunEvent payload 키(반복 한도 도달 이벤트). 이벤트 매핑 표 한 파일의 예외(screen-delegation 0.1)" },
];

/** 정확히 같은 이름 검사에서 허용된 항목인지. */
export function isAllowedExact(file: string, name: string): boolean {
  const f = file.replaceAll("\\", "/");
  return ALLOWED_EXACT_LITERALS.some((a) => a.file === f && a.name === name);
}

/**
 * 독립 위임·반복·조건·중첩 팀 화면이 코드·테스트에 쓰면 안 되는 종류·연산자·설정 키 이름(정확히 같은 따옴표 문자열만 본다, screen-delegation 0·11).
 * 모두 예시(데이터)이며 화면은 디스크립터 속성(`cycle`·`handles_failure`·`invocation`·`binds`)과 서버 목록만 본다.
 */
export const DELEGATION_NAMES: readonly string[] = ["delegate", "loop", "when", "on_error", "team", "host", "eq", "contains", "max_iterations", "conditions", "team_ref"];
