import { useEffect, useState } from "react";
import { keepPreviousData } from "@tanstack/react-query";
import { ApiError, type RestClient } from "@agent-console/api-client";
import { useApiQuery } from "../../app/queries";
import { LINK_PART_IDS, useLinkPart } from "../../modules";

/** 초안 계산을 요청하기 전 기다리는 시간(밀리초). 변경이 멈춘 뒤에 한 번만 묻는다. */
export const DRAFT_DEBOUNCE_MS = 600;

/** `enabled`가 true인 동안 값이 `ms` 동안 바뀌지 않아야 따라온다. false면 즉시 현재 값. */
export function useDebouncedValue<T>(value: T, ms: number, enabled = true): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    if (!enabled) return;
    const handle = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(handle);
  }, [value, ms, enabled]);
  return enabled ? settled : value;
}

export interface DraftPreviewOptions<T, D> {
  /** 질의 키 접두(그래프·노드 식별). 초안 키는 입력까지 더해 따로 만든다 */
  keyBase: readonly unknown[];
  /** 저장 전 초안 입력. `undefined`면 초안 모드가 아니다(저장본을 읽는다) */
  draftInput: D | undefined;
  /** 저장본을 읽을 수 있는가(저장 전 노드 등은 false) */
  savedEnabled?: boolean;
  /** 저장본 키에 더할 값(저장하면 바뀌는 버전 등) */
  savedKeyExtra?: string;
  loadSaved: (rest: RestClient) => Promise<T>;
  loadDraft: (rest: RestClient, input: D) => Promise<T>;
  delayMs?: number;
}

export interface DraftPreviewResult<T> {
  data: T | undefined;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  /** 지금 보이는 값이 초안 기준인가 */
  isDraft: boolean;
  /** 초안 계산이 진행 중(마지막 성공 결과는 그대로 둔다) */
  updating: boolean;
  refetch: () => void;
}

/**
 * 저장본 질의와 초안 질의를 하나로 합친다. 초안 모드면 `delayMs` 디바운스 뒤 서버에 초안을 묻고,
 * 갱신 중에는 마지막 성공 결과를 유지한다. 초안 경로는 연동 부분 `teams.draft-preview`(`links/linkParts.ts`가 필요한 모듈을 정한다)가
 * 켜져 있을 때만 부른다. 꺼져 있거나 서버가 경로를 모르면(404/405) 저장본으로 폴백한다. 이 폴백은 이 훅 인스턴스에만 걸린다
 * (모듈 전역 기억 없음: 모듈이 다시 켜지면 `/modules` 갱신으로 다음 마운트부터 다시 묻는다).
 */
export function useDraftPreview<T, D>(opts: DraftPreviewOptions<T, D>): DraftPreviewResult<T> {
  const { keyBase, draftInput, loadSaved, loadDraft, savedEnabled = true, savedKeyExtra = "" } = opts;
  const [lastDraft, setLastDraft] = useState<T | undefined>(undefined);
  const wantsDraft = draftInput !== undefined;
  const draftPart = useLinkPart(LINK_PART_IDS.teamsDraftPreview);
  const mayAskDraft = wantsDraft && draftPart.visible;
  const settled = useDebouncedValue(draftInput, opts.delayMs ?? DRAFT_DEBOUNCE_MS, mayAskDraft);

  const draft = useApiQuery<T>(
    ["list", ...keyBase, "draft", settled ?? null],
    (rest) => loadDraft(rest, settled as D),
    { enabled: mayAskDraft && settled !== undefined, retry: false, staleTime: 0, placeholderData: keepPreviousData },
  );

  // 404/405면 서버가 초안 경로를 모른다(연동이 꺼졌는데 목록이 아직 낡은 경우 등): 바로 저장본으로 폴백한다.
  const unsupportedNow = draft.error instanceof ApiError && (draft.error.status === 404 || draft.error.status === 405);
  const draftOn = mayAskDraft && !unsupportedNow;
  const saved = useApiQuery<T>(["list", ...keyBase, savedKeyExtra], loadSaved, { enabled: savedEnabled && !draftOn, retry: false });

  // 마지막으로 성공한 초안 결과(갱신이 실패해도 유지한다)
  const draftData = draft.data;
  if (draftData !== undefined && draftData !== lastDraft) setLastDraft(draftData);

  if (!draftOn) {
    return { data: saved.data, isLoading: savedEnabled && saved.isLoading, isError: saved.isError, error: saved.error, isDraft: false, updating: false, refetch: () => void saved.refetch() };
  }
  return {
    data: draftData ?? lastDraft,
    isLoading: (draftData ?? lastDraft) === undefined && !draft.isError,
    isError: draft.isError,
    error: draft.error,
    isDraft: true,
    updating: draft.isFetching || settled !== draftInput,
    refetch: () => void draft.refetch(),
  };
}
