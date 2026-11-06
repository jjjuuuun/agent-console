/**
 * 페이지 저장·되돌리기·지우기 같은 쓰기 동작과 그 결과(띠에 보일 실패·경고)를 한곳에 모은 훅.
 * 낙관적 갱신은 없다 — 서버 응답으로 닫는다. 실패는 `WikiFailure` 종류로 나눠 들고 화면이 띠로 보인다.
 */
import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Issue } from "@agent-console/contracts";
import type { WikiPageView } from "@agent-console/contracts/wiki";
import type { Versioned } from "@agent-console/api-client";
import { classifyWikiError, type WikiFailure } from "./wikiErrors";
import { ownWriteKey, useWikiSpace, wikiKeys, type OwnWrites } from "./useWikiApi";
import { wikiMessages as m } from "./messages";

export interface SaveOutcome {
  /** 저장은 됐지만 경고할 이슈(규칙 경고·비밀 의심) */
  warnings: readonly Issue[];
}

/** 쓰기 결과: 성공이면 `saved`, 실패면 `failure`. */
export type WriteResult = { saved: Versioned<WikiPageView>; failure: null } | { saved: null; failure: WikiFailure };

export interface PageSaver {
  saving: boolean;
  /** 마지막 쓰기 실패(성공하면 비운다) */
  failure: WikiFailure | null;
  /** 마지막 쓰기의 경고 이슈 */
  warnings: readonly Issue[];
  clearFailure: () => void;
  clearWarnings: () => void;
  /** 본문 저장. 성공하면 서버가 돌려준 페이지, 실패하면 실패 종류(`failure`에도 남는다). */
  save: (path: string, content: string, expectedHash: string | undefined) => Promise<WriteResult>;
  /** 기록의 한 버전으로 되돌리기. */
  restore: (path: string, version: number) => Promise<WriteResult>;
}

export function usePageSaver(wikiId: string, ownWrites: { readonly current: OwnWrites }, onWritten: () => void): PageSaver {
  const space = useWikiSpace();
  const qc = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<WikiFailure | null>(null);
  const [warnings, setWarnings] = useState<readonly Issue[]>([]);

  const finish = useCallback(
    (path: string, saved: Versioned<WikiPageView>) => {
      ownWrites.current.set(ownWriteKey(wikiId, path), Date.now());
      qc.setQueryData(wikiKeys.page(space.key, wikiId, path), saved);
      setFailure(null);
      setWarnings(saved.issues ?? []);
      onWritten();
    },
    [ownWrites, wikiId, qc, space.key, onWritten],
  );

  const save = useCallback<PageSaver["save"]>(
    async (path, content, expectedHash) => {
      setSaving(true);
      setFailure(null);
      try {
        const saved = await space.client.putWikiPage(wikiId, path, { content }, expectedHash === undefined ? {} : { expectedHash });
        finish(path, saved);
        return { saved, failure: null };
      } catch (e) {
        const failure = classifyWikiError(e, m.band.saveFailed);
        setFailure(failure);
        return { saved: null, failure };
      } finally {
        setSaving(false);
      }
    },
    [space, wikiId, finish],
  );

  const restore = useCallback<PageSaver["restore"]>(
    async (path, version) => {
      setSaving(true);
      setFailure(null);
      try {
        const saved = await space.client.restoreWikiPage(wikiId, path, { version });
        finish(path, saved);
        return { saved, failure: null };
      } catch (e) {
        const failure = classifyWikiError(e, m.history.restoreFailed);
        setFailure(failure);
        return { saved: null, failure };
      } finally {
        setSaving(false);
      }
    },
    [space, wikiId, finish],
  );

  return { saving, failure, warnings, clearFailure: () => setFailure(null), clearWarnings: () => setWarnings([]), save, restore };
}
