import { createContext, useContext, useMemo, type ReactNode } from "react";

/** 설정 값 기준 JSON Pointer로 매단 서버 이슈 한 건(`/conditions/all/1/value`). */
export interface ConfigIssue {
  path: string;
  message: string;
  severity?: "error" | "warning";
}

const Ctx = createContext<readonly ConfigIssue[]>([]);

/** 설정 폼 아래 위젯(필드)이 자기 위치의 서버 이슈를 읽도록 공급한다. 폼 엔진은 중첩 오류를 사용자 위젯에 넘기지 않아서 따로 둔다. */
export function ConfigIssuesProvider({ issues, children }: { issues: readonly ConfigIssue[]; children: ReactNode }) {
  const value = useMemo(() => issues, [issues]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** `pointer` 아래의 이슈를 그 위치 기준 상대 경로로. */
export function useConfigIssuesUnder(pointer: string | undefined): ConfigIssue[] {
  const all = useContext(Ctx);
  return useMemo(() => {
    if (pointer === undefined) return [];
    return all.filter((i) => i.path === pointer || i.path.startsWith(`${pointer}/`)).map((i) => ({ ...i, path: i.path.slice(pointer.length) }));
  }, [all, pointer]);
}

/**
 * 서버 이슈 경로를 연결/노드 `config` 기준으로 맞춘다. `/edges/3/config/conditions/all/1/value`처럼 앞에 그래프 위치가 붙어 있으면 `/config` 뒤만 쓴다.
 * 이미 config 기준이면 그대로.
 */
export function configRelativePath(path: string | null | undefined): string | undefined {
  if (path === null || path === undefined || path === "") return undefined;
  const m = /^\/(?:edges|nodes)\/[^/]+\/config(\/.*)?$/.exec(path);
  if (m) return m[1] ?? "";
  return path;
}
