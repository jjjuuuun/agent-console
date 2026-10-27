import type { TokenRollupRow, UsageSetupSnippet, UsageSourceInfo, UsageWindowSnapshot } from "@agent-console/contracts";

/** 사용량 화면의 순수 로직(UI·네트워크 없음). 시각은 모두 epoch 초. 창 이름·출처 id를 코드에 두지 않는다. */

/** 이 스냅샷이 보여 줄 값(사용률·상태·토큰)이 하나라도 있는가. */
export function hasValue(s: UsageWindowSnapshot): boolean {
  return s.used_ratio != null || (s.status != null && s.status !== "") || s.used_tokens != null;
}

export type PrimaryRule = "order" | "recent-official" | "recent";

export interface WindowGroup {
  window: string;
  /** 카드 대표 스냅샷(값이 하나도 없는 창이면 가장 최근 것) */
  primary: UsageWindowSnapshot;
  rule: PrimaryRule;
  /** 설정 순서를 쓰려 했으나 값이 있는 출처가 없어 기본 규칙으로 대신했는가 */
  fellBack: boolean;
  /** 대표를 뺀 나머지(출처별 최신 1건씩, 최신 순) */
  others: UsageWindowSnapshot[];
}

/** 창 id별로 출처당 가장 최근 스냅샷만 남긴다. 창 순서는 처음 나온 순서(출처가 준 순서). */
export function latestPerSource(snapshots: readonly UsageWindowSnapshot[]): Map<string, UsageWindowSnapshot[]> {
  const byWindow = new Map<string, Map<string, UsageWindowSnapshot>>();
  for (const s of snapshots) {
    const sources = byWindow.get(s.window) ?? new Map<string, UsageWindowSnapshot>();
    const prev = sources.get(s.source);
    if (prev === undefined || s.observed_at >= prev.observed_at) sources.set(s.source, s);
    byWindow.set(s.window, sources);
  }
  const out = new Map<string, UsageWindowSnapshot[]>();
  for (const [window, sources] of byWindow) out.set(window, [...sources.values()]);
  return out;
}

/**
 * 창 카드 묶음을 만든다. 대표값 규칙(design §R4.3):
 * `primaryOrder`가 비어 있지 않으면 그 순서에서 값이 있는 첫 출처, 아니면 가장 최근의 공식 값, 공식이 없으면 가장 최근 값.
 * 정렬: 출처가 준 순서(처음 나온 순서).
 * @param isOfficial 출처 id → 공식 등급인가(앱이 출처 디스크립터에서 계산해 넘긴다)
 */
export function buildWindowGroups(
  snapshots: readonly UsageWindowSnapshot[],
  primaryOrder: readonly string[],
  isOfficial: (sourceId: string) => boolean,
): WindowGroup[] {
  const grouped = latestPerSource(snapshots);
  const groups: WindowGroup[] = [];
  for (const [window, list] of grouped) {
    const byRecent = [...list].sort((a, b) => b.observed_at - a.observed_at);
    const withValue = byRecent.filter(hasValue);
    let primary: UsageWindowSnapshot | undefined;
    let rule: PrimaryRule = "recent-official";
    let fellBack = false;
    if (primaryOrder.length > 0) {
      for (const id of primaryOrder) {
        const hit = withValue.find((s) => s.source === id);
        if (hit !== undefined) {
          primary = hit;
          rule = "order";
          break;
        }
      }
      fellBack = primary === undefined;
    }
    if (primary === undefined) {
      const official = withValue.find((s) => isOfficial(s.source));
      if (official !== undefined) primary = official;
      else {
        primary = withValue[0] ?? byRecent[0];
        rule = "recent";
      }
    }
    const chosen = primary as UsageWindowSnapshot;
    groups.push({ window, primary: chosen, rule, fellBack, others: byRecent.filter((s) => s !== chosen) });
  }
  return groups; // 출처가 준 순서(처음 나온 순서)를 유지한다
}

/** 설정이 숫자로 정해져 있고 관측이 그보다 오래됐으면 true. null/undefined면 절대 true가 아니다. */
export function isStaleObservation(observedAt: number, nowSec: number, staleAfterSeconds: number | null | undefined): boolean {
  return typeof staleAfterSeconds === "number" && Number.isFinite(staleAfterSeconds) && nowSec - observedAt > staleAfterSeconds;
}

export type ResetState = "unknown" | "future" | "passed";

