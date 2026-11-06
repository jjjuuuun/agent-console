/**
 * 위키 화면의 데이터 표(`docs/design/screen-wiki.md`). 수치·저장소 키·주소 인자 이름이 전부 여기(와 `wikiData.json`) 있고 화면 코드는 이 표만 읽는다.
 * 위키 이름·페이지 경로·링크 패턴·머리말 키·규칙 id·쓰기 규칙 동작 이름은 이 파일에도 없다(서버 데이터).
 * 기록 동작·쓴 주체 종류·링크 상태·점검 코드·가져오기 상태는 계약이 이름 붙인 문서 상수에 문구·톤을 붙인 표(`wikiDisplay.json`)로만 안다.
 */
import type { DisplayEntry, WikiDisplay } from "@agent-console/wiki-view";
import data from "./wikiData.json";
import display from "./wikiDisplay.json";
import { wikiMessages } from "./messages";

/** 이 화면이 맡는 역할(라우트 `serves`·`requires`와 같은 값). 모듈 id가 아니다. */
export const WIKI_ROLE = "wiki";
/** 공용 구성 › 위키 규칙 화면의 역할(라우트 `serves`). 서버 모듈 역할과 같은 이름이다. 화면이 없으면 규칙 열기 링크·가져오기가 빠진다. */
export const WIKI_RULES_ROLE = "wiki:rules";
/** 이 화면이 있어야 켜지는 다른 화면의 역할(실행 기록 링크). 화면이 없으면 실행 링크 없이 글자만 보인다. */
export const RUNS_ROLE = "runs";

/** 주소 인자 이름(`wikiData.json`). 선택·모드는 URL이 진실이다. */
export const WIKI_PARAMS: Readonly<Record<keyof typeof data.params, string>> = data.params;

/** 탭 목록(데이터). 탭 본문은 `wikiTabs`의 등록 표가 그린다 — 본문이 등록되지 않은 탭은 줄에 나오지 않는다(그래프·점검·규칙은 7R.20이 등록). */
export const WIKI_TAB_DEFS: readonly { id: string; labelKey: string }[] = data.tabs;
export const DEFAULT_TAB: string = data.defaultTab;
/** 오른쪽 패널 세그먼트(데이터). 기록은 기록 저장소가 없어도 보이고 본문에서 안내한다. */
export const SIDE_TAB_DEFS: readonly { id: string; labelKey: string }[] = data.sideTabs;

export type PageViewMode = "view" | "edit" | "split";
export const VIEW_MODES: readonly PageViewMode[] = data.viewModes as PageViewMode[];

/** 화면 상태를 저장하는 localStorage 키(서버 설정이 아니다). */
export const WIKI_STORAGE = {
  tree: (wikiId: string) => `${data.storage.tree}${wikiId}`,
  treeTitleMode: data.storage.treeTitleMode,
  pageView: data.storage.pageView,
  lastTemplate: (wikiId: string) => `${data.storage.lastTemplate}${wikiId}`,
  lastPage: (wikiId: string) => `${data.storage.lastPage}${wikiId}`,
  secretDismissed: (wikiId: string, path: string) => `${data.storage.secretDismissed}${wikiId}/${path}`,
} as const;

export const WIKI_LIMITS = data.limits;

/** 가져오기 겹침 처리 목록(서버 `policy` 값 + 문구 키). */
export const IMPORT_POLICIES: readonly { id: string; labelKey: string; destructive?: boolean }[] = data.importPolicies;

/** 읽을 수 없는 페이지 경로의 마지막 조각(서버 주소 규칙 `PAGE_ROUTE_WORDS`). 이 이름으로 끝나는 새 경로는 만들기 전에 안내한다. */
export const ROUTE_WORDS: readonly string[] = Object.values(data.routeWords);

interface TableEntry {
  tone?: string;
  icon?: string;
  labelKey?: string;
  hintKey?: string;
}

function table(entries: Readonly<Record<string, TableEntry>>, labels: Readonly<Record<string, string>>, hints?: Readonly<Record<string, string>>): Readonly<Record<string, DisplayEntry>> {
  const out: Record<string, DisplayEntry> = {};
  for (const [id, e] of Object.entries(entries)) {
    const entry: DisplayEntry = {};
    const label = e.labelKey === undefined ? undefined : labels[e.labelKey];
    if (label !== undefined) entry.label = label;
    if (e.tone !== undefined) entry.tone = e.tone;
    if (e.icon !== undefined) entry.icon = e.icon;
    const hint = e.hintKey === undefined || hints === undefined ? undefined : hints[e.hintKey];
    if (hint !== undefined) entry.hint = hint;
    out[id] = entry;
  }
  return out;
}

/** 표현 컴포넌트에 넘기는 표시 표(문서 상수 → 문구·톤·아이콘). 모르는 값은 표에 없으므로 원문 + 중립 톤으로 보인다. */
export function buildWikiDisplay(): WikiDisplay {
  const d = wikiMessages.display;
  return {
    ops: table(display.ops, d.ops),
    authorKinds: table(display.authorKinds, d.authors),
    linkStatuses: table(display.linkStatuses, d.links),
    severities: table(display.severities, d.severities),
    codes: table(display.codes, d.codes, d.codeHints),
  };
}

/** 가져오기 결과 상태(열린 문자열) → 톤·문구. 모르는 값은 중립 + 원문. */
export function importStatusDisplay(status: string): { tone: string; label: string } {
  const e = (display.importStatuses as Record<string, TableEntry | undefined>)[status];
  const label = e?.labelKey === undefined ? undefined : wikiMessages.display.importStatuses[e.labelKey];
  return { tone: e?.tone ?? "neutral", label: label ?? status };
}

/** 이슈 심각도(열린 문자열) → 톤. 모르는 값은 중립. */
export function severityTone(severity: string): string {
  return (display.severities as Record<string, TableEntry | undefined>)[severity]?.tone ?? "neutral";
}

/** 그래프 탭 깊이 선택(데이터): 숫자 단계, 기본 단계, "전체"를 뜻하는 주소 값. 서버는 `depth` 숫자 하나를 받고 없으면 전체다. */
export const WIKI_GRAPH = data.graph as { depths: readonly number[]; defaultDepth: number; all: string };
export const GRAPH_LIST_ONLY_KEY: string = data.storage.graphListOnly;

/** 공용 구성 › 위키 규칙 화면의 데이터(주소 인자·탭·REST 컬렉션·고급이어도 섹션으로 보일 속성). */
export const WIKI_RULES_SCREEN = data.rulesScreen as {
  params: { rule: string; tab: string; section: string; file: string };
  tabs: readonly { id: "rules" | "files" | "versions"; labelKey: string }[];
  collection: string;
  includeAdvanced: readonly string[];
  nameMax: number;
  /** 본문 파일을 가리키는 규칙 문서 속성(데이터): 한 파일 참조 속성들, 파일 참조 목록 속성들, 참조 안의 파일 경로 키, 목록 항목의 표시 이름 후보 키 */
  fileFields: { single: readonly string[]; list: readonly string[]; fileKey: string; labelKeys: readonly string[] };
};
export type WikiRulesTabId = (typeof WIKI_RULES_SCREEN.tabs)[number]["id"];

/** 심각도 순서(앞이 심각): 표시 표(`wikiDisplay.json`)의 심각도 키 순서. 모르는 값은 표가 뒤로 보낸다. */
export const SEVERITY_ORDER: readonly string[] = Object.keys(display.severities);
