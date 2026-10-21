/** 중첩 팀 [열기]로 들어온 편집기가 받는 라우터 상태(screen-delegation.md 2.7.4). 주소 직접 입력·새로고침이면 없다. */
export interface OpenedFrom {
  /** 부모 정의 종류(저장소 kind) */
  definitionKind: string;
  id: string;
  title: string;
  /** 그 위 단계(가까운 순서의 반대, 오래된 것부터). 깊이 제한은 없고 브레드크럼이 최근 몇 단계만 보인다 */
  trail?: { id: string; title: string }[];
}

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

/** 라우터 `location.state`에서 `openedFrom`을 읽는다. 모양이 맞지 않으면 undefined. */
export function readOpenedFrom(state: unknown): OpenedFrom | undefined {
  if (!isObj(state) || !isObj(state["openedFrom"])) return undefined;
  const o = state["openedFrom"];
  if (typeof o["definitionKind"] !== "string" || typeof o["id"] !== "string" || typeof o["title"] !== "string") return undefined;
  const trail = Array.isArray(o["trail"]) ? o["trail"].filter((t): t is { id: string; title: string } => isObj(t) && typeof t["id"] === "string" && typeof t["title"] === "string") : [];
  return { definitionKind: o["definitionKind"], id: o["id"], title: o["title"], ...(trail.length > 0 ? { trail } : {}) };
}

/** 자식을 열 때 넘길 상태: 지금 화면이 부모가 되고, 지금 화면의 `openedFrom`은 `trail`로 이어진다. */
export function openedFromState(current: { definitionKind: string; id: string; title: string }, previous: OpenedFrom | undefined): { openedFrom: OpenedFrom } {
  const trail = [...(previous?.trail ?? []), ...(previous === undefined ? [] : [{ id: previous.id, title: previous.title }])];
  return { openedFrom: { ...current, ...(trail.length > 0 ? { trail } : {}) } };
}

/** 부모로 돌아갈 때 넘길 상태: 부모 자신의 `openedFrom`은 `trail`의 마지막 항목이다(없으면 상태 없음). */
export function parentState(from: OpenedFrom): { openedFrom: OpenedFrom } | undefined {
  const trail = from.trail ?? [];
  const up = trail[trail.length - 1];
  if (up === undefined) return undefined;
  const rest = trail.slice(0, -1);
  return { openedFrom: { definitionKind: from.definitionKind, id: up.id, title: up.title, ...(rest.length > 0 ? { trail: rest } : {}) } };
}

export interface Crumb {
  label: string;
  href?: string;
  /** 부모 단계 항목이면 그 정의 id */
  id?: string;
  /** 그 부모 화면으로 돌아갈 때 넘길 라우터 상태(그 화면 자신의 `openedFrom`) */
  state?: { openedFrom: OpenedFrom };
}

/**
 * 헤더 브레드크럼: `{루트} / … / 부모들 / 현재`. 부모 단계는 최근 `max`개만 보이고 앞쪽은 `…`(링크 없음, 툴팁용 이름은 `hidden`)로 접는다.
 * `hrefOf(id)`는 정의 편집 화면 경로(없으면 링크 없음). 부모 단계마다 그 화면이 받을 `openedFrom` 상태를 함께 준다.
 */
export function buildBreadcrumb(opts: { root: Crumb; from: OpenedFrom | undefined; current: string; hrefOf(id: string): string | undefined; max?: number }): { crumbs: Crumb[]; hidden: string[] } {
  const chain = opts.from === undefined ? [] : [...(opts.from.trail ?? []), { id: opts.from.id, title: opts.from.title }];
  const max = opts.max ?? 3;
  const firstShown = Math.max(0, chain.length - max);
  const hidden = chain.slice(0, firstShown).map((c) => c.title);
  const crumbs: Crumb[] = [opts.root];
  if (hidden.length > 0) crumbs.push({ label: "…" });
  chain.forEach((c, k) => {
    if (k < firstShown) return;
    const href = opts.hrefOf(c.id);
    const above = chain[k - 1];
    const state = above === undefined || opts.from === undefined ? undefined : { openedFrom: { definitionKind: opts.from.definitionKind, id: above.id, title: above.title, ...(k - 1 > 0 ? { trail: chain.slice(0, k - 1) } : {}) } };
    crumbs.push({ label: c.title, id: c.id, ...(href === undefined ? {} : { href }), ...(state === undefined ? {} : { state }) });
  });
  crumbs.push({ label: opts.current });
  return { crumbs, hidden };
}
