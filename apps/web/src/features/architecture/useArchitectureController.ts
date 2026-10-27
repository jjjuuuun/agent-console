/**
 * 구조도 화면의 상태·질의·동작을 한 곳에 모은 훅(표현은 `ArchitecturePanel`이 맡는다).
 * 세션 상세 흐름 패널, 실행 상세 탭, 크게 보기 대화상자가 같은 훅으로 같은 동작을 얻는다.
 * 이 폴더는 로그 화면(`features/logs`)을 import하지 않는다: 범위·강조할 이벤트·수집 알림은 호출하는 쪽이 넘긴다.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, type LogQueryParams } from "@agent-console/api-client";
import type { ArchitectureMembership, ArchitectureProfileList, ArchitectureView } from "@agent-console/contracts";
import { useToast } from "@agent-console/ui";
import { useStorage } from "../../app/StorageContext";
import { ARCH_LIMITS, ARCH_QUERY, ARCH_STORAGE } from "./archConfig";
import {
  classifyArchError,
  drillQuery,
  drillStepFor,
  dropAfter,
  mergeQuery,
  resolveTarget,
  targetQuery,
  type ArchErrorInfo,
  type ArchTarget,
  type DrillStep,
  type ResolvedTarget,
} from "./archLib";
import { archMessages as t } from "./messages";
import { useArchitectureProfiles, useArchitectureRows, useArchitectureView, useEventMembership, type ArchitectureRows } from "./useArchitectureApi";

export interface ArchitectureControllerOptions {
  /** 구조도와 표 질의에 같이 실리는 범위(세션·레인 `thread` 등). 내용이 같으면 같은 참조로 넘긴다(`useMemo`). */
  scope: LogQueryParams;
  /** false면 질의하지 않는다(세그먼트를 처음 열기 전, 역할이 없을 때). */
  enabled: boolean;
  /** 표에서 고른 이벤트(그 이벤트가 맞은 칸·연결을 강조). */
  highlightUid?: string | null;
  /** 필터 이름 → 칩에 보일 이름(서버 `GET /logs/schema`의 제목). 모르면 이름 그대로. */
  filterTitle?: (name: string) => string;
  /** 프로필 선택 저장 키. 기본은 `ARCH_STORAGE.profile`. */
  profileStorageKey?: string;
}

/** 필터 줄에 놓는 칩 하나(구조도 선택 또는 하위 구조도 단계). */
export interface ArchitectureChip {
  id: string;
  kind: "arch" | "drill";
  label: string;
  /** 지우기 단추의 접근 이름 */
  removeLabel: string;
  onRemove(): void;
}

export interface ArchitectureController {
  enabled: boolean;
  /** 서버에 요청한 프로필 id(없으면 서버 기본) */
  profile: string | undefined;
  setProfile(id: string): void;
  profiles: ArchitectureProfileList | undefined;
  view: ArchitectureView | undefined;
  /** 첫 응답을 기다리는 중 */
  loading: boolean;
  /** 이전 그림을 둔 채 다시 질의하는 중 */
  refreshing: boolean;
  error: ArchErrorInfo | null;
  refetch(): void;
  updatedAt: number | null;
  selection: ArchTarget | null;
  target: ResolvedTarget | undefined;
  /** 선택 대상을 사람이 읽는 이름(칸 이름, 연결 라벨, "칸 › 묶음", "분류 안 됨"). 선택이 없으면 빈 문자열. */
  targetTitle: string;
  drill: readonly DrillStep[];
  /** 표 질의에 더할 인자(구조도 선택·하위 구조도). 둘 다 없으면 null. */
  rowsParams: LogQueryParams | null;
  rows: ArchitectureRows;
  highlight: ArchitectureMembership | null;
  select(next: ArchTarget | null): void;
  blocked(target: ArchTarget, reason: "not_collected" | "structural"): void;
  drillInto(cellId: string, group?: string | null): void;
  /** 빵 부스러기: `index`번째 단계로 돌아간다(`-1` = 처음). 그 뒤 단계의 필터는 사라진다. */
  goTo(index: number): void;
  clearAll(): void;
  /** 로그 수집 알림을 받았을 때(호출하는 쪽이 디바운스한다): 다시 질의한다. */
  ingested(count: number): void;
  /** 10초에 한 번만 바뀌는 polite 알림 문구 */
  announcement: string;
  chips: readonly ArchitectureChip[];
}