/** `resets_at`이 없는지/미래인지/지났는지(설정과 무관한 사실). */
export function resetState(resetsAt: number | null | undefined, nowSec: number): ResetState {
  if (resetsAt === null || resetsAt === undefined || !Number.isFinite(resetsAt)) return "unknown";
  return resetsAt > nowSec ? "future" : "passed";
}

/** 남은 초 → "2시간 14분" / "3일 4시간" / "5분" / "1분 미만". */
export function formatRemaining(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  if (days > 0) return hours > 0 ? `${days}일 ${hours}시간` : `${days}일`;
  if (hours > 0) return minutes > 0 ? `${hours}시간 ${minutes}분` : `${hours}시간`;
  if (minutes > 0) return `${minutes}분`;
  return "1분 미만";
}

/** 사용률(0~1, 넘을 수 있음) → "63%". 서버 값만 쓴다. */
export function formatRatio(ratio: number): string {
  return `${Math.round(ratio * 100)}%`;
}

// ---------------------------------------------------------------- 사용량 표시기(순수 함수)

/** 사용률(0~1, 넘을 수 있음) → 사용 정수 퍼센트. `formatRatio`와 같은 반올림이라 사용 + 남음 = 100이 된다. */
export function usedPercent(ratio: number): number {
  return Math.round(ratio * 100);
}

/** 사용률 → 남은 정수 퍼센트(한도를 넘었으면 0). */
export function remainingPercent(ratio: number): number {
  return Math.max(0, 100 - usedPercent(ratio));
}

export interface ColorRuleLike {
  at: number;
  tone: string;
}

/** 사용률이 `at` 이상인 규칙 중 `at`이 가장 큰 것 하나. 규칙이 없거나 해당 없으면 undefined. */
export function pickColorRule<R extends ColorRuleLike>(rules: readonly R[] | null | undefined, usedRatio: number): R | undefined {
  let best: R | undefined;
  for (const r of rules ?? []) if (usedRatio >= r.at && (best === undefined || r.at > best.at)) best = r;
  return best;
}

export type IndicatorValueKind = "ratio" | "status" | "tokens" | "none";

export interface IndicatorItem {
  window: string;
  /** 표시 이름(`window_labels` → 출처가 준 창 이름 → 창 id 원문 순) */
  name: string;
  /** 좁은 자리용 이름(`window_labels` → 출처가 준 짧은 이름 → `name`). `name`과 같으면 생략 */
  short?: string;
  kind: IndicatorValueKind;
  /** 관측된 창인가(설정에 적었으나 관측이 없으면 false) */
  observed: boolean;
  source?: string;
  observedAt?: number;
  resetsAt?: number | null;
  status?: string;
  tokens?: number;
  /** kind="ratio"일 때: 사용·남은 정수 퍼센트와 원래 사용률 */
  used?: number;
  remaining?: number;
  ratio?: number;
  overLimit: boolean;
  reset: ResetState;
  stale: boolean;
  /** 적용된 색 규칙 */
  rule?: ColorRuleLike;
}

export interface BuildIndicatorArgs {
  groups: readonly WindowGroup[];
  /** 설정 `windows`. 비어 있으면 묶음 순서의 앞 `maxItems`개 */
  windows: readonly string[];
  maxItems: number;
  labels: Readonly<Record<string, string>>;
  /** 창 id → 출처 디스크립터가 준 이름(`window_labels`에 없을 때 쓴다) */
  windowInfo?: Readonly<Record<string, WindowNameInfo>>;
  /** 출처 id → 출처 제목(선택). 주면 폴백 이름이 "출처 제목 + 창 id"가 된다. 사이드바는 라벨이 좁아 주지 않는다 */
  sourceTitle?: (sourceId: string) => string | undefined;
  nowSec: number;
  staleAfterSeconds: number | null | undefined;
  colorRules: readonly ColorRuleLike[] | null | undefined;
}

/** 출처가 준 창 이름(디스크립터 `windows[]`). */
export interface WindowNameInfo {
  title: string;
  short?: string | null | undefined;
}

/** 출처 목록에서 창 id → 이름 표를 만든다(먼저 나온 출처가 이긴다). */
export function windowNameIndex(sources: readonly UsageSourceInfo[]): Record<string, WindowNameInfo> {
  const out: Record<string, WindowNameInfo> = {};
  for (const s of sources) {
    for (const w of s.descriptor.windows ?? []) {
      if (out[w.id] === undefined) out[w.id] = { title: w.title, short: w.short_title };
    }
  }
  return out;
}

