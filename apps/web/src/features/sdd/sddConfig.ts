/**
 * 스펙(SDD) 화면의 데이터 표(`docs/design/screen-sdd.md`). 수치·저장소 키·주소 인자 이름이 전부 여기 있고 화면 코드는 이 표만 읽는다.
 * 문서 종류·문서 상태·작업 상태·단계·프로필 이름은 이 파일에도 없다(서버 데이터). 계약이 이름 붙인 어휘(`KNOWN_*`)만 계약 상수로 읽는다.
 */
import { KNOWN_TASK_LINK_KINDS, KNOWN_TRANSITION_ACTORS } from "@agent-console/contracts/constants";
import data from "./sddData.json";

/** 이 화면이 맡는 역할(라우트 `serves`·`requires`와 같은 값). 모듈 id가 아니다. */
export const SDD_ROLE = "sdd";
/** 사용자 설정 섹션 이름(공통 설정 문서의 키, 계약 `SddSettings`). */
export const SDD_SETTINGS_SECTION = "sdd";
/** 공용 구성 › 문서 틀 화면의 역할(라우트 `serves`). 서버 모듈 역할이 아니라 화면 역할이다. */
export const SDD_TEMPLATES_ROLE = "sdd:templates";

/** 주소 인자 이름(`sddData.json`). 선택·거르기는 URL이 진실이다. */
export const SDD_PARAMS: Readonly<Record<keyof typeof data.params, string>> = data.params;

/** 스펙 목록 열 머리 정렬(데이터): 기본 정렬, 열 id·문구 키·처음 누를 때 방향. 비교 함수는 `SpecListScreen`의 `SPEC_COMPARATORS`가 id로 찾는다. */
export const SPEC_SORT = data.specSort as {
  default: { id: string; direction: "asc" | "desc" };
  columns: readonly { id: string; labelKey: string; firstDirection: "asc" | "desc" }[];
};

/** 상세 탭 목록(데이터). 탭 본문은 `sddTabs`의 등록 표가 그린다 — 본문이 등록되지 않은 탭은 줄에 나오지 않는다. */
export const SDD_TAB_DEFS: readonly { id: string; labelKey: string }[] = data.tabs;
export const DEFAULT_TAB: string = data.defaultTab;

/** 화면 상태를 저장하는 localStorage 키(서버 설정이 아니다). */
export const SDD_STORAGE = {
  tab: (specId: string) => `ac.sdd.tab.${specId}`,
  lastTemplate: (projectId: string | null) => `ac.sdd.lasttemplate.${projectId ?? ""}`,
  docView: "ac.sdd.docview",
  /** 작업 탭 단계 접힘(스펙별, 사용자가 바꾼 단계만: 단계 키 → 접힘 여부) */
  stage: (specId: string) => `ac.sdd.stage.${specId}`,
} as const;

export const SDD_LIMITS = {
  /** `sdd.changed` 뒤 질의를 다시 하는 디바운스(ms) */
  liveDebounceMs: 300,
  /** 작업 검색 서버 질의 디바운스(ms) */
  searchDebounceMs: 250,
  /** 편집 영역이 이 폭 이상일 때만 "나란히" 보기가 기본이다(`--ac-sdd-split-min-w`) */
  splitMinWidth: 880,
  /** 이 뷰포트 폭 이상이면 문서 편집기가 처음부터 "나란히"(사이드바·문서 목록 폭을 더한 값) */
  splitViewportMin: 1360,
  /** 문서 틀이 이 수 이상이면 검색 칸이 나온다 */
  templateSearchMin: 8,
  /** 작업 동작 목록을 다시 묻지 않는 시간(ms, 같은 행 재열기는 캐시) */
  actionsStaleMs: 30_000,
  /** 이름 최대 글자 수 */
  nameMax: 100,
  /** 규칙 초안이 바뀐 뒤 자동 검사까지 기다리는 시간(ms, screen-sdd §10.2) */
  checkDebounceMs: 600,
  /** 목록 로딩 스켈레톤을 보이기 전 지연(ms) */
  skeletonDelayMs: 150,
} as const;

/** 사람이 UI에서 하는 전환 주체(계약 어휘). */
export const HUMAN_ACTOR: string = KNOWN_TRANSITION_ACTORS.HUMAN;
/** 작업 연결 중 실행 칩으로 여는 연결 종류(계약 어휘) */
export const RUN_LINK_KIND: string = KNOWN_TASK_LINK_KINDS.RUN;
/** 앱이 링크로 여는 연결 종류(`sddData.json`) */
export const OPENABLE_LINK_KINDS: readonly string[] = data.taskLinkKinds;

export interface ToneDisplay {
  tone: string;
  labelKey?: string;
  hintKey?: string;
}

/** 추적 표의 빈 곳 코드 → 톤·문구 키. 모르는 코드는 `gapFallbackTone` + 코드 원문(6R.21이 쓴다). */
export function gapDisplay(code: string): ToneDisplay {
  const known = (data.gaps as Record<string, ToneDisplay | undefined>)[code];
  return known ?? { tone: data.gapFallbackTone };
}

/** 검증 결과 값 → 톤·문구 키. 모르는 값(사용자가 정한 결과 이름)은 중립 + 원문. */
export function verificationDisplay(result: string): ToneDisplay {
  const known = (data.verification as Record<string, ToneDisplay | undefined>)[result];
  return known ?? { tone: data.verificationFallbackTone };
}

/** 문서 응답·저장 응답 이슈 중 이 앱이 따로 다루는 코드(`sddData.json`). 위치만 있고 값은 없다. */
export const SECRET_SUSPECT_CODE: string = data.issueCodes.secretSuspect;

/** 실행 상태(Run 상태 원문) → 톤. 문구는 앱 공용 실행 상태 표가 맡고, 모르는 상태는 중립(`sddData.json`). */
export const RUN_STATUS_TONES: Readonly<Record<string, string>> = data.runStatusTones;
/** 이 작업 수를 넘으면 계획 그래프를 자동으로 그리지 않고 글 목록을 권한다. */
export const PLAN_GRAPH_AUTO_LIMIT: number = data.planGraphAutoLimit;
/** 스펙 규칙의 자동 진행 필드 이름(계약 `AutomationConfig`, `sddData.json`). */
export const AUTOMATION_FIELDS = data.automationRules;
/** 자동 진행 조작 이름(서버 경로의 끝, `sddData.json`). */
export const AUTOMATION_OPS: Readonly<{ stop: string; resume: string }> = data.automationOps;

/** 값 목록을 같은 폼의 배열에서 얻는 참조 위젯: 계약 `KNOWN_UI_WIDGETS` 상수 이름 → 값 안의 배열 위치(`sddData.json`). 위젯 이름 문자열은 코드에 없다. */
export const WIDGET_REF_SOURCES: Readonly<Record<string, readonly string[]>> = data.widgetRefSources;
/** 톤 위젯이 보여 주는 제안(톤 어휘는 열린 문자열이라 직접 입력도 된다). 라벨은 `messages.widgets.tones[labelKey]` */
export const TONE_CHOICES: readonly { tone: string; labelKey: string }[] = data.toneChoices;
