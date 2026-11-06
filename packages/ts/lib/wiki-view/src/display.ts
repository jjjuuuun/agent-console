/**
 * 표시 데이터(`wikiDisplay` 자리)와 열린 문자열 → 칩 값 순수 함수.
 * op·쓴 주체 종류·심각도·점검 코드·링크 상태는 서버가 늘릴 수 있는 열린 문자열이다. 이 파일에는 그 값의 목록이 없다.
 * 표(`WikiDisplay`)는 호출자(앱 데이터)가 주고, 표에 없는 값은 원문 + 중립 톤으로 떨어진다(R0.1).
 */
import type { WikiAuthor } from "@agent-console/contracts/wiki";
import { toneAttr } from "@agent-console/markdown-doc";

/** 값 하나의 표시. 전부 선택이다. */
export interface DisplayEntry {
  label?: string;
  /** 서버 톤 어휘(열린 문자열). 모르면 중립. */
  tone?: string;
  /** 아이콘 이름(CSS가 `data-icon`으로 고른다). */
  icon?: string;
  /** 도움말 한 줄(툴팁). */
  hint?: string;
}

/** 열린 문자열 종류별 표시 표. 키는 서버 값 원문이다. */
export interface WikiDisplay {
  /** 기록 동작(`WikiPageVersion.op`·`WikiChange.op`) */
  ops?: Readonly<Record<string, DisplayEntry>>;
  /** 쓴 주체 종류(`WikiAuthor.kind`) */
  authorKinds?: Readonly<Record<string, DisplayEntry>>;
  /** 링크 상태(`WikiLink.status`) */
  linkStatuses?: Readonly<Record<string, DisplayEntry>>;
  /** 이슈 심각도(`Issue.severity`) → 톤 */
  severities?: Readonly<Record<string, DisplayEntry>>;
  /** 점검 코드(`Issue.code`) */
  codes?: Readonly<Record<string, DisplayEntry>>;
  /** 규칙 동작(`WikiRuleResult.action`·쓰기 규칙 `action`) */
  actions?: Readonly<Record<string, DisplayEntry>>;
  /** 규칙 항목 종류(`WikiRuleEntry.kind`) */
  entryKinds?: Readonly<Record<string, DisplayEntry>>;
  /** 문법 값 출처(`EffectiveWikiSyntax.sources`의 값) */
  sources?: Readonly<Record<string, DisplayEntry>>;
}

/** 그릴 값(항상 채워짐). */
export interface ResolvedDisplay {
  id: string;
  label: string;
  tone: string;
  icon: string | undefined;
  hint: string | undefined;
  /** 표에 있던 값인지(없으면 원문 + 중립으로 떨어진 것) */
  known: boolean;
}

/** 표에서 `id`를 찾아 그릴 값으로 만든다. 없거나 `label`이 비면 원문. */
export function resolveDisplay(table: Readonly<Record<string, DisplayEntry>> | undefined, id: string): ResolvedDisplay {
  const e = table && Object.prototype.hasOwnProperty.call(table, id) ? table[id] : undefined;
  return {
    id,
    label: e?.label && e.label !== "" ? e.label : id,
    tone: toneAttr(e?.tone),
    icon: e?.icon,
    hint: e?.hint,
    known: e !== undefined,
  };
}

/**
 * 쓴 주체 이름 = `label ?? agent_id ?? 종류 표시`. 빈 문자열은 없는 것으로 본다.
 * 종류 표시가 표에 없으면 종류 원문.
 */
export function authorLabel(author: WikiAuthor, display?: WikiDisplay): string {
  if (author.label && author.label !== "") return author.label;
  if (author.agent_id && author.agent_id !== "") return author.agent_id;
  return resolveDisplay(display?.authorKinds, author.kind).label;
}

/** 쓴 주체 툴팁에 쓸 조각들(값이 있는 것만, 순서 고정). 문구 틀은 호출자 messages가 정한다. */
export function authorFacts(author: WikiAuthor): { agentId?: string; nodePath?: string; runId?: string } {
  const out: { agentId?: string; nodePath?: string; runId?: string } = {};
  if (author.agent_id) out.agentId = author.agent_id;
  if (author.node_path && author.node_path.length > 0) out.nodePath = author.node_path.join(" › ");
  if (author.run_id) out.runId = author.run_id;
  return out;
}

/** 이슈 심각도 순서(앞이 심각). 모르는 값은 뒤. 순서는 호출자가 준다(예: `["error","warning","info"]`). */
export function severityRank(severity: string, order: readonly string[]): number {
  const i = order.indexOf(severity);
  return i < 0 ? order.length : i;
}
