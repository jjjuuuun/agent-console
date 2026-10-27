import { useCallback, useEffect, useRef, useState } from "react";
import type { ArchitectureProfileCheckRequest, ArchitectureProfileCheckResult, Issue } from "@agent-console/contracts";
import { parseProfileYaml } from "./yamlProfile";

export type CheckPhase = "idle" | "checking" | "done" | "failed";

export interface ProfileCheck {
  phase: CheckPhase;
  /** YAML 형식 오류(서버에 보내기 전) */
  parseError: { message: string; line: number | null } | null;
  /** 서버가 돌려준 문제 목록 */
  issues: readonly Issue[];
  checkedAt: number | null;
  /** 지금 검사를 다시 한다 */
  retry: () => void;
}

/**
 * 편집 중인 YAML을 멈춘 지 `delayMs` 뒤에 서버 검사(`check`)로 보낸다. 서버 호출은 주입받는다(`check`).
 * 오래된 응답은 버린다. 요청이 실패하면 `failed`이고 저장을 막을지는 호출자가 정한다.
 */
export function useProfileCheck(text: string, id: string | null, check: (body: ArchitectureProfileCheckRequest) => Promise<ArchitectureProfileCheckResult>, enabled: boolean, delayMs = 600, now: () => number = Date.now): ProfileCheck {
  const [state, setState] = useState<{ phase: CheckPhase; issues: readonly Issue[]; checkedAt: number | null; key: string }>({ phase: "idle", issues: [], checkedAt: null, key: "" });
  const [nonce, setNonce] = useState(0);
  const latest = useRef({ check, now });
  useEffect(() => {
    latest.current = { check, now };
  });
  const parsed = parseProfileYaml(text);
  const parseError = parsed.ok ? null : { message: parsed.message, line: parsed.line };
  const body = parsed.ok ? parsed.value : null;
  const bodyKey = body === null ? "" : JSON.stringify(body);
  const key = `${id ?? ""}\u0000${bodyKey}\u0000${nonce}`;
  const runnable = enabled && body !== null;
  useEffect(() => {
    if (!runnable || body === null) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      latest.current
        .check({ ...(id === null ? {} : { id }), profile: body as ArchitectureProfileCheckRequest["profile"] })
        .then((r) => {
          if (!cancelled) setState({ phase: "done", issues: r.issues ?? [], checkedAt: latest.current.now(), key });
        })
        .catch(() => {
          if (!cancelled) setState((s) => ({ ...s, phase: "failed", key }));
        });
    }, delayMs);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // body는 bodyKey로 비교한다(매 렌더 새 객체).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runnable, key, delayMs]);
  const retry = useCallback(() => setNonce((n) => n + 1), []);
  // 입력이 바뀐 직후(디바운스 대기)에도 지난 결과를 "검사 중"으로 본다.
  const stale = runnable && state.key !== key;
  return { phase: parseError !== null || !enabled ? "idle" : stale ? "checking" : state.phase, parseError, issues: parseError !== null ? [] : state.issues, checkedAt: state.checkedAt, retry };
}
