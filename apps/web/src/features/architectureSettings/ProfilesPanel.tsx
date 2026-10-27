import { useState } from "react";
import type { ArchitectureProfileCheckRequest, ArchitectureProfileCheckResult } from "@agent-console/contracts";
import { Banner, Button, ConfirmDialog, Spinner } from "@agent-console/ui";
import { ErrorBlock } from "../../app/ErrorBlock";
import { IdDialog } from "./IdDialog";
import { ImportDialog } from "./ImportDialog";
import { ProfileEditor } from "./ProfileEditor";
import { ProfileTable, type RowAction } from "./ProfileTable";
import { archSettingsMessages as t } from "./messages";
import { ORIGIN } from "./messages";
import { deleteProfile, disableProfile, removeKey, setProfile, suggestCloneId, type ProfileRow, type ProfilesMap } from "./profileLogic";
import { newProfileSkeleton, parseProfileYaml, profileToYaml } from "./yamlProfile";

export interface ProfilesPanelProps {
  /** 설정 초안의 `profiles` 맵 */
  profiles: ProfilesMap;
  /** 저장된 설정의 `profiles` 맵(지우기 방식·저장 전 표시 비교) */
  saved: ProfilesMap;
  onChange: (next: ProfilesMap) => void;
  rows: readonly ProfileRow[];
  disabledRows: readonly ProfileRow[];
  includeDefaults: boolean;
  onEnableDefaults: () => void;
  status: "loading" | "error" | "ready";
  error?: Error | null;
  onRetry: () => void;
  /** 기본·플러그인 프로필 본문 한 개(보기·복제용). 서버 상세 응답의 `profile` */
  loadBody: (id: string) => Promise<unknown>;
  check: (body: ArchitectureProfileCheckRequest) => Promise<ArchitectureProfileCheckResult>;
  /** 목록 응답의 기본 프로필 사용 값과 초안이 다르면 알림을 보인다 */
  defaultsPending: boolean;
  disabled?: boolean;
  /** 편집기 검사 지연(ms, 테스트에서 줄인다) */
  checkDelayMs?: number;
}

interface EditorState {
  key: number;
  id: string;
  title: string;
  text: string;
  readOnly: boolean;
}

type DialogState =
  | { kind: "id"; mode: "new" | "clone"; sourceId: string; sourceTitle: string; text: string | null }
  | { kind: "import" }
  | { kind: "remove"; row: ProfileRow }
  | null;

/**
 * 프로필 목록 + 인라인 편집기(표현 전용). 설정 문서에는 초안(`profiles`)만 바꾸고, 파일 기록은 설정 화면의 [저장]이 한다.
 * 서버 호출(본문 읽기·검사)은 props로 받는다.
 */
