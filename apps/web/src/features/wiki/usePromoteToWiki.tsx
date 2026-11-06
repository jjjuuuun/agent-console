import { lazy, Suspense, useCallback, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { useToast, type MenuItemDef } from "@agent-console/ui";
import { useProjectId } from "../../app/projectScope";
import { useStorage } from "../../app/StorageContext";
import { describeError } from "../../app/errors";
import { useModule } from "../../modules";
import { PROMOTE } from "./integrationConfig";
import { wikiLinkMessages as t } from "./integrationMessages";
import type { PromoteSource } from "./PromoteDialog";
import { useInvalidateWiki, useWikiList } from "./useWikiApi";
import { WIKI_ROLE } from "./wikiConfig";
import { wikiPagePath } from "./wikiPaths";

// 대화상자는 처음 열 때 내려받는다(메모리 화면 번들에 위키 편집 부품이 들어가지 않게).
const Dialog = lazy(() => import("./PromoteDialog").then((m) => ({ default: m.PromoteDialog })));

export type { PromoteSource } from "./PromoteDialog";

/** 본문 첫 줄(빈 줄 건너뜀)을 제목으로. 길면 `max`자에서 자른다. */
export function titleFromContent(content: string, max = PROMOTE.titleMax): string {
  const line = content.split(/\r?\n/).find((l) => l.trim() !== "") ?? "";
  return Array.from(line.trim()).slice(0, max).join("");
}

export interface PromoteToWiki {
  /** 항목 메뉴에 더할 줄. 역할 `wiki`가 없거나 현재 프로젝트가 없으면 null(항목 자체가 없다) */
  menuItem: (id: string, load: () => Promise<PromoteSource | null>) => MenuItemDef | null;
  /** 열린 대화상자(없으면 null). 화면 아무 데나 한 번 그린다 */
  dialog: ReactNode;
}

/**
 * 다른 화면의 항목을 위키 새 페이지로 복사해 올리는 동작(screen-wiki.md 11.3). 위키는 항목을 모르고 `{title, content}`만 받는다.
 * 켜짐 조건 = 위키 화면 역할이 있고 현재 프로젝트가 있을 때(호출 쪽은 자기 화면 역할이 이미 있다). 프로젝트의 위키가 0개면 줄은 보이되 비활성이다.
 */
export function usePromoteToWiki(): PromoteToWiki {
  // 서버 모듈 목록의 웹 역할로 본다. 목록을 받기 전(확인 중)에는 켜지 않는다(`useRoutesOn`은 확인 중에 켜짐으로 읽는다)
  const wikiRole = useModule(WIKI_ROLE);
  const projectId = useProjectId();
  const on = wikiRole.active && projectId !== null;
  const list = useWikiList(on);
  const storage = useStorage();
  const toast = useToast();
  const navigate = useNavigate();
  const invalidate = useInvalidateWiki();
  const [source, setSource] = useState<PromoteSource | null>(null);
  const lastKey = projectId === null ? "" : `${PROMOTE.lastWikiStorage}${projectId}`;
  const noWiki = list.isSuccess && list.data.length === 0;

  const menuItem = useCallback(
    (id: string, load: () => Promise<PromoteSource | null>): MenuItemDef | null => {
      if (!on) return null;
      return {
        id,
        label: t.fromMemory.menu,
        disabled: noWiki,
        ...(noWiki ? { title: t.fromMemory.noWiki } : {}),
        onSelect: () => {
          load().then(
            (s) => {
              if (s !== null) setSource(s);
            },
            (e: unknown) => toast({ tone: "danger", text: `${t.fromMemory.loadFailed}: ${describeError(e, t.fromMemory.loadFailed).message}` }),
          );
        },
      };
    },
    [on, noWiki, toast],
  );

  const dialog = useMemo(() => {
    const wikis = list.data ?? [];
    if (source === null || wikis.length === 0) return null;
    return (
      <Suspense fallback={null}>
        <Dialog
          wikis={wikis}
          initialWiki={storage.get(lastKey) ?? ""}
          source={source}
          onClose={() => setSource(null)}
          onCreated={(wikiId, path) => {
            storage.set(lastKey, wikiId);
            setSource(null);
            void invalidate();
            toast({ tone: "success", text: t.fromMemory.created, durationMs: PROMOTE.toastMs, action: { label: t.fromMemory.open, onClick: () => void navigate(wikiPagePath(wikiId, path)) } });
          }}
          onOpenExisting={(wikiId, path) => {
            setSource(null);
            void navigate(wikiPagePath(wikiId, path));
          }}
        />
      </Suspense>
    );
  }, [source, list.data, storage, lastKey, invalidate, toast, navigate]);

  return { menuItem, dialog };
}