/**
 * 창 표시 이름: 사용자 `window_labels` → 출처가 준 창 이름 → "출처 제목 + 창 id(`_`는 공백)" → 창 id 원문.
 * 원시 창 id를 그대로 내지 않기 위한 폴백이다(ux-overhaul §8.1).
 */
export function windowDisplayName(
  id: string,
  labels: Readonly<Record<string, string>>,
  info: WindowNameInfo | undefined,
  sourceTitle?: string,
): string {
  const label = labels[id];
  if (label) return label;
  if (info?.title) return info.title;
  const spaced = id.replace(/_/g, " ");
  return sourceTitle ? `${sourceTitle} ${spaced}` : spaced;
}

/** 연결 안내 조각을 제목별로 묶는다(탭 하나 = 제목 하나, 안의 항목 = 셸별). 처음 나온 순서를 지킨다. */
export function groupSetupSnippets(snippets: readonly UsageSetupSnippet[]): { title: string; items: UsageSetupSnippet[] }[] {
  const out: { title: string; items: UsageSetupSnippet[] }[] = [];
  for (const sn of snippets) {
    const hit = out.find((g) => g.title === sn.title);
    if (hit) hit.items.push(sn);
    else out.push({ title: sn.title, items: [sn] });
  }
  return out;
}

/**
 * 순위(작을수록 먼저): 0 = 값이 있고 대표가 사용자 순서·공식 규칙으로 정해진 창, 1 = 값은 있으나 공식 값이 없어 최근 값으로 대신한 창, 2 = 값 없음.
 * 사용량 화면 카드의 대표값 규칙(`buildWindowGroups`)을 그대로 따른다.
 */
function windowRank(g: WindowGroup): number {
  if (!hasValue(g.primary)) return 2;
  return g.rule === "recent" ? 1 : 0;
}

/**
 * `windows` 설정이 비었을 때 보일 창: 값 있는 창을 먼저(공식/지정 출처 > 그 밖의 값, 같은 순위는 묶음 순서) 고른 뒤 앞 `maxItems`개.
 * 값이 약하거나 없는 창이 앞자리를 차지해 공식 값이 있는 창을 밀어내지 않게 한다. 같은 창을 여러 출처가 주면 `groups`의 대표가 이미 하나로 정했다.
 */
function pickDefaultWindows(groups: readonly WindowGroup[], maxItems: number): string[] {
  const ranked = groups.map((g, i) => ({ g, i, r: windowRank(g) }));
  ranked.sort((x, y) => x.r - y.r || x.i - y.i);
  return ranked.slice(0, Math.max(0, maxItems)).map((x) => x.g.window);
}

/** 표시기가 그릴 항목 목록. 대표값 규칙은 `buildWindowGroups`의 결과를 그대로 쓴다(카드와 같은 숫자). */
export function buildIndicatorItems(a: BuildIndicatorArgs): IndicatorItem[] {
  const byWindow = new Map(a.groups.map((g) => [g.window, g]));
  const ids = a.windows.length > 0 ? [...a.windows] : pickDefaultWindows(a.groups, a.maxItems);
  return ids.map((id): IndicatorItem => {
    const info = a.windowInfo?.[id];
    const g = byWindow.get(id);
    const name = windowDisplayName(id, a.labels, info, g === undefined ? undefined : a.sourceTitle?.(g.primary.source));
    const shortName = a.labels[id] ?? (info?.short ? info.short : name);
    const short = shortName === name ? {} : { short: shortName };
    if (g === undefined) return { window: id, name, ...short, kind: "none", observed: false, overLimit: false, reset: "unknown", stale: false };
    const s = g.primary;
    const reset = resetState(s.resets_at, a.nowSec);
    const base = {
      window: id,
      name,
      ...short,
      observed: true,
      source: s.source,
      observedAt: s.observed_at,
      resetsAt: s.resets_at,
      reset,
      stale: isStaleObservation(s.observed_at, a.nowSec, a.staleAfterSeconds),
    };
    if (s.used_ratio != null) {
      const rule = pickColorRule(a.colorRules, s.used_ratio);
      return { ...base, kind: "ratio", ratio: s.used_ratio, used: usedPercent(s.used_ratio), remaining: remainingPercent(s.used_ratio), overLimit: s.used_ratio > 1, ...(rule ? { rule } : {}) };
    }
    if (s.status != null && s.status !== "") return { ...base, kind: "status", status: s.status, overLimit: false };
    if (s.used_tokens != null) return { ...base, kind: "tokens", tokens: s.used_tokens, overLimit: false };
    return { ...base, kind: "none", overLimit: false };
  });
}