export function ProfilesPanel(p: ProfilesPanelProps) {
  const { profiles, saved, onChange, rows, disabledRows, includeDefaults, status } = p;
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [dialog, setDialog] = useState<DialogState>(null);
  const [discard, setDiscard] = useState(false);
  const [bodyError, setBodyError] = useState(false);
  const [seq, setSeq] = useState(0);
  const [editorDirty, setEditorDirty] = useState(false);
  const userIds = new Set(Object.entries(profiles).filter(([, v]) => v !== null && typeof v === "object").map(([k]) => k));
  const baseIds = new Set([...rows, ...disabledRows].filter((r) => r.origin !== ORIGIN.user || r.overrides !== undefined).map((r) => r.id));
  const allIds = new Set([...rows, ...disabledRows].map((r) => r.id));

  const openEditor = (id: string, title: string, text: string, readOnly: boolean) => {
    setBodyError(false);
    setEditorDirty(false);
    setSeq((n) => n + 1);
    setEditor({ key: seq + 1, id, title, text, readOnly });
  };
  const bodyOf = async (row: ProfileRow): Promise<Record<string, unknown> | null> => {
    const own = profiles[row.id];
    if (own !== null && typeof own === "object") return own as Record<string, unknown>;
    try {
      const b = await p.loadBody(row.id);
      return (b ?? {}) as Record<string, unknown>;
    } catch {
      setBodyError(true);
      return null;
    }
  };
  const act = async (action: RowAction, row: ProfileRow) => {
    switch (action) {
      case "view": {
        const b = await bodyOf(row);
        if (b !== null) openEditor(row.id, row.title, profileToYaml(b), true);
        return;
      }
      case "edit": {
        const b = await bodyOf(row);
        if (b !== null) openEditor(row.id, row.title, profileToYaml(b), false);
        return;
      }
      case "clone":
        setDialog({ kind: "id", mode: "clone", sourceId: row.id, sourceTitle: row.title, text: null });
        return;
      case "disable":
        onChange(disableProfile(profiles, row.id));
        if (editor?.id === row.id) setEditor(null);
        return;
      case "enable":
      case "revert":
        onChange(removeKey(profiles, row.id));
        if (editor?.id === row.id) setEditor(null);
        return;
      case "remove":
        setDialog({ kind: "remove", row });
    }
  };
  const confirmId = async (id: string, title: string) => {
    if (dialog === null || dialog.kind !== "id") return;
    const d = dialog;
    setDialog(null);
    if (d.text !== null) {
      openEditor(id, title || id, d.text, false);
      return;
    }
    if (d.mode === "new") {
      openEditor(id, title || id, profileToYaml(newProfileSkeleton(title || id, t.editor.newCellId)), false);
      return;
    }
    const src = [...rows, ...disabledRows].find((r) => r.id === d.sourceId);
    const b = src === undefined ? null : await bodyOf(src);
    if (b === null) return;
    openEditor(id, title || id, profileToYaml({ ...b, title: title || id }), false);
  };
  const requestClose = (dirty: boolean) => (dirty ? setDiscard(true) : setEditor(null));

  return (
    <div
      className="arch-settings-panel"
      onKeyDown={(e) => {
        // Esc: 편집기 안(CodeMirror)에서는 편집기 동작이 먼저, 밖에서는 편집기 닫기
        if (e.key !== "Escape" || editor === null || e.defaultPrevented) return;
        if ((e.target as HTMLElement).closest(".cm-editor") !== null) return;
        if ((e.target as HTMLElement).closest("[role=dialog]") !== null) return;
        requestClose(editorDirty);
      }}
    >
      <div className="arch-settings-listhead">
        <h3 className="arch-settings-list-title">{t.list.title(rows.length)}</h3>
        <span className="arch-settings-listhead-actions">
          <Button size="sm" disabled={p.disabled === true} onClick={() => setDialog({ kind: "id", mode: "new", sourceId: "", sourceTitle: "", text: null })}>+ {t.list.new}</Button>
          <Button size="sm" disabled={p.disabled === true} onClick={() => setDialog({ kind: "import" })}>{t.list.import}</Button>
        </span>
      </div>
      {p.defaultsPending ? <p className="app-muted arch-settings-note">{t.list.defaultsPending}</p> : null}
      {status === "loading" ? (
        <p role="status" className="app-muted"><Spinner label={t.editor.checking} /></p>
      ) : status === "error" ? (
        <ErrorBlock title={t.list.loadFailed} {...(p.error ? { message: p.error.message } : {})} retryLabel={t.list.retry} onRetry={p.onRetry} />
      ) : rows.length === 0 && disabledRows.length === 0 ? (
        <div className="arch-settings-empty">
          <p className="arch-settings-empty-title">{t.list.empty}</p>
          <p className="app-muted">{t.list.emptyBody}</p>
          {includeDefaults ? null : <Button size="sm" onClick={p.onEnableDefaults}>{t.list.enableDefaults}</Button>}
        </div>
      ) : (
        <ProfileTable rows={rows} disabledRows={disabledRows} openId={editor?.id ?? null} onAction={(a, r) => void act(a, r)} {...(p.disabled === undefined ? {} : { disabled: p.disabled })} />
      )}
      {bodyError ? <Banner tone="warning">{t.editor.loadFailed}</Banner> : null}
      {editor === null ? null : (
        <ProfileEditor
          key={editor.key}
          id={editor.id}
          title={editor.title}
          initialText={editor.text}
          readOnly={editor.readOnly}
          check={p.check}
          {...(p.checkDelayMs === undefined ? {} : { delayMs: p.checkDelayMs })}
          onSave={(body) => {
            onChange(setProfile(profiles, editor.id, body));
            setEditor(null);
          }}
          onClose={requestClose}
          onDirtyChange={setEditorDirty}
        />
      )}
      {dialog?.kind === "id" ? (
        <IdDialog
          title={dialog.mode === "new" ? t.dialog.newTitle : t.dialog.cloneTitle(dialog.sourceTitle)}
          defaultId={dialog.mode === "clone" ? suggestCloneId(dialog.sourceId, allIds) : ""}
          defaultTitle={dialog.mode === "clone" ? dialog.sourceTitle : ""}
          baseIds={baseIds}
          userIds={userIds}
          onConfirm={(id, title) => void confirmId(id, title)}
          onCancel={() => setDialog(null)}
        />
      ) : null}
      {dialog?.kind === "import" ? (
        <ImportDialog
          onCancel={() => setDialog(null)}
          onImport={(text) => {
            const parsed = parseProfileYaml(text);
            const title = parsed.ok && typeof parsed.value["title"] === "string" ? parsed.value["title"] : "";
            setDialog({ kind: "id", mode: "new", sourceId: "", sourceTitle: title, text });
          }}
        />
      ) : null}
      <ConfirmDialog
        open={dialog?.kind === "remove"}
        danger
        title={dialog?.kind === "remove" ? t.dialog.removeTitle(dialog.row.title) : ""}
        confirmLabel={t.dialog.removeOk}
        cancelLabel={t.dialog.cancel}
        onCancel={() => setDialog(null)}
        onConfirm={() => {
          if (dialog?.kind === "remove") {
            onChange(deleteProfile(profiles, dialog.row.id, saved));
            if (editor?.id === dialog.row.id) setEditor(null);
          }
          setDialog(null);
        }}
      >
        <p className="ac-text">{t.dialog.removeBody}</p>
      </ConfirmDialog>
      <ConfirmDialog
        open={discard}
        danger
        title={t.editor.discardTitle}
        confirmLabel={t.editor.discardOk}
        cancelLabel={t.dialog.cancel}
        onCancel={() => setDiscard(false)}
        onConfirm={() => {
          setDiscard(false);
          setEditor(null);
        }}
      >
        <p className="ac-text">{t.editor.discardBody}</p>
      </ConfirmDialog>
    </div>
  );
}
