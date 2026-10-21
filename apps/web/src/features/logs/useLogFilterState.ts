import { useCallback, useMemo } from "react";
import { useLocation, useNavigate } from "react-router";
import { CURRENT_PROJECT_PARAM } from "../../app/projectScope";
import { buildScreenSearch, reservedParams, splitSearchParams, type FilterFieldSpec, type LogFilterValue } from "@agent-console/log-view";

/**
 * 로그 화면의 URL 상태: 서버 필터(`LogFilter` 이름 그대로)와 화면 전용 파라미터(`through`·`lane`·`view`·`range`·`tab`)를 나눠 읽고 쓴다.
 * 화면 전용 파라미터는 서버 요청에 싣지 않는다(`splitSearchParams`/`buildFilterQuery`). 쓰기는 `replace`라 뒤로 가기를 오염시키고,
 * 해시(`#e=<uid>` 선택)는 유지한다.
 */
export interface LogUrlState {
  filter: LogFilterValue;
  screen: Record<string, string[]>;
  /** 예약도 아니고 필드 정의에도 없는 이름("알 수 없는 필터" 경고) */
  unknown: string[];
  setFilter(next: LogFilterValue): void;
  /** 화면 전용 파라미터를 바꾼다(null/빈 배열 = 지움). */
  setScreen(patch: Readonly<Record<string, string | readonly string[] | null>>): void;
  /** 필터와 화면 전용 파라미터를 한 번에 바꾼다(두 번 이동하며 서로 덮어쓰는 일을 막는다). */
  update(filter: LogFilterValue, patch: Readonly<Record<string, string | readonly string[] | null>>): void;
}

/** 화면 전용 예약 이름 + 앱의 현재 프로젝트 쿼리(로그 필터로 해석하지 않고 그대로 보존). */
const RESERVED = [...reservedParams, CURRENT_PROJECT_PARAM];

export function useLogUrlState(fields: readonly Pick<FilterFieldSpec, "name">[]): LogUrlState {
  const location = useLocation();
  const navigate = useNavigate();
  const parsed = useMemo(() => splitSearchParams(location.search, { fields: fields as FilterFieldSpec[], reserved: RESERVED }), [location.search, fields]);
  const write = useCallback(
    (search: URLSearchParams) => {
      const s = search.toString();
      void navigate({ pathname: location.pathname, search: s === "" ? "" : `?${s}`, hash: location.hash }, { replace: true });
    },
    [navigate, location.pathname, location.hash],
  );
  const setFilter = useCallback((next: LogFilterValue) => write(buildScreenSearch(next, parsed.screen, { reserved: RESERVED })), [write, parsed.screen]);
  const update = useCallback(
    (filter: LogFilterValue, patch: Readonly<Record<string, string | readonly string[] | null>>) => {
      const screen: Record<string, string[]> = { ...parsed.screen };
      for (const [k, v] of Object.entries(patch)) {
        const list = v === null ? [] : typeof v === "string" ? [v] : [...v];
        if (list.length === 0) delete screen[k];
        else screen[k] = list;
      }
      write(buildScreenSearch(filter, screen, { reserved: RESERVED }));
    },
    [write, parsed.screen],
  );
  const setScreen = useCallback((patch: Readonly<Record<string, string | readonly string[] | null>>) => update(parsed.filter, patch), [update, parsed.filter]);
  return { filter: parsed.filter, screen: parsed.screen, unknown: parsed.unknown, setFilter, setScreen, update };
}

/** 해시 `#e=<uid>`(선택한 이벤트). 값을 바꾸면 `replace`로 쓰며 쿼리는 유지한다. */
export function useSelectedUid(): [string | null, (uid: string | null) => void] {
  const location = useLocation();
  const navigate = useNavigate();
  const uid = useMemo(() => {
    const m = /(?:^#|&)e=([^&]*)/.exec(location.hash);
    return m?.[1] ? decodeURIComponent(m[1]) : null;
  }, [location.hash]);
  const set = useCallback(
    (next: string | null) => {
      void navigate({ pathname: location.pathname, search: location.search, hash: next === null ? "" : `#e=${encodeURIComponent(next)}` }, { replace: true });
    },
    [navigate, location.pathname, location.search],
  );
  return [uid, set];
}
