/**
 * 위키 목록·위키 화면이 같이 쓰는 대화상자 컨테이너 훅: 새 위키·zip 가져오기·zip 내보내기·위키 삭제.
 * 각 훅은 `{ open, dialog }`를 돌려주고 `dialog`를 화면 어디든 한 번 그린다(열려 있을 때만 마운트된다).
 * 요청·캐시 갱신·토스트·이동은 여기서 하고 대화상자 자체는 props만 받는다.
 */
import { useCallback, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useToast, ConfirmDialog } from "@agent-console/ui";
import type { WikiCreateRequest, WikiSummary } from "@agent-console/contracts/wiki";
import { useApi } from "../../app/ApiContext";
import { describeError } from "../../app/errors";
import { saveBlob } from "../../lib/download";
import { routePath, useRouteOn } from "../library";
import { useCopyDialog } from "../projects";
import { NewWikiDialog } from "./NewWikiDialog";
import { WikiExportDialog, WikiImportDialog } from "./WikiTransferDialog";
import { wikiMessages as m } from "./messages";
import { useInvalidateWiki, useWikiList, useWikiRulesList, useWikiSpace } from "./useWikiApi";
import { useWikiContext } from "./useWikiContext";
import { wikiRulesPath } from "./wikiPaths";
import { WIKI_RULES_ROLE } from "./wikiConfig";
import { useNavigate } from "react-router";

/** 위키 규칙 화면이 이 앱에 있고 켜져 있는가(규칙 열기·공용에서 가져오기 UI의 조건). */
export function useRulesScreenOn(): boolean {
  const on = useRouteOn(WIKI_RULES_ROLE);
  return wikiRulesPath() !== undefined && on;
}

/**
 * 공용 위키 규칙의 정의 종류 이름. 서버 설정으로 바뀌는 값이라 코드에 두지 않고, 공용 규칙 하나의 정의에서 읽는다.
 * 공용에 규칙이 없으면 가져올 것도 없으므로 `null`이다. 읽지 못하면(정의 모듈 꺼짐 등) `null`.
 */
function useLibraryRulesKind(enabled: boolean): { kind: string | null; loading: boolean } {
  const { wiki } = useApi();
  const q = useQuery({
    queryKey: ["wiki", "library-rules-kind"],
    enabled,
    retry: false,
    meta: { silentBackgroundError: true },
    queryFn: async (): Promise<string | null> => {
      const library = wiki(null);
      const first = (await library.listWikiRules())[0];
      if (first === undefined) return null;
      return (await library.getWikiRules(first.id)).value.rules.kind;
    },
  });
  return { kind: q.data ?? null, loading: enabled && q.isPending };
}

export interface DialogHook {
  open: () => void;
  dialog: ReactNode;
}

/** 새 위키 대화상자. 만들면 `onCreated(위키 id)`를 부른다(보통 그 위키 화면으로 이동). */
export function useNewWikiDialog(onCreated: (wikiId: string) => void, onImportZip?: () => void): DialogHook {
  const [shown, setShown] = useState(false);
  const open = useCallback(() => setShown(true), []);
  const copy = useCopyDialog();
  const dialog = (
    <>
      {shown ? <NewWikiHost onClose={() => setShown(false)} onCreated={onCreated} copy={copy} {...(onImportZip === undefined ? {} : { onImportZip })} /> : null}
      {copy.dialog}
    </>
  );
  return { open, dialog };
}

function NewWikiHost({ onClose, onCreated, copy, onImportZip }: { onClose: () => void; onCreated: (id: string) => void; copy: ReturnType<typeof useCopyDialog>; onImportZip?: () => void }) {
  const space = useWikiSpace();
  const ctx = useWikiContext();
  const invalidate = useInvalidateWiki();
  const rules = useWikiRulesList(true);
  const rulesScreen = useRulesScreenOn();
  const canImport = rulesScreen && ctx.capabilities.rules_library && ctx.projectId !== null;
  const library = useLibraryRulesKind(canImport);
  const navigate = useNavigate();
  const importRules = (added: (ruleId: string) => void) => {
    const kind = library.kind;
    if (kind === null || ctx.projectId === null) return;
    copy.open({
      direction: "import",
      project: ctx.projectId,
      start: "pick",
      onlyKinds: [kind],
      onApplied: (outcome) => {
        void invalidate();
        if (outcome.first !== null && outcome.first.kind === kind) added(outcome.first.id);
      },
    });
  };
  return (
    <NewWikiDialog
      open
      onClose={onClose}
      folder={ctx.projectName === undefined ? undefined : { name: ctx.projectName }}
      pagesRoot={ctx.pagesRoot}
      rules={rules.data}
      rulesFailed={rules.isError}
      blockedReason={ctx.readOnly ? ctx.readOnlyReason : undefined}
      {...(canImport ? { onImportRules: importRules, importDisabledReason: library.loading || library.kind !== null ? undefined : m.newWiki.fromLibraryNone } : {})}
      {...(rulesScreen ? { onOpenRule: (id: string) => void navigate(wikiRulesPath(id) ?? routePath(WIKI_RULES_ROLE)) } : {})}
      onImportZip={ctx.capabilities.import_export && onImportZip !== undefined ? () => { onClose(); onImportZip(); } : undefined}
      onSubmit={async (body: WikiCreateRequest) => {
        const created = await space.client.createWiki(body);
        await invalidate();
        onClose();
        onCreated(created.value.wiki.id);
      }}
    />
  );
}

