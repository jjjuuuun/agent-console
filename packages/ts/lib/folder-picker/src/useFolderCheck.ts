import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { checkingState, deriveCheckState, errorState, IDLE_STATE, type FolderCheckState } from "./checkState";
import type { FolderCheckFn, FolderCheckOutcome } from "./types";

export interface UseFolderCheckOptions {
  check: FolderCheckFn;
  /** 경로 다시 지정 모드: 확인 요청에 실어 보낸다. */
  excludeProjectId?: string;
  /** 경로 다시 지정 모드의 이전 경로(`same_path` 판정). */
  currentFolder?: string | null;
  /** 입력 멈춘 뒤 기다리는 시간(ms). 기본 300. */
  debounceMs?: number;
}

export interface UseFolderCheck {
  state: FolderCheckState;
  /** 입력이 바뀌었을 때. 기본은 디바운스, `immediate`면 바로 확인. 빈 입력이면 idle. */
  request(path: string, opts?: { immediate?: boolean }): void;
  /** 대기 중인 확인을 지금 하고 결과 상태를 돌려준다(없으면 현재 상태). */
  flush(): Promise<FolderCheckState>;
  /** 지금 바로 확인하고 결과 상태를 돌려준다(선택한 경로용, 디바운스 없음). */
  checkNow(path: string): Promise<FolderCheckState>;
  /** 이미 받은 확인 결과를 그대로 상태로 쓴다(요청 없음). 진행 중인 요청은 버린다. */
  adopt(path: string, outcome: FolderCheckOutcome): FolderCheckState;
  /** 마지막 입력을 다시 확인(오류 뒤 [다시 확인]). */
  recheck(): void;
  /** 사용자가 [폴더 만들기]를 눌렀을 때: `create: true`로 확인하고 성공하면 그 결과가 상태가 된다. */
  createHere(): void;
  /** 만드는 중인가. */
  creating: boolean;
}

/**
 * 폴더 확인 훅. 디바운스, 즉시 확인, 오래된 응답 버리기(요청 번호 + AbortController)를 맡는다.
 * 확인 함수는 주입받는다(api-client를 모른다).
 */
export function useFolderCheck(opts: UseFolderCheckOptions): UseFolderCheck {
  const { debounceMs = 300 } = opts;
  const optsRef = useRef(opts);
  useLayoutEffect(() => {
    optsRef.current = opts;
  });
  const [state, setState] = useState<FolderCheckState>(IDLE_STATE);
  const [creating, setCreating] = useState(false);
  const stateRef = useRef(state);
  useLayoutEffect(() => {
    stateRef.current = state;
  }, [state]);
  const seq = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abort = useRef<AbortController | null>(null);
  const latest = useRef("");
  const pending = useRef<Promise<FolderCheckState> | null>(null);

  const run = useCallback((path: string, create: boolean): Promise<FolderCheckState> => {
    abort.current?.abort();
    const ctl = new AbortController();
    abort.current = ctl;
    const my = ++seq.current;
    setState(checkingState(path));
    const o = optsRef.current;
    const p = o
      .check({ path, ...(create ? { create: true } : {}), ...(o.excludeProjectId ? { excludeProjectId: o.excludeProjectId } : {}) }, ctl.signal)
      .then((outcome) => deriveCheckState(path, outcome, { currentFolder: optsRef.current.currentFolder }), () => errorState(path))
      .then((next) => {
        if (my === seq.current) {
          setState(next);
          if (create) setCreating(false);
        }
        return my === seq.current ? next : stateRef.current;
      });
    pending.current = p;
    return p;
  }, []);

  const clearTimer = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };

  const request = useCallback(
    (path: string, o?: { immediate?: boolean }) => {
      latest.current = path;
      clearTimer();
      if (path.trim() === "") {
        abort.current?.abort();
        seq.current += 1;
        pending.current = null;
        setCreating(false);
        setState(IDLE_STATE);
        return;
      }
      if (o?.immediate) {
        void run(path, false);
        return;
      }
      abort.current?.abort();
      seq.current += 1; // 이전 응답은 이제 오래된 것
      setState(checkingState(path));
      timer.current = setTimeout(() => {
        timer.current = null;
        void run(latest.current, false);
      }, debounceMs);
    },
    [debounceMs, run],
  );

  const flush = useCallback((): Promise<FolderCheckState> => {
    if (timer.current) {
      clearTimer();
      return run(latest.current, false);
    }
    return pending.current && stateRef.current.group === "checking" ? pending.current : Promise.resolve(stateRef.current);
  }, [run]);

  const checkNow = useCallback(
    (path: string): Promise<FolderCheckState> => {
      latest.current = path;
      clearTimer();
      if (path.trim() === "") {
        abort.current?.abort();
        seq.current += 1;
        pending.current = null;
        setState(IDLE_STATE);
        return Promise.resolve(IDLE_STATE);
      }
      return run(path, false);
    },
    [run],
  );

  const adopt = useCallback((path: string, outcome: FolderCheckOutcome): FolderCheckState => {
    latest.current = path;
    clearTimer();
    abort.current?.abort();
    seq.current += 1;
    pending.current = null;
    const next = deriveCheckState(path, outcome, { currentFolder: optsRef.current.currentFolder });
    stateRef.current = next;
    setState(next);
    return next;
  }, []);

  const recheck = useCallback(() => {
    if (latest.current.trim() !== "") void run(latest.current, false);
  }, [run]);

  const createHere = useCallback(() => {
    if (latest.current.trim() === "") return;
    setCreating(true);
    void run(latest.current, true);
  }, [run]);

  useEffect(
    () => () => {
      clearTimer();
      abort.current?.abort();
      seq.current += 1;
    },
    [],
  );

  return { state, request, flush, checkNow, adopt, recheck, createHere, creating };
}
