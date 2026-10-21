import { useEffect, useMemo, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Run, RunSnapshot } from "@agent-console/contracts";
import { useApi } from "../../app/ApiContext";
import { useApiQuery } from "../../app/queries";
import { activeDescendants, ancestorChain, directChildren, splitSubscriptions } from "./runTree";
import { isActiveRun } from "./runsLib";

/** 활성 자식 Run을 동시에 구독하는 상한(초과분은 폴링, screen-delegation.md 3.1). */
export const CHILD_SUBSCRIBE_LIMIT = 5;
/** 자식 이벤트가 오고 나서 부모 화면을 다시 읽기까지의 디바운스(ms). */
export const CHILD_REFRESH_DEBOUNCE_MS = 500;
/** 활성 후손이 있을 때 후손 목록을 다시 읽는 간격(ms). 구독 상한을 넘은 자식은 이 폴링으로 따라간다. */
export const CHILD_POLL_MS = 5000;

export interface RunTree {
  /** 맨 위 Run id(이 Run이 루트면 자기 자신) */
  rootId: string;
  isChild: boolean;
  /** 루트부터 이 Run까지(이 Run 포함). 체인을 아직 못 읽었으면 이 Run만 */
  chain: readonly Run[];
  /** 직접 자식(만든 순) */
  children: readonly Run[];
  /** 모든 후손(손자 포함) */
  descendants: readonly Run[];
  /** 활성 후손(자식·손자…) */
  active: readonly Run[];
  /** 구독 중인 활성 Run id / 폴링으로 맡긴 활성 Run id */
  subscribed: readonly string[];
  polled: readonly string[];
  loading: boolean;
}

const treeKey = (rootId: string) => ["run", rootId, "tree"] as const;

/**
 * 자식 Run(중첩 팀) 트리를 읽는다. 이 Run이 자식이거나 자식을 가졌을 때만 후손 목록(`GET /runs?root=`)을 부르고,
 * 활성 자식은 `run:<child>`를 구독(상한 5)하며 이벤트가 오면 `onActivity`를 500ms 디바운스로 부른다. 화면을 떠나면 모두 해제한다.
 * 부모 trace·상호작용 갱신은 호출 쪽이 `onActivity`로 연결한다.
 */
export function useRunTree(run: Run | undefined, snapshotChildren: readonly Run[] | null | undefined, onActivity: () => void): RunTree {
  const { ws } = useApi();
  const qc = useQueryClient();
  const rootId = run?.root_run_id ?? run?.id ?? "";
  const isChild = run?.root_run_id != null && run.root_run_id !== run.id;
  const hasChildren = (snapshotChildren?.length ?? 0) > 0;
  const needTree = run !== undefined && (isChild || hasChildren);

  const root = useApiQuery<RunSnapshot>(["run", rootId], (r) => r.getRun(rootId), { enabled: needTree && isChild });
  const tree = useApiQuery<Run[]>(treeKey(rootId), (r) => r.listRuns({ root: rootId }), {
    enabled: needTree,
    refetchInterval: (q) => ((q.state.data ?? []).some((r) => isActiveRun(r.status)) || (run !== undefined && isActiveRun(run.status)) ? CHILD_POLL_MS : false),
  });
  const descendants = useMemo<readonly Run[]>(() => tree.data ?? [], [tree.data]);
  const chain = useMemo<readonly Run[]>(() => {
    if (run === undefined) return [];
    return ancestorChain([...(root.data ? [root.data.run] : []), ...descendants], run);
  }, [run, root.data, descendants]);
  const children = useMemo(() => (run === undefined ? [] : directChildren(run.id, snapshotChildren, descendants)), [run, snapshotChildren, descendants]);
  const active = useMemo(() => (run === undefined ? [] : activeDescendants(descendants, run.id)), [run, descendants]);
  const { subscribe, poll } = useMemo(() => splitSubscriptions(active.map((r) => r.id), CHILD_SUBSCRIBE_LIMIT), [active]);

  const activity = useRef(onActivity);
  useEffect(() => {
    activity.current = onActivity;
  });
  // 구독 상한을 넘은 활성 자식은 후손 목록 폴링으로 따라가므로, 목록이 새로 올 때마다 부모 화면도 갱신한다
  const polling = poll.length > 0;
  const updatedAt = tree.dataUpdatedAt;
  useEffect(() => {
    if (polling && updatedAt > 0) activity.current();
  }, [polling, updatedAt]);
  const key = subscribe.join(",");
  useEffect(() => {
    if (key === "") return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const ping = () => {
      if (timer !== undefined) return;
      timer = setTimeout(() => {
        timer = undefined;
        void qc.invalidateQueries({ queryKey: treeKey(rootId), exact: true });
        activity.current();
      }, CHILD_REFRESH_DEBOUNCE_MS);
    };
    const subs = key.split(",").map((id) => ws.subscribeRun(id, ping));
    return () => {
      if (timer !== undefined) clearTimeout(timer);
      subs.forEach((s) => s?.unsubscribe());
    };
  }, [ws, key, qc, rootId]);

  return { rootId, isChild, chain, children, descendants, active, subscribed: subscribe, polled: poll, loading: needTree && tree.isPending };
}