/** zip 가져오기 대화상자. 끝나면 `onImported(위키 id, 가져온 수)`. */
export function useImportDialog(onImported?: (wikiId: string, n: number) => void): { open: (wikiId?: string) => void; dialog: ReactNode } {
  const [state, setState] = useState<{ wiki?: string } | null>(null);
  const open = useCallback((wikiId?: string) => setState(wikiId === undefined ? {} : { wiki: wikiId }), []);
  const dialog = state === null ? null : <ImportHost initialWiki={state.wiki} onClose={() => setState(null)} {...(onImported === undefined ? {} : { onImported })} />;
  return { open, dialog };
}

function ImportHost({ initialWiki, onClose, onImported }: { initialWiki: string | undefined; onClose: () => void; onImported?: (wikiId: string, n: number) => void }) {
  const space = useWikiSpace();
  const ctx = useWikiContext();
  const list = useWikiList();
  const toast = useToast();
  const invalidate = useInvalidateWiki();
  const run = useCallback(
    (wiki: string, zip: Uint8Array, policy: string, dryRun: boolean) => space.client.importWiki(wiki, zip, { policy, dryRun }),
    [space],
  );
  return (
    <WikiImportDialog
      open
      onClose={onClose}
      wikis={list.data ?? []}
      initialWiki={initialWiki}
      blockedReason={ctx.readOnly ? ctx.readOnlyReason : undefined}
      run={run}
      onDone={(wiki, n) => {
        void invalidate();
        onClose();
        toast({ tone: "success", text: m.transfer.done(n) });
        onImported?.(wiki, n);
      }}
    />
  );
}

/** zip 내보내기 대화상자(확인 → 내려받기). */
export function useExportDialog(): { open: (wiki: WikiSummary) => void; dialog: ReactNode } {
  const [target, setTarget] = useState<WikiSummary | null>(null);
  const space = useWikiSpace();
  const open = useCallback((w: WikiSummary) => setTarget(w), []);
  const dialog =
    target === null ? null : (
      <WikiExportDialog
        open
        onClose={() => setTarget(null)}
        name={target.name && target.name !== "" ? target.name : target.id}
        pages={target.pages ?? null}
        onDownload={async () => {
          const r = await space.client.exportWiki(target.id);
          saveBlob(r.blob, r.filename ?? `${target.id}.zip`);
        }}
      />
    );
  return { open, dialog };
}

/** 위키 삭제 확인(정의만 지워지고 페이지 폴더는 남는다는 것을 알린다). 끝나면 `onDeleted`. */
export function useDeleteWikiDialog(onDeleted?: (wikiId: string) => void): { open: (wiki: WikiSummary) => void; dialog: ReactNode } {
  const [target, setTarget] = useState<WikiSummary | null>(null);
  const space = useWikiSpace();
  const toast = useToast();
  const invalidate = useInvalidateWiki();
  const open = useCallback((w: WikiSummary) => setTarget(w), []);
  const remove = async (w: WikiSummary) => {
    try {
      const current = await space.client.getWiki(w.id);
      await space.client.deleteWiki(w.id, current.version_hash ?? current.value.version_hash);
      setTarget(null);
      await invalidate();
      const directory = w.directory ?? "";
      toast({
        tone: "success",
        text: m.deleteWiki.done,
        durationMs: 8000,
        ...(directory === "" ? {} : { action: { label: m.deleteWiki.copyPath, onClick: () => void navigator.clipboard?.writeText(directory) } }),
      });
      onDeleted?.(w.id);
    } catch (e) {
      setTarget(null);
      toast({ tone: "danger", text: describeError(e, m.deleteWiki.failed).message });
    }
  };
  const name = target === null ? "" : target.name && target.name !== "" ? target.name : target.id;
  const dialog =
    target === null ? null : (
      <ConfirmDialog open title={m.deleteWiki.title(name)} confirmLabel={m.deleteWiki.confirm} cancelLabel={m.cancel} danger onConfirm={() => void remove(target)} onCancel={() => setTarget(null)}>
        <p>{m.deleteWiki.body(target.directory ?? "")}</p>
        <p className="app-muted">{m.deleteWiki.usage}</p>
      </ConfirmDialog>
    );
  return { open, dialog };
}
