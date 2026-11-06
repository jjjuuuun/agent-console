/**
 * 규칙 폼 위젯이 읽는 서버·폼 데이터(고를 수 있는 값 목록, 입력 틀 변수). 위젯은 API를 모르고 이 문맥만 읽는다.
 * 목록은 위젯 이름(계약 `KNOWN_UI_WIDGETS`) 키로 들어온다 — 어떤 필드가 어떤 목록을 쓰는지는 코드가 아니라 스키마의 `x-ui.widget`이 정한다.
 */
import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { KNOWN_UI_WIDGETS } from "@agent-console/contracts/constants";
import type { SpecDefinition } from "@agent-console/contracts/sdd";
import { useApi } from "../../../app/ApiContext";
import { WIDGET_REF_SOURCES } from "../sddConfig";
import { useSddSpace } from "../useSddApi";

export interface RefOption {
  id: string;
  label?: string;
}

export interface SddWidgetEnv {
  /** 위젯 이름 → 고를 수 있는 값. null = 목록을 알 수 없음(연동 꺼짐·불러오기 실패) — 위젯은 직접 입력만 받는다 */
  refs: Readonly<Record<string, readonly RefOption[] | null>>;
  /** 실행 입력 틀에서 쓸 수 있는 변수 이름(서버 `…/variables`) */
  variables: readonly string[];
}

const EMPTY: SddWidgetEnv = { refs: {}, variables: [] };
const Ctx = createContext<SddWidgetEnv>(EMPTY);

export function SddWidgetEnvProvider({ env, children }: { env: SddWidgetEnv; children: ReactNode }) {
  return <Ctx.Provider value={env}>{children}</Ctx.Provider>;
}

export function useSddWidgetEnv(): SddWidgetEnv {
  return useContext(Ctx);
}

type Obj = Record<string, unknown>;
const idsOf = (list: readonly { id: string; label?: string | null; title?: string | null }[] | null | undefined): RefOption[] =>
  (list ?? []).map((x) => {
    const label = x.label ?? x.title;
    return label === undefined || label === null || label === "" || label === x.id ? { id: x.id } : { id: x.id, label };
  });

/**
 * 규칙 초안(`def`)에서 같은 폼이 정한 문서 상태·작업 상태·실행 프로필 id를, 서버에서 팀 구성 목록·입력 틀 변수를 읽어 위젯 환경을 만든다.
 * 팀 구성 목록은 `teamsOn`일 때만 부른다(꺼져 있거나 실패하면 null = 직접 입력).
 */
export function useSddWidgetData(specId: string, def: SpecDefinition, teamsOn: boolean): SddWidgetEnv {
  const space = useSddSpace();
  const { space: spaceRest } = useApi();
  const variables = useQuery({ queryKey: ["sdd", space.key, "spec", specId, "variables"] as const, queryFn: () => space.client.listSpecVariables(specId), retry: false, staleTime: 30_000 });
  const graphs = useQuery({
    queryKey: ["list", "graphs", "space", space.project] as const,
    queryFn: () => spaceRest(space.project).listGraphs(),
    enabled: teamsOn,
    retry: false,
    staleTime: 30_000,
  });
  // 같은 폼의 배열에서 고를 값을 얻는 위젯(위치는 sddData.json). 배열이 바뀔 때만 다시 계산한다.
  const sourceKeys = Object.keys(WIDGET_REF_SOURCES);
  const fromForm = JSON.stringify(sourceKeys.map((k) => (WIDGET_REF_SOURCES[k] ?? []).reduce<unknown>((o, seg) => (typeof o === "object" && o !== null ? (o as Obj)[seg] : undefined), def) ?? null));
  const graphList = graphs.data;
  const names = variables.data;
  return useMemo(() => {
    const lists = JSON.parse(fromForm) as ({ id: string }[] | null)[];
    const refs: Record<string, readonly RefOption[] | null> = {};
    sourceKeys.forEach((k, i) => {
      const name = (KNOWN_UI_WIDGETS as Record<string, string>)[k];
      if (name !== undefined) refs[name] = idsOf(lists[i]);
    });
    refs[KNOWN_UI_WIDGETS.GRAPH_REF] = graphList === undefined ? null : graphList.map((g) => ({ id: g.id, ...(g.name ? { label: g.name } : {}) }));
    return { refs, variables: (names ?? []).map((v) => v.name) };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fromForm, graphList, names]);
}
