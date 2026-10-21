import type { ModuleInfo } from "@agent-console/contracts";

/**
 * 모듈 목록(`GET /modules`)으로 화면·연동 부분의 켜짐을 판정하는 순수 함수들(`docs/design/screen-modules.md` 1.3).
 * 사이드바·빠른 이동·단축키·안내 화면·연동 부분이 모두 이 파일의 판정 하나를 쓴다. 모듈 id·역할 이름은 여기에 없다.
 */

/** 계약이 고정한 상태 값(열린 문자열이라 다른 값도 올 수 있다). */
export const MODULE_STATUS = {
  active: "active",
  disabled: "disabled",
  unsatisfied: "unsatisfied",
  failed: "failed",
  conflict: "conflict",
} as const;

/** 미충족 대표 상태: 모듈 상태 5종 + 목록에 없음. 앞일수록 심각하다(안내 화면 제목을 고른다). */
export type Severity = "missing" | "failed" | "conflict" | "unsatisfied" | "disabled";
const SEVERITY_ORDER: readonly Severity[] = ["missing", "failed", "conflict", "unsatisfied", "disabled"];

/** `requires` 항목 하나(모듈 id 또는 역할)가 가리키는 모듈들. */
export function modulesFor(item: string, modules: readonly ModuleInfo[]): ModuleInfo[] {
  return modules.filter((m) => m.id === item || (m.web_roles ?? []).includes(item));
}

/** 항목 하나가 만족하는가: 일치하는 모듈 중 `active`가 하나라도 있다. */
export function itemSatisfied(item: string, modules: readonly ModuleInfo[]): boolean {
  return modulesFor(item, modules).some((m) => m.status === MODULE_STATUS.active);
}

/** 만족하지 못한 항목 하나. */
export interface UnmetItem {
  /** 라우트·부분의 `requires` 항목 그대로 */
  require: string;
  /** 모듈 id와 일치하면 `module`, 역할로만 일치하거나 아무도 없으면 `role` */
  by: "module" | "role";
  /** 일치한 모듈 전부(없으면 빈 배열 = 목록에 없음) */
  matches: ModuleInfo[];
  severity: Severity;
}

export interface RequiresResult {
  satisfied: boolean;
  unmet: UnmetItem[];
}

function severityOf(status: string): Severity {
  // 모르는 상태는 "연결 부족"처럼 다룬다(켜지지 않은 이유를 모르므로 설치자가 확인해야 한다)
  return (SEVERITY_ORDER as readonly string[]).includes(status) && status !== "missing" ? (status as Severity) : "unsatisfied";
}

function worst(severities: readonly Severity[]): Severity {
  return SEVERITY_ORDER.find((s) => severities.includes(s)) ?? "disabled";
}

/**
 * `requires`(모든 항목 AND)를 모듈 목록으로 판정한다.
 * 항목마다 대표 심각도는 일치한 모듈 중 가장 심각한 상태다(없으면 `missing`).
 */
export function resolveRequires(requires: readonly string[], modules: readonly ModuleInfo[]): RequiresResult {
  const unmet: UnmetItem[] = [];
  for (const item of requires) {
    const matches = modulesFor(item, modules);
    if (matches.some((m) => m.status === MODULE_STATUS.active)) continue;
    unmet.push({
      require: item,
      by: matches.some((m) => m.id === item) ? "module" : "role",
      matches,
      severity: matches.length === 0 ? "missing" : worst(matches.map((m) => severityOf(m.status))),
    });
  }
  return { satisfied: unmet.length === 0, unmet };
}

/** 미충족 항목들의 대표 심각도(없으면 undefined). */
export function worstSeverity(unmet: readonly UnmetItem[]): Severity | undefined {
  return unmet.length === 0 ? undefined : worst(unmet.map((u) => u.severity));
}

/** 켜져 있지 않고 사용자가 의도해서 끈 것도 아닌 상태("문제"). */
export function isProblemStatus(status: string): boolean {
  return status !== MODULE_STATUS.active && status !== MODULE_STATUS.disabled;
}

export function problemModules(modules: readonly ModuleInfo[]): ModuleInfo[] {
  return modules.filter((m) => isProblemStatus(m.status));
}

/** 구성이 바뀌었는지 비교하는 서명(`id:status`를 정렬해 합친다). */
export function modulesSignature(modules: readonly ModuleInfo[]): string {
  return modules
    .map((m) => `${m.id}:${m.status}`)
    .sort()
    .join("|");
}

/** 모듈 목록에 있는 모든 id와 역할(개발 중 `requires` 오타 점검용). */
export function knownNames(modules: readonly ModuleInfo[]): Set<string> {
  const out = new Set<string>();
  for (const m of modules) {
    out.add(m.id);
    for (const r of m.web_roles ?? []) out.add(r);
  }
  return out;
}

/** 어떤 모듈의 `provides`·`web_roles`·`id` 중 부분 일치가 있는가(설정 화면 검색). */
export function moduleMatchesText(m: ModuleInfo, text: string): boolean {
  const q = text.trim().toLowerCase();
  if (q === "") return true;
  return [m.id, ...(m.web_roles ?? []), ...(m.provides ?? [])].some((s) => s.toLowerCase().includes(q));
}

/** 모듈 하나가 켜 주는(= `requires`에 쓰이면 만족시켜 주는) 이름들: id와 역할. */
export function namesOf(m: ModuleInfo): string[] {
  return [m.id, ...(m.web_roles ?? [])];
}

/** `requires` 배열 중 하나라도 이 모듈이 만족시켜 주는 항목이 있는가("영향받는 화면·부분" 계산). */
export function moduleAffects(m: ModuleInfo, requires: readonly string[]): boolean {
  const names = namesOf(m);
  return requires.some((r) => names.includes(r));
}
