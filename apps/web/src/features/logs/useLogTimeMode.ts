/**
 * 로그 이벤트 표 시각 열의 표시 방식(날짜·시각 / 시각만 / 경과 시각). 모든 로그 화면이 같은 값을 쓴다.
 * 저장은 화면 상태 저장소(localStorage, 실패해도 메모리만으로 동작)다. 같은 탭의 다른 표는 구독으로, 다른 탭은 `storage` 이벤트로 따라온다.
 */
import { useCallback, useMemo, useSyncExternalStore } from "react";
import { parseTimeMode, timeColumnWidth, type TimeMode } from "@agent-console/log-view";
import { useStorage } from "../../app/StorageContext";
import type { SafeStorage } from "../../app/storage";
import { LOGS_STORAGE } from "./logsConfig";

/** 옛 값(`absolute` = 시각만, `relative` = 경과)을 새 방식 id로 옮긴다. 모르는 값은 기본(날짜·시각). */
export function readTimeMode(storage: SafeStorage): TimeMode {
  const raw = storage.get(LOGS_STORAGE.timeMode);
  return parseTimeMode(raw === "absolute" ? "time" : raw === "relative" ? "elapsed" : raw);
}

const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export interface LogTimeMode {
  mode: TimeMode;
  setMode(mode: TimeMode): void;
  /** 이 방식에 맞는 시각 열 폭(`eventColumns`의 폭 표에 그대로 넘긴다) */
  widths: Readonly<Record<string, number>>;
}

/** 시각 열 표시 방식과 그에 맞는 열 폭. */
export function useLogTimeMode(): LogTimeMode {
  const storage = useStorage();
  const subscribe = useCallback((cb: () => void) => {
    listeners.add(cb);
    const onStorage = (e: StorageEvent) => {
      if (e.key === LOGS_STORAGE.timeMode) cb();
    };
    window.addEventListener("storage", onStorage);
    return () => {
      listeners.delete(cb);
      window.removeEventListener("storage", onStorage);
    };
  }, []);
  const mode = useSyncExternalStore(subscribe, () => readTimeMode(storage), () => "datetime" as TimeMode);
  const setMode = useCallback(
    (next: TimeMode) => {
      storage.set(LOGS_STORAGE.timeMode, next);
      emit();
    },
    [storage],
  );
  const widths = useMemo(() => ({ time: timeColumnWidth(mode) }), [mode]);
  return { mode, setMode, widths };
}
