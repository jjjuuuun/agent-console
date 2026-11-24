import { useMemo } from "react";
import { ERROR_CODES } from "@agent-console/contracts";
import { RUNS_BLOCK_PORTS } from "./runsBlockPorts";
import { queryKeys, useApiQuery } from "../../app/queries";

export interface ProjectRunsBlocked {
  blocked: boolean;
  /** 서버가 준 문구(막혔을 때만) */
  message: string | undefined;
}

interface WarningLike {
  code: string;
  message?: string | undefined;
  details?: Record<string, unknown> | null | undefined;
}

/** 경고 목록에서 실행 연동 꺼짐 경고를 찾는다(순수 함수). */
export function findRunsBlocked(warnings: readonly WarningLike[] | undefined): ProjectRunsBlocked {
  const hit = (warnings ?? []).find((w) => w.code === ERROR_CODES.FEATURE_UNAVAILABLE && RUNS_BLOCK_PORTS.has(String(w.details?.["port"] ?? "")));
  return hit === undefined ? { blocked: false, message: undefined } : { blocked: true, message: hit.message === "" ? undefined : hit.message };
}

/** 서버 정보(`/server-info`)의 경고에서 "프로젝트 실행이 막혔는가"를 읽는다. 질의가 아직 없거나 실패하면 막지 않는다. */
export function useProjectRunsBlocked(): ProjectRunsBlocked {
  const info = useApiQuery(queryKeys.descriptors("server-info"), (rest) => rest.getServerInfo(), { retry: false, meta: { silentBackgroundError: true } });
  const warnings = info.data?.warnings;
  return useMemo(() => findRunsBlocked(warnings), [warnings]);
}
