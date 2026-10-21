import { useCallback, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, type RestClient, type Versioned } from "@agent-console/api-client";
import type { Issue, VersionConflictDetails } from "@agent-console/contracts";
import type { FormError } from "@agent-console/schema-form";
import { useApi } from "../app/ApiContext";
import { describeError } from "../app/errors";
import { messages as m } from "../app/messages";
import { useApiQuery } from "../app/queries";
import { jsonEqual } from "../lib/jsonPointer";

export type SavePhase = "idle" | "saving" | "failed";

/**
 * 저장이 일부만 서버에 반영된 채 멈췄을 때 `save`가 던진다(여러 요청으로 나뉘는 정의, 예: 여러 파일).
 * `saved`는 서버에 반영된 상태(새 `version_hash` 포함), `remaining`은 아직 못 보낸 변경이 남은 초안이다.
 * 편집기는 서버 값을 `saved`로 바꾸고 초안을 `remaining`으로 두어 다음 저장이 이어서 진행되게 한다.
 */
export class PartialSaveResult<T> extends Error {
  readonly saved: Versioned<T>;
  readonly remaining: T;
  constructor(message: string, saved: Versioned<T>, remaining: T) {
    super(message);
    this.name = "PartialSaveResult";
    this.saved = saved;
    this.remaining = remaining;
  }
}

export interface DefinitionEditorOptions<T> {
  /** 질의 키(`queryKeys`로 만든다). 저장하면 이 키의 캐시를 새 값으로 바꾼다 */
  queryKey: readonly unknown[];
  /** 서버에서 값과 `version_hash`(ETag)를 읽는다 */
  load: (rest: RestClient) => Promise<Versioned<T>>;
  /** 저장한다. `versionHash`는 `If-Match`로 보낼 값(없으면 undefined). 412는 `ApiError`로 던진다 */
  save: (rest: RestClient, value: T, versionHash: string | undefined) => Promise<Versioned<T>>;
  enabled?: boolean;
}

export interface DefinitionEditor<T> {
  status: "loading" | "error" | "ready";
  error: Error | undefined;
  /** 불러오기를 다시 시도 */
  reload: () => void;
  /** 서버에서 마지막으로 받은 값 */
  base: T | undefined;
  /** 편집 중인 값(편집하지 않았으면 `base`) */
  draft: T | undefined;
  versionHash: string | undefined;
  dirty: boolean;
  setDraft: (next: T | ((current: T) => T)) => void;
  /** 편집 내용을 버리고 서버 값으로 */
  revert: () => void;
  savePhase: SavePhase;
  saveError: string | null;
  /** 마지막 저장이 성공했지만 서버가 경고한 이슈(`X-Console-Issues`). 다음 저장 시작·되돌리기 때 비운다 */
  saveIssues: readonly Issue[];
  /** 422 검증 실패의 필드 오류(JSON Pointer 경로). 화면이 섹션별로 나눠 폼에 넘긴다 */
  fieldErrors: FormError[];
  /** 저장. 성공하면 true. 412는 `conflict`로 올라오고 false */
  save: () => Promise<boolean>;
  conflict: VersionConflictDetails | null;
  /** 충돌 해결: 내 변경을 버리고 서버 버전을 다시 읽는다 */
  loadServerVersion: () => Promise<void>;
  /** 충돌 해결: 서버의 최신 버전 위에 내 변경을 저장한다 */
  overwrite: () => Promise<boolean>;
}

interface Edit<T> {
  baseHash: string | undefined;
  value: T;
}

/**
 * 정의(설정·팀 구성·에이전트·리소스) 편집의 공통 상태: 서버 값 읽기 + 로컬 초안 + 명시 저장(`If-Match`) + 412 충돌.
 * 서버 호출은 `load`/`save`로 주입받아 종류를 모른다. 저장 전에는 서버에 아무것도 보내지 않는다.
 * 다른 곳에서 값이 바뀌어도(창 복귀 갱신) 초안은 유지되며, 저장 때 `If-Match`가 달라 충돌로 드러난다.
 */