/** 구조도 컨트롤러. */
export function useArchitectureController(opts: ArchitectureControllerOptions): ArchitectureController {
  const { scope, enabled, highlightUid = null, filterTitle } = opts;
  const storage = useStorage();
  const toast = useToast();
  const storageKey = opts.profileStorageKey ?? ARCH_STORAGE.profile;
  const [profile, setProfileState] = useState<string | undefined>(() => storage.get(storageKey) || undefined);
  const [picked, setSelection] = useState<ArchTarget | null>(null);
  const [drill, setDrill] = useState<readonly DrillStep[]>([]);
  const [announcement, setAnnouncement] = useState("");

  // ---- 그림: 범위 + 하위 구조도 필터 + 프로필
  const sceneParams = useMemo<LogQueryParams>(() => mergeQuery(scope, drillQuery(drill), profile === undefined ? undefined : { [ARCH_QUERY.profile]: profile }), [scope, drill, profile]);
  // 규칙(프로필)이 하나도 없으면 서버가 404를 내 콘솔 오류가 남는다(5.5R.20). 프로필 목록을 먼저 보고, 0개면 그림을 요청하지 않는다.
  // 목록을 못 읽었으면(오류) 예전처럼 그림을 요청해 서버의 판단을 따른다.
  const profilesQ = useArchitectureProfiles(enabled);
  const noRules = profilesQ.isSuccess && (profilesQ.data.profiles ?? []).every((x) => x.disabled === true);
  const viewReady = profilesQ.isSuccess ? !noRules : profilesQ.isError;
  const viewQ = useArchitectureView(sceneParams, enabled && viewReady);
  const view = viewQ.data;

  // ---- 선택 → 표 질의
  const target = useMemo(() => (view === undefined || picked === null ? undefined : resolveTarget(view, picked, t.noName)), [view, picked]);
  // 새 그림에 고른 대상이 없으면(프로필·범위가 바뀜) 선택이 없는 것으로 본다.
  const selection = picked !== null && view !== undefined && target === undefined && !viewQ.isFetching ? null : picked;
  const rowsParams = useMemo<LogQueryParams | null>(() => {
    if (target !== undefined) return mergeQuery(scope, drillQuery(drill), targetQuery(target.selector, view?.max_seq));
    if (drill.length > 0) return mergeQuery(scope, drillQuery(drill));
    return null;
  }, [target, scope, drill, view?.max_seq]);
  const rows = useArchitectureRows(rowsParams, enabled);

  // 서버가 거절하면(422 등) 이전 상태로 돌아가고 서버 메시지를 알린다. 다 읽은 상태를 "마지막으로 좋았던 상태"로 기억한다.
  const good = useRef<{ selection: ArchTarget | null; drill: readonly DrillStep[] }>({ selection: null, drill: [] });
  useEffect(() => {
    if (rowsParams === null || (rows.complete && rows.error === null)) good.current = { selection, drill };
  }, [rowsParams, rows.complete, rows.error, selection, drill]);
  useEffect(() => {
    const error = rows.error;
    if (error === null) return;
    toast({ tone: "danger", text: t.toast.rejected(error instanceof ApiError || error instanceof Error ? error.message : String(error)) });
    setSelection(good.current.selection);
    setDrill(good.current.drill);
  }, [rows.error, toast]);

  // ---- 강조(표에서 고른 이벤트)
  const membershipQ = useEventMembership(highlightUid, view?.profile, enabled && view !== undefined);
  const highlight = highlightUid !== null && membershipQ.data !== undefined && (membershipQ.data.uid ?? highlightUid) === highlightUid ? membershipQ.data : null;

  // ---- 동작
  const setProfile = useCallback(
    (id: string) => {
      setProfileState(id);
      storage.set(storageKey, id);
      setSelection(null);
    },
    [storage, storageKey],
  );
  const select = useCallback((next: ArchTarget | null) => setSelection(next), []);
  const blocked = useCallback(
    (_target: ArchTarget, reason: "not_collected" | "structural") => toast({ tone: "info", text: reason === "structural" ? t.toast.structural : t.toast.notCollected }),
    [toast],
  );
  const drillInto = useCallback(
    (cellId: string, group?: string | null) => {
      if (view === undefined) return;
      const step = drillStepFor(view, cellId, group, t.noName);
      if (step === undefined) {
        if (group === undefined && view.cells?.find((c) => c.id === cellId)?.drillable) toast({ tone: "info", text: t.toast.pickGroup });
        return;
      }
      setDrill((prev) => [...prev, step]);
      setSelection(null);
    },
    [view, toast],
  );
  const goTo = useCallback((index: number) => {
    setDrill((prev) => dropAfter(prev, index));
    setSelection(null);
  }, []);
  const clearAll = useCallback(() => {
    setDrill([]);
    setSelection(null);
  }, []);

  // ---- 실시간
  const pending = useRef(0);
  const lastAnnounce = useRef(0);
  const { refetch } = viewQ;
  const ingested = useCallback(
    (count: number) => {
      pending.current += count;
      void refetch();
      const now = Date.now();
      if (now - lastAnnounce.current >= ARCH_LIMITS.announceMs && pending.current > 0) {
        setAnnouncement(t.status.reflected(pending.current));
        pending.current = 0;
        lastAnnounce.current = now;
      }
    },
    [refetch],
  );

  const chips = useMemo<ArchitectureChip[]>(() => {
    const out: ArchitectureChip[] = [];
    drill.forEach((step, i) => {
      const label = `${filterTitle?.(step.filter) ?? step.filter}: ${step.label}`;
      out.push({ id: `drill:${i}`, kind: "drill", label, removeLabel: t.chip.drillClear(label), onRemove: () => goTo(i - 1) });
    });
    if (selection !== null && target !== undefined) {
      const label =
        selection.kind === "group" ? t.chip.group(target.cellName ?? "", target.name)
        : selection.kind === "edge" ? t.chip.edge(target.name)
        : selection.kind === "unassigned" ? t.chip.unassigned
        : t.chip.cell(target.name);
      out.push({ id: "arch", kind: "arch", label, removeLabel: t.chip.clear, onRemove: () => setSelection(null) });
    }
    return out;
  }, [drill, selection, target, filterTitle, goTo]);

  const error: ArchErrorInfo | null = enabled && noRules ? { kind: "rules", message: "" } : viewQ.isError && view === undefined ? classifyArchError(viewQ.error) : null;
  return {
    enabled,
    profile,
    setProfile,
    profiles: profilesQ.data,
    view,
    loading: enabled && !noRules && viewQ.isPending,
    refreshing: viewQ.isFetching && view !== undefined,
    error,
    refetch: () => void refetch(),
    updatedAt: viewQ.dataUpdatedAt > 0 ? viewQ.dataUpdatedAt : null,
    selection,
    target,
    targetTitle: selection === null || target === undefined ? "" : selection.kind === "group" ? `${target.cellName ?? ""} › ${target.name}` : selection.kind === "unassigned" ? t.unassigned : target.name,
    drill,
    rowsParams,
    rows,
    highlight,
    select,
    blocked,
    drillInto,
    goTo,
    clearAll,
    ingested,
    announcement,
    chips,
  };
}
