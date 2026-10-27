import { useCallback } from "react";
import { ApiError } from "@agent-console/api-client";
import { folderOf, withFolder } from "@agent-console/list-arrange";
import { useToast } from "@agent-console/ui";
import { describeError } from "../../app/errors";
import { useInvalidateLists } from "./data";
import type { ArrangeMessages } from "./arrangeMessages";

type Doc = Record<string, unknown>;

/** 정의 종류마다 다른 읽기·저장 경로를 주입한다(에이전트·팀 구성·리소스). 저장은 문서 전체를 바꾸는 `PUT` + `If-Match`다. */
export interface DefinitionStore<T extends object> {
  load: (id: string) => Promise<{ value: T; version_hash?: string | undefined }>;
  save: (value: T, versionHash: string | undefined) => Promise<unknown>;
}

export interface DefinitionEdits {
  /** 폴더를 옮긴다(최신 원문을 읽어 폴더만 바꿔 `If-Match`로 저장). 성공하면 되돌리기 토스트. 실패는 오류 토스트. */
  moveToFolder: (id: string, name: string, folder: string | undefined) => Promise<boolean>;
  /** 라벨을 바꿔 저장한다. */
  saveLabels: (id: string, name: string, labels: string[]) => Promise<boolean>;
}

/** attributes가 비게 되면 원래 없던 키는 만들지 않는다. */
function withAttributes(doc: Doc, attributes: Record<string, unknown>): Doc {
  if (Object.keys(attributes).length === 0 && doc["attributes"] === undefined) return doc;
  return { ...doc, attributes };
}

const isConflict = (e: unknown): boolean => e instanceof ApiError && (e.status === 412 || e.status === 428);

/**
 * 목록의 가벼운 편집(폴더 이동·라벨) 공용 훅. 저장 경로는 `store`로 받아 종류를 모른다.
 * 항상 최신 문서를 읽고 → 일부만 바꾸고 → 그 `ETag`로 저장하므로 다른 필드는 보존된다.
 * 412·428(버전 충돌)이면 안내 토스트에 [다시 시도]를 붙인다(다시 시도는 최신 문서를 새로 읽는다).
 */
export function useDefinitionEdits<T extends object>(store: DefinitionStore<T>, m: Pick<ArrangeMessages, "move" | "labels" | "conflict" | "retry">): DefinitionEdits {
  const toast = useToast();
  const invalidate = useInvalidateLists();
  const { load, save } = store;

  const edit = useCallback(
    async (id: string, change: (d: Doc) => Doc): Promise<Doc> => {
      const { value, version_hash } = await load(id);
      await save(change({ ...(value as Doc) }) as T, version_hash);
      await invalidate();
      return value as Doc;
    },
    [load, save, invalidate],
  );

  const fail = useCallback(
    (e: unknown, fallback: string, retry: () => void) => {
      if (isConflict(e)) toast({ tone: "danger", text: m.conflict, action: { label: m.retry, onClick: retry } });
      else toast({ tone: "danger", text: describeError(e, fallback).message });
    },
    [toast, m],
  );

  async function moveToFolder(id: string, name: string, folder: string | undefined): Promise<boolean> {
      try {
        const before = await edit(id, (d) => withAttributes(d, withFolder(d["attributes"] as Doc | undefined, folder)));
        const prev = folderOf(before["attributes"] as Doc | undefined);
        toast({
          tone: "success",
          text: folder === undefined ? m.move.doneClear(name) : m.move.done(name, folder),
          action: {
            label: m.move.undo,
            onClick: () => {
              const undo = (): void => {
                void edit(id, (d) => withAttributes(d, withFolder(d["attributes"] as Doc | undefined, prev)))
                  .then(() => toast({ tone: "info", text: m.move.undone }))
                  .catch((e: unknown) => fail(e, m.move.failed, undo));
              };
              undo();
            },
          },
        });
        return true;
      } catch (e) {
        fail(e, m.move.failed, () => void moveToFolder(id, name, folder));
        return false;
      }
  }

  async function saveLabels(id: string, name: string, labels: string[]): Promise<boolean> {
      try {
        await edit(id, (d) => {
          const { labels: _l, ...rest } = d;
          void _l;
          return labels.length === 0 ? rest : { ...rest, labels };
        });
        toast({ tone: "success", text: m.labels.saved(name) });
        return true;
      } catch (e) {
        fail(e, m.labels.failed, () => void saveLabels(id, name, labels));
        return false;
      }
  }

  return { moveToFolder, saveLabels };
}
