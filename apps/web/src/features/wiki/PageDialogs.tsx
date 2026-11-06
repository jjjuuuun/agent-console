/**
 * 페이지 대화상자 네 개(screen-wiki §4.2~§4.4, §6.10): 새 페이지·이름 바꾸기·지우기 확인·되돌리기 확인.
 * 폼 그림은 `@agent-console/wiki-view`의 `NewPageForm`·`MovePageForm`이 맡고, 여기는 요청(틀 채우기·dry_run·쓰기)과 서버 오류를 화면 문구로 잇는 조립이다.
 * 위키 이름·경로·틀·규칙 id·메시지는 전부 서버 데이터다. 서버 문장은 가공하지 않고 그대로 보인다.
 */
import { useEffect, useRef, useState } from "react";
import { ConfirmDialog, Dialog } from "@agent-console/ui";
import { MovePageForm, NewPageForm, type NewPageValue } from "@agent-console/wiki-view";
import type { WikiBacklink, WikiMoveResult, WikiPageVersion } from "@agent-console/contracts/wiki";
import { classifyWikiError, failureText } from "./wikiErrors";
import { ROUTE_WORDS, WIKI_LIMITS } from "./wikiConfig";
import { useWikiSpace, useWikiTemplates } from "./useWikiApi";
import type { NewPagePrefill } from "./wikiTabs";
import { wikiMessages as m } from "./messages";

const lastSegment = (path: string): string => path.split("/").pop() ?? path;

/** 서버가 읽을 수 없는 이름으로 끝나는 새 경로인가(주소 규칙). 맞으면 그 낱말. */
export function routeWordOf(path: string): string | undefined {
  const last = lastSegment(path.trim());
  return ROUTE_WORDS.find((w) => w === last);
}

// ------------------------------------------------------------------ 새 페이지

export interface NewPageDialogProps {
  wikiId: string;
  wikiName: string;
  open: boolean;
  onClose: () => void;
  prefill?: NewPagePrefill | undefined;
  /** 이미 있는 페이지 경로들(폴더 제안·"이미 있는 페이지" 경고) */
  existingPaths: readonly string[];
  /** 페이지 저장 위치(서버 값) — 경로 미리보기 앞부분. 모르면 줄을 그리지 않는다 */
  directory?: string | undefined;
  blockedReason?: string | undefined;
  /** 자기가 방금 쓴 페이지 경로(`wiki.changed`를 다시 읽지 않기 위해 호출자가 기록한다) */
  onWritten: (paths: readonly string[]) => void;
  onCreated: (path: string) => void;
  onOpenExisting: (path: string) => void;
}

