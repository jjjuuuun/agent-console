import { useState } from "react";
import { Banner } from "@agent-console/ui";
import type { WikiSummary } from "@agent-console/contracts/wiki";
import { NewPageDialog } from "./PageDialogs";
import { usePageList } from "./useWikiApi";
import { useWikiContext } from "./useWikiContext";
import { wikiLinkMessages as t } from "./integrationMessages";

export interface PromoteSource {
  title: string;
  content: string;
}

export interface PromoteDialogProps {
  wikis: readonly WikiSummary[];
  /** 처음 고를 위키 id(마지막으로 쓴 위키, 없으면 첫 번째) */
  initialWiki: string;
  source: PromoteSource;
  onClose: () => void;
  /** 만들었다(위키 id, 경로). 자기 쓰기 기록·토스트는 호출자가 맡는다 */
  onCreated: (wikiId: string, path: string) => void;
  onOpenExisting: (wikiId: string, path: string) => void;
}

/**
 * 메모리 항목 등에서 본문을 위키 새 페이지로 복사해 올리는 대화상자(screen-wiki.md 11.3). 새 페이지 대화상자에 본문·제목을 채우고
 * 위키 고르기와 "복사본입니다" 안내를 끼운다. 원본과 연결하지 않는다. 경로는 비워 둔다.
 */
export function PromoteDialog({ wikis, initialWiki, source, onClose, onCreated, onOpenExisting }: PromoteDialogProps) {
  const ctx = useWikiContext();
  const [wikiId, setWikiId] = useState(wikis.some((w) => w.id === initialWiki) ? initialWiki : (wikis[0]?.id ?? ""));
  const pages = usePageList(wikiId, wikiId !== "");
  const chosen = wikis.find((w) => w.id === wikiId);
  const name = chosen?.name || wikiId;
  const directory = chosen?.directory !== undefined && chosen.directory !== "" ? chosen.directory : ctx.pagesRoot === undefined ? undefined : `${ctx.pagesRoot}/${wikiId}`;
  const selectId = "wiki-promote-target";
  return (
    <NewPageDialog
      key={wikiId}
      wikiId={wikiId}
      wikiName={name}
      open
      onClose={onClose}
      prefill={{ title: source.title, content: source.content }}
      existingPaths={(pages.data?.items ?? []).map((p) => p.path)}
      directory={directory}
      blockedReason={ctx.readOnly ? (ctx.readOnlyReason ?? "") : undefined}
      onWritten={() => undefined}
      onCreated={(path) => onCreated(wikiId, path)}
      onOpenExisting={(path) => onOpenExisting(wikiId, path)}
      header={
        <div className="wiki-promote-head">
          <Banner tone="info">{t.fromMemory.note}</Banner>
          {wikis.length > 1 ? (
            <label htmlFor={selectId}>
              {t.fromMemory.wiki}{" "}
              <select id={selectId} value={wikiId} onChange={(e) => setWikiId(e.target.value)}>
                {wikis.map((w) => (
                  <option key={w.id} value={w.id}>{w.name || w.id}</option>
                ))}
              </select>
            </label>
          ) : null}
        </div>
      }
    />
  );
}