export function useDefinitionEditor<T>(options: DefinitionEditorOptions<T>): DefinitionEditor<T> {
  const { queryKey, load, save: saveFn } = options;
  const { rest } = useApi();
  const queryClient = useQueryClient();
  const loaded = useApiQuery<Versioned<T>>(queryKey, load, options.enabled === undefined ? {} : { enabled: options.enabled });
  const baseState = loaded.data;

  const [edit, setEdit] = useState<Edit<T> | null>(null);
  const [savePhase, setSavePhase] = useState<SavePhase>("idle");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveIssues, setSaveIssues] = useState<readonly Issue[]>([]);
  const [fieldErrors, setFieldErrors] = useState<FormError[]>([]);
  const [conflict, setConflict] = useState<VersionConflictDetails | null>(null);

  const base = baseState?.value;
  const draft = edit?.value ?? base;
  const dirty = useMemo(() => edit !== null && base !== undefined && !jsonEqual(edit.value, base), [edit, base]);
  const refetch = loaded.refetch;

  const setDraft = useCallback(
    (next: T | ((current: T) => T)) => {
      if (baseState === undefined) return;
      setEdit((cur) => {
        const current = cur?.value ?? baseState.value;
        return { baseHash: cur?.baseHash ?? baseState.version_hash, value: typeof next === "function" ? (next as (c: T) => T)(current) : next };
      });
    },
    [baseState],
  );

  const revert = useCallback(() => {
    setEdit(null);
    setSaveError(null);
    setConflict(null);
    setFieldErrors([]);
    setSavePhase("idle");
    setSaveIssues([]);
  }, []);

  const applySaved = useCallback(
    (saved: Versioned<T>, sent: T) => {
      queryClient.setQueryData(queryKey, saved);
      // 저장하는 동안 더 고친 내용은 살린다
      setEdit((cur) => (cur !== null && cur.value !== sent ? { baseHash: saved.version_hash, value: cur.value } : null));
      setConflict(null);
      setSavePhase("idle");
      setSaveError(null);
      setFieldErrors([]);
      setSaveIssues(saved.issues ?? []);
    },
    [queryClient, queryKey],
  );

  const report = useCallback(
    (e: unknown) => {
      if (e instanceof PartialSaveResult) {
        const partial = e as PartialSaveResult<T>;
        queryClient.setQueryData(queryKey, partial.saved);
        setSaveIssues(partial.saved.issues ?? []);
        setEdit({ baseHash: partial.saved.version_hash, value: partial.remaining });
        setConflict(null);
        setSavePhase("failed");
        setSaveError(partial.message);
        setFieldErrors([]);
      } else if (e instanceof ApiError && e.versionConflict) {
        setConflict(e.versionConflict);
        setSavePhase("idle");
      } else if (e instanceof ApiError && e.status === 428) {
        setSavePhase("failed");
        setSaveError(m.definition.missingVersion);
      } else {
        setSavePhase("failed");
        setSaveError(describeError(e, m.common.requestFailed).message);
        setFieldErrors(e instanceof ApiError && e.status === 422 ? issuesToFormErrors(e.details["issues"]) : []);
      }
      },
    [queryClient, queryKey],
  );

  const save = useCallback(async (): Promise<boolean> => {
    if (baseState === undefined || draft === undefined || conflict !== null) return false;
    const sent = draft;
    setSavePhase("saving");
    setSaveError(null);
    setSaveIssues([]);
    try {
      applySaved(await saveFn(rest, sent, edit?.baseHash ?? baseState.version_hash), sent);
      return true;
    } catch (e) {
      report(e);
      return false;
    }
  }, [baseState, draft, conflict, saveFn, rest, edit, applySaved, report]);

  const loadServerVersion = useCallback(async () => {
    revert();
    await refetch();
  }, [revert, refetch]);

  const overwrite = useCallback(async (): Promise<boolean> => {
    if (draft === undefined) return false;
    const sent = draft;
    setSavePhase("saving");
    try {
      const latest = await load(rest);
      applySaved(await saveFn(rest, sent, latest.version_hash), sent);
      return true;
    } catch (e) {
      report(e);
      return false;
    }
  }, [draft, load, rest, saveFn, applySaved, report]);

  return {
    status: baseState !== undefined ? "ready" : loaded.isError ? "error" : "loading",
    error: loaded.error ?? undefined,
    reload: () => void refetch(),
    base,
    draft,
    versionHash: baseState?.version_hash,
    dirty,
    setDraft,
    revert,
    savePhase,
    saveError,
    saveIssues,
    fieldErrors,
    save,
    conflict,
    loadServerVersion,
    overwrite,
  };
}

/** 서버 검증 이슈(`Issue[]`)를 폼 오류로. 경로(`path`)가 없는 이슈는 필드에 붙일 수 없어 뺀다. */
export function issuesToFormErrors(raw: unknown): FormError[] {
  if (!Array.isArray(raw)) return [];
  const out: FormError[] = [];
  for (const item of raw as Partial<Issue>[]) {
    if (typeof item?.path === "string" && typeof item.message === "string") {
      out.push({ path: item.path, message: item.message, severity: item.severity === "warning" ? "warning" : "error" });
    }
  }
  return out;
}