export function NewPageDialog({ wikiId, wikiName, open, onClose, prefill, existingPaths, directory, blockedReason, onWritten, onCreated, onOpenExisting }: NewPageDialogProps) {
  const space = useWikiSpace();
  const templates = useWikiTemplates(wikiId, open);
  const prefilled = prefill?.content !== undefined && prefill.content !== "";
  const [value, setValue] = useState<NewPageValue>({ path: prefill?.path ?? "", title: prefill?.title ?? "", templateId: null, variables: {} });
  const [error, setError] = useState<string | null>(null);
  const [pathError, setPathError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const touched = useRef(prefill?.path !== undefined && prefill.path !== "");
  const word = routeWordOf(value.path);
  const blocked = blockedReason !== undefined && blockedReason !== "";

  // 틀을 고르면 서버가 경로 틀을 채운 경로를 돌려준다(사용자가 경로를 직접 고쳤으면 그 값이 우선)
  const onTemplateChange = (id: string | null) => {
    if (id === null || touched.current) return;
    void space.client.renderWikiTemplate(wikiId, id, { ...(value.title === "" ? {} : { title: value.title }), values: {} }).then(
      (r) => {
        if (r.path !== undefined && r.path !== null && r.path !== "") setValue((v) => (v.templateId === id && !touched.current ? { ...v, path: r.path as string } : v));
      },
      () => undefined,
    );
  };
  const submit = async () => {
    if (busy || blocked) return;
    const path = value.path.trim();
    if (path === "") return;
    if (word !== undefined) {
      setPathError(m.newPage.routeWord(word));
      return;
    }
    setBusy(true);
    setError(null);
    setPathError(null);
    try {
      let content = prefill?.content ?? "";
      if (!prefilled && value.templateId !== null) {
        const rendered = await space.client.renderWikiTemplate(wikiId, value.templateId, { ...(value.title === "" ? {} : { title: value.title }), values: { ...value.variables } });
        content = rendered.content ?? "";
      }
      const saved = await space.client.putWikiPage(wikiId, path, { content }, { createOnly: true });
      onWritten([path]);
      onCreated(saved.value.page.path || path);
    } catch (e) {
      const f = classifyWikiError(e, m.newPage.failed);
      if (f.kind === "pageExists" || f.kind === "invalidPath") setPathError(f.message);
      else setError(failureText(e, m.newPage.failed));
    } finally {
      setBusy(false);
    }
  };
  const preview = directory === undefined || directory === "" ? null : `${directory}/${value.path === "" ? "…" : value.path}`;
  return (
    <Dialog
      open={open}
      title={m.newPage.title}
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <p className="app-muted wiki-hint">{m.newPage.wiki}: <strong>{wikiName}</strong></p>
      <NewPageForm
        value={value}
        onChange={(next) => {
          if (next.path !== value.path) touched.current = true;
          setValue(next);
          setPathError(null);
        }}
        templates={templates.data ?? []}
        onTemplateChange={onTemplateChange}
        existingPaths={existingPaths}
        onOpenExisting={(p) => {
          onClose();
          onOpenExisting(p);
        }}
        prefilledChars={prefilled ? (prefill?.content ?? "").length : null}
        pathError={pathError ?? (word === undefined ? null : m.newPage.routeWord(word))}
        error={error}
        pathPreview={preview}
        submitting={busy}
        readOnly={blocked}
        {...(blocked ? { readOnlyReason: blockedReason } : {})}
        onSubmit={() => void submit()}
        onCancel={onClose}
      />
    </Dialog>
  );
}

// ------------------------------------------------------------------ 이름 바꾸기

export interface MovePageDialogProps {
  wikiId: string;
  from: string;
  open: boolean;
  onClose: () => void;
  /** 저장 안 된 편집 등 막는 이유 */
  blockedReason?: string | undefined;
  readOnly?: boolean;
  readOnlyReason?: string | undefined;
  onWritten: (paths: readonly string[]) => void;
  /** 옮겼다(새 경로, 고친 링크 수). 건너뛴 페이지가 있으면 대화상자는 닫지 않고 이 콜백은 사용자가 닫을 때 불린다. */
  onMoved: (to: string, links: number) => void;
  onOpenPage: (path: string) => void;
}

export function MovePageDialog({ wikiId, from, open, onClose, blockedReason, readOnly = false, readOnlyReason, onWritten, onMoved, onOpenPage }: MovePageDialogProps) {
  const space = useWikiSpace();
  const [to, setTo] = useState(from);
  const [rewrite, setRewrite] = useState(true);
  const [preview, setPreview] = useState<WikiMoveResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [toError, setToError] = useState<string | null>(null);
  const [result, setResult] = useState<WikiMoveResult | null>(null);
  const [busy, setBusy] = useState(false);
  const idle = to.trim() === "" || to.trim() === from;

  // 새 경로를 입력하고 멈추면 dry_run으로 바뀔 페이지·링크를 미리 본다(한 번에 한 건, 앞 요청은 취소)
  useEffect(() => {
    if (!open || result !== null) return;
    const target = to.trim();
    if (target === "" || target === from) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true);
      space.client.moveWikiPage(wikiId, from, { to: target, rewrite_links: rewrite, dry_run: true }, controller.signal).then(
        (r) => {
          if (controller.signal.aborted) return;
          setPreview(r);
          setToError(null);
          setLoading(false);
        },
        (e: unknown) => {
          if (controller.signal.aborted) return;
          setPreview(null);
          setLoading(false);
          const f = classifyWikiError(e, m.move.failed);
          setToError(f.kind === "pageExists" ? m.move.exists : failureText(e, m.move.failed));
        },
      );
    }, WIKI_LIMITS.moveDebounceMs);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [open, to, rewrite, from, wikiId, space, result]);

  const submit = async () => {
    const target = to.trim();
    if (busy || target === "" || target === from) return;
    setBusy(true);
    setToError(null);
    try {
      const r = await space.client.moveWikiPage(wikiId, from, { to: target, rewrite_links: rewrite, dry_run: false });
      onWritten([from, target, ...(r.rewritten ?? []).map((x) => x.path)]);
      const links = (r.rewritten ?? []).reduce((n, x) => n + x.count, 0);
      if ((r.conflicts ?? []).length > 0) setResult(r);
      else {
        onClose();
        onMoved(r.to || target, links);
      }
    } catch (e) {
      const f = classifyWikiError(e, m.move.failed);
      setToError(f.kind === "pageExists" ? m.move.exists : failureText(e, m.move.failed));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} title={m.move.title} size="lg" onClose={() => { if (!busy) onClose(); }}>
      <MovePageForm
        from={from}
        to={to}
        onToChange={(v) => {
          setTo(v);
          setToError(null);
        }}
        rewriteLinks={rewrite}
        onRewriteLinksChange={setRewrite}
        preview={idle ? null : preview}
        previewLoading={loading && !idle}
        result={result}
        toError={idle ? null : toError}
        {...(blockedReason === undefined ? {} : { blockedReason })}
        readOnly={readOnly}
        {...(readOnlyReason === undefined ? {} : { readOnlyReason })}
        submitting={busy}
        onSubmit={() => {
          if (result !== null) {
            const links = (result.rewritten ?? []).reduce((n, x) => n + x.count, 0);
            onClose();
            onMoved(result.to, links);
          } else void submit();
        }}
        onCancel={() => {
          if (result !== null) onMoved(result.to, (result.rewritten ?? []).reduce((n, x) => n + x.count, 0));
          onClose();
        }}
        onOpenPage={onOpenPage}
      />
    </Dialog>
  );
}