/** 게이지 채움 비율(0~1): 값 방향이 `used`면 사용, 아니면 남은 양. 사용률이 없으면 undefined. */
export function indicatorFill(item: IndicatorItem, mode: string): number | undefined {
  if (item.kind !== "ratio" || item.used === undefined || item.remaining === undefined) return undefined;
  return (mode === "used" ? Math.min(100, item.used) : item.remaining) / 100;
}

// ---------------------------------------------------------------- 토큰 집계

export type RollupDimension = "agent_id" | "graph_id" | "model" | "day";

export interface RollupLine {
  key: string;
  /** 차원 값(없으면 null) */
  value: string | null;
  total: number | undefined;
  input: number | undefined;
  output: number | undefined;
  costUsd: number | undefined;
  /** 서버가 준 정밀도 메모(중복 제거) */
  precision: string[];
  /** 일부 행에 입력/출력 구분이 없었는가 */
  partialSplit: boolean;
}

function rowTotal(r: TokenRollupRow): number | undefined {
  const u = r.usage;
  if (typeof u.total_tokens === "number") return u.total_tokens;
  const parts = [u.input_tokens, u.output_tokens].filter((v): v is number => typeof v === "number");
  return parts.length === 0 ? undefined : parts.reduce((a, b) => a + b, 0);
}

function add(a: number | undefined, b: number | undefined): number | undefined {
  return b === undefined ? a : (a ?? 0) + b;
}

/** `YYYY-MM-DD` 기준으로 `days`일 안의 행만 남긴다(오늘 포함). `days`가 null이면 전부. */
export function filterRollupByDays(rows: readonly TokenRollupRow[], days: number | null, today: Date): TokenRollupRow[] {
  if (days === null) return [...rows];
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate() - (days - 1));
  const iso = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, "0")}-${String(start.getDate()).padStart(2, "0")}`;
  return rows.filter((r) => r.day == null || r.day >= iso);
}

/** 서버 집계 행(에이전트·팀 구성·모델·일 조합)을 한 차원으로 다시 합친다. 합계 내림차순(일 보기는 날짜 오름차순). */
export function aggregateRollup(rows: readonly TokenRollupRow[], by: RollupDimension): RollupLine[] {
  const map = new Map<string, RollupLine>();
  for (const r of rows) {
    const value = r[by] ?? null;
    const key = value ?? "\u0000";
    const line = map.get(key) ?? { key, value, total: undefined, input: undefined, output: undefined, costUsd: undefined, precision: [], partialSplit: false };
    line.total = add(line.total, rowTotal(r));
    const hasSplit = typeof r.usage.input_tokens === "number" || typeof r.usage.output_tokens === "number";
    if (hasSplit) {
      line.input = add(line.input, r.usage.input_tokens ?? undefined);
      line.output = add(line.output, r.usage.output_tokens ?? undefined);
    } else line.partialSplit = true;
    line.costUsd = add(line.costUsd, r.usage.cost_usd ?? undefined);
    if (r.precision && !line.precision.includes(r.precision)) line.precision.push(r.precision);
    map.set(key, line);
  }
  const lines = [...map.values()];
  if (by === "day") return lines.sort((a, b) => (a.value ?? "").localeCompare(b.value ?? ""));
  return lines.sort((a, b) => (b.total ?? -1) - (a.total ?? -1));
}

/** 막대 길이 비율(0~1). 최대값 기준 상대. */
export function barRatio(total: number | undefined, max: number): number {
  return total === undefined || max <= 0 ? 0 : Math.min(1, total / max);
}

/** 출처 id → 디스크립터. 목록에 없으면 undefined. */
export function sourceIndex(sources: readonly UsageSourceInfo[]): Map<string, UsageSourceInfo> {
  return new Map(sources.map((s) => [s.descriptor.id, s]));
}

/**
 * 수동 새로 고침을 지금 해도 되는가(연타 방지). 마지막 조회·새로 고침이 `gapMs` 안이면 false.
 * @param nowMs 지금(ms) @param lastMs 마지막 조회/새로 고침 시각(ms), 없으면 0 이하 @param gapMs 최소 간격(ms)
 */
export function canRefreshNow(nowMs: number, lastMs: number, gapMs: number): boolean {
  return lastMs <= 0 || nowMs - lastMs >= gapMs;
}

/** 마크다운 표식(백틱·강조·링크 문법)을 걷어 낸 한 줄 글. 한 줄 요약(말줄임) 표시용. */
export function plainText(md: string): string {
  return md
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[`*_#>]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}
