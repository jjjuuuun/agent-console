import { queryKeys, useApiQuery } from "../../app/queries";
import type { RestClient } from "@agent-console/api-client";

const load = (rest: RestClient) => rest.listObserveEventPrefixes();
const NONE: readonly string[] = [];
const STALE_MS = 60_000;

export interface ObservePrefixes {
  /** 관측 탭이 모을 이벤트 type 접두어(서버 `GET /observe-event-prefixes`). 읽는 동안·실패하면 빈 목록 */
  prefixes: readonly string[];
  /** 관측 탭을 보일지. 서버가 빈 목록을 주거나 경로가 없으면(실패) false, 읽는 중에는 true(탭이 깜빡이지 않게) */
  enabled: boolean;
}

/** 관측 탭 이벤트 접두어를 서버에서 읽는다(코드에 목록을 두지 않는다, 5.5R.18). */
export function useObservePrefixes(): ObservePrefixes {
  const query = useApiQuery(queryKeys.descriptors("observe-event-prefixes"), load, { staleTime: STALE_MS });
  const prefixes = query.data ?? NONE;
  const settled = query.data !== undefined;
  return { prefixes, enabled: query.isError ? false : !settled || prefixes.length > 0 };
}