// ------------------------------------------------------------------ 지우기·되돌리기 확인

export interface DeletePageDialogProps {
  open: boolean;
  title: string;
  backlinks: readonly WikiBacklink[];
  /** 기록 저장소가 있어 되돌릴 수 있는가 */
  recoverable: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

const BACKLINK_SHOWN = 5;

export function DeletePageDialog({ open, title, backlinks, recoverable, onConfirm, onCancel }: DeletePageDialogProps) {
  return (
    <ConfirmDialog open={open} title={m.delete.title(title)} confirmLabel={m.delete.confirm} cancelLabel={m.cancel} danger onConfirm={onConfirm} onCancel={onCancel}>
      {backlinks.length === 0 ? null : (
        <div className="wiki-warn-block" role="note" data-testid="wiki-delete-backlinks">
          <p>{m.delete.backlinks(backlinks.length)}</p>
          <ul>
            {backlinks.slice(0, BACKLINK_SHOWN).map((b) => <li key={b.path} className="ac-ellipsis" title={b.path}>{b.title !== undefined && b.title !== "" ? b.title : b.path}</li>)}
            {backlinks.length > BACKLINK_SHOWN ? <li className="app-muted">{m.delete.more(backlinks.length - BACKLINK_SHOWN)}</li> : null}
          </ul>
        </div>
      )}
      <p className={recoverable ? "app-muted wiki-hint" : "wiki-hint wiki-danger-text"}>{recoverable ? m.delete.recoverable : m.delete.unrecoverable}</p>
    </ConfirmDialog>
  );
}

export interface RestoreDialogProps {
  open: boolean;
  path: string;
  version: WikiPageVersion | null;
  /** 쓴 주체 이름·시각처럼 이미 문구로 만든 값 */
  authorText: string;
  timeText: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function RestoreDialog({ open, path, version, authorText, timeText, onConfirm, onCancel }: RestoreDialogProps) {
  return (
    <ConfirmDialog
      open={open && version !== null}
      title={version === null ? "" : m.history.restoreTitle(path, version.version, timeText, authorText)}
      confirmLabel={m.history.restoreConfirm}
      cancelLabel={m.cancel}
      onConfirm={onConfirm}
      onCancel={onCancel}
    >
      <p>{m.history.restoreBody}</p>
    </ConfirmDialog>
  );
}
