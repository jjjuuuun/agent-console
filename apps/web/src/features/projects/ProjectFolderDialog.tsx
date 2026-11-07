import { useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError } from "@agent-console/api-client";
import { FolderPicker, createTranslate, middleEllipsis, type FolderCheckState, type FolderSelectPhase, IDLE_STATE } from "@agent-console/folder-picker";
import { folderErrorOutcome } from "@agent-console/projects";
import { Banner, Button, Dialog, Disclosure } from "@agent-console/ui";
import { folderHomeMessages as m } from "./folderHomeMessages";
import { canSubmitAdd, canSubmitRepath, suggestionFor } from "./projectFolderLib";
import type { FolderApi } from "./useFolderApi";

const fpText = createTranslate();

/** 제출 값. 호출한 쪽(호스트)이 서버 호출·토스트·이동을 맡는다. */
export type FolderSubmit =
  | { kind: "add"; folder: string; name: string; id: string | undefined; description: string | undefined; adopted: number | null; manifestInvalid: boolean }
  | { kind: "reregister"; projectId: string; name: string }
  | { kind: "repath"; folder: string };

/** 경로 다시 지정 대상(표시용 값). */
export interface RepathTarget {
  id: string;
  name: string;
  /** 지금 등록된 경로. null/빈 값 = 폴더 미지정 */
  folder: string | null;
  /** 상태 칩 글자(문제 상태일 때) */
  statusLabel?: string | undefined;
  /** 서버가 준 구성 폴더 이름(`{dir}`) */
  configDir?: string | undefined;
  /** "제안" 경로(미지정 폴더의 제안 버튼). 없으면 줄 없음 */
  suggestedFolder?: string | undefined;
  /** 앱에 저장된 옛 기록이 있는가(안내 한 줄) */
  hasAppRecords?: boolean | undefined;
}

export interface ProjectFolderDialogProps {
  mode: "add" | "repath";
  /** `repath`일 때 대상 */
  target?: RepathTarget | undefined;
  api: FolderApi;
  /** 제출. 거절(예외)이면 대화상자 안에 오류를 보이고 열어 둔다. 성공이면 호출자가 닫는다. */
  onSubmit: (value: FolderSubmit) => Promise<void>;
  onClose: () => void;
  /** 이미 등록된 폴더 [열기]·[그 프로젝트 열기] */
  onOpenProject?: ((projectId: string) => void) | undefined;
  /** 프로젝트 id → 이름(충돌 문구용). 없으면 id */
  projectName?: ((id: string) => string | undefined) | undefined;
}

interface Problem {
  tone: "danger" | "warning" | "info";
  text: string;
  /** 보관된 같은 폴더면 [다시 등록] 단서 */
  reregister?: { projectId: string; name: string };
  openId?: string;
}

/** 서버 오류를 대화상자 안 배너 문구로 바꾼다(예상한 409 충돌은 확인 상태와 같은 문구). */
function problemOf(error: unknown, fallback: string, nameOf: (id: string) => string | undefined): { problem: Problem; idField: string | null } {
  if (error instanceof ApiError) {
    const outcome = folderErrorOutcome(error, { projectName: nameOf });
    if (outcome?.kind === "taken") {
      return outcome.archived
        ? { problem: { tone: "info", text: m.dialog.archivedFound(outcome.name), reregister: { projectId: outcome.projectId, name: outcome.name } }, idField: null }
        : { problem: { tone: "danger", text: fpText("folder.check.taken", { name: outcome.name }), openId: outcome.projectId }, idField: null };
    }
    if (outcome?.kind === "overlap") {
      const key = outcome.relation === "parent" ? "folder.check.overlap_parent" : "folder.check.overlap_child";
      return { problem: { tone: "danger", text: fpText(key, { name: outcome.name, path: middleEllipsis(outcome.path, 40) }), openId: outcome.projectId }, idField: null };
    }
    if (outcome?.kind === "remote_disabled") return { problem: { tone: "warning", text: fpText("folder.check.remote_disabled") }, idField: null };
    if (error.status === 422 && JSON.stringify(error.details).includes('"id"')) return { problem: { tone: "danger", text: error.message }, idField: error.message };
    return { problem: { tone: "danger", text: error.message || fallback }, idField: null };
  }
  return { problem: { tone: "danger", text: fallback }, idField: null };
}

/**
 * 프로젝트 폴더 추가(`add`)·경로 다시 지정(`repath`) 대화상자(표현 + 입력 상태, screen-projects §3).
 * 폴더 고르기는 `@agent-console/folder-picker`가 하고, 이름·id·설명·제출은 여기서 한다.
 * 서버 호출·이동·토스트는 `api`와 `onSubmit`으로 주입받는다.
 */
export function ProjectFolderDialog({ mode, target, api, onSubmit, onClose, onOpenProject, projectName }: ProjectFolderDialogProps) {
  const uid = useId();
  const add = mode === "add";
  const [path, setPath] = useState("");
  const [state, setState] = useState<FolderCheckState>(IDLE_STATE);
  const [phase, setPhase] = useState<FolderSelectPhase>("idle");
  const [name, setName] = useState("");
  const [id, setId] = useState("");
  const [description, setDescription] = useState("");
  const touched = useRef({ name: false, id: false, description: false });
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [idError, setIdError] = useState<string | null>(null);
  const submitRef = useRef<HTMLButtonElement>(null);
  const nameOf = useCallback((pid: string) => projectName?.(pid), [projectName]);

  const info = api.lastCheckFor(state.check?.path ?? state.forInput);
  const suggestion = useMemo(() => suggestionFor(state, info), [state, info]);
  // 선택 전에는 마지막으로 받은 `config_dir`, 그것도 없으면 모름(undefined) — `{dir}` 없는 짝 문장을 쓴다
  const dir = info?.config_dir ?? target?.configDir ?? api.configDir ?? undefined;

  // 확인이 통과한 경로마다 고치지 않은 이름·id·설명만 새 제안으로 바꾼다
  const filledFor = useRef<string | null>(null);
  useEffect(() => {
    if (!add || !state.submittable || state.check === null) return;
    const key = state.check.path ?? state.forInput;
    if (key === filledFor.current) return;
    filledFor.current = key;
    if (!touched.current.name) setName(suggestion.name);
    if (!touched.current.id) setId(suggestion.id);
    if (!touched.current.description) setDescription(suggestion.description);
  }, [add, state, suggestion]);

  const waiting = phase === "waiting";
  const canSubmit = add ? canSubmitAdd(state, name, busy, waiting) : canSubmitRepath(state, busy, waiting);
  const reregister = add && state.reregister && state.outcome?.kind === "taken" ? state.outcome : null;

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setProblem(null);
    setIdError(null);
    try {
      const folder = state.check?.path ?? path.trim();
      if (!add) await onSubmit({ kind: "repath", folder });
      else if (reregister) await onSubmit({ kind: "reregister", projectId: reregister.projectId, name: reregister.name });
      else {
        await onSubmit({
          kind: "add",
          folder,
          name: name.trim(),
          id: id.trim() === "" ? undefined : id.trim(),
          description: description.trim() === "" ? undefined : description.trim(),
          adopted: suggestion.adopted === null ? null : suggestion.adopted.definitions,
          manifestInvalid: suggestion.manifestInvalid,
        });
      }
    } catch (e) {
      const r = problemOf(e, add ? m.dialog.submitFailed : m.dialog.repathFailed, nameOf);
      setProblem(r.problem);
      setIdError(r.idField);
    } finally {
      setBusy(false);
    }
  };

  const reregisterNow = async (hit: { projectId: string; name: string }) => {
    setBusy(true);
    setProblem(null);
    try {
      await onSubmit({ kind: "reregister", projectId: hit.projectId, name: hit.name });
    } catch (e) {
      setProblem(problemOf(e, m.dialog.submitFailed, nameOf).problem);
    } finally {
      setBusy(false);
    }
  };

  const title = add ? m.dialog.addTitle : target?.folder ? m.dialog.repathTitle(target.name) : m.dialog.repathTitleUnset(target?.name ?? "");
  const submitLabel = busy ? m.dialog.busy : add ? (reregister ? m.dialog.reregisterSubmit : m.dialog.addSubmit) : m.dialog.repathSubmit;
  const close = () => {
    if (!busy) onClose();
  };

  const adoptNote: ReactNode =
    !add && state.id === "manifest_found" && suggestion.adopted !== null ? (
      <Banner tone="info" role="status">{m.dialog.repathNoteAdopt(suggestion.adopted.name, suggestion.adopted.definitions)}</Banner>
    ) : null;

  return (
    <Dialog
      open
      title={title}
      onClose={close}
      actions={
        <>
          <Button onClick={close} disabled={busy}>{m.dialog.cancel}</Button>
          <Button
            ref={submitRef}
            variant="primary"
            loading={busy}
            aria-disabled={!canSubmit && !busy ? "true" : undefined}
            onClick={() => void submit()}
          >
            {submitLabel}
          </Button>
        </>
      }
    >
      <div
        className="prj-fd"
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            void submit();
          }
        }}
      >
        {add ? (
          <p className="prj-fd-intro">{m.dialog.addIntro}</p>
        ) : (
          <div className="prj-fd-old">
            {target?.folder ? (
              <>
                <span className="prj-fd-old-label">{m.dialog.repathOld}</span>
                <span className="ac-mono-wrap prj-fd-old-path">{target.folder}</span>
                {target.statusLabel === undefined ? null : <span className="prj-chip-status">{target.statusLabel}</span>}
              </>
            ) : target?.suggestedFolder ? (
              <>
                <span className="prj-fd-old-label">{m.dialog.repathSuggest}</span>
                <span className="ac-mono-wrap prj-fd-old-path">{target.suggestedFolder}</span>
                <Button size="sm" onClick={() => setPath(target.suggestedFolder ?? "")}>{m.dialog.repathSuggestApply}</Button>
              </>
            ) : null}
          </div>
        )}

        <FolderPicker
          id={`${uid}-fp`}
          value={path}
          onValueChange={setPath}
          check={api.check}
          list={api.list}
          createFolder={api.createFolder}
          roots={api.roots}
          capabilities={api.capabilities}
          {...(api.pickNative === undefined ? {} : { onPickNative: api.pickNative })}
          {...(dir ? { configDir: dir } : {})}
          {...(!add && target?.folder ? { excludeProjectId: target.id, currentFolder: target.folder } : {})}
          disabled={busy}
          autoFocus
          onStateChange={setState}
          onSelectPhaseChange={setPhase}
          onSubmit={() => void submit()}
          {...(onOpenProject === undefined ? {} : { onOpenProject })}
          onPicked={(_p, st) => {
            if (st.submittable && add) document.getElementById(`${uid}-name`)?.focus();
          }}
        />

        {adoptNote}
        {!add ? (
          <Banner tone="info" role="status">
            {dir ? fpWithDir(m.dialog.repathNoteConfig, dir) : m.dialog.repathNoteConfigUnknown} {m.dialog.repathNoteLogs}
          </Banner>
        ) : null}

        {add && (path.trim() !== "" || state.submittable) ? (
          <>
            <div className="prj-fd-field">
              <label htmlFor={`${uid}-name`}>{m.dialog.name} *</label>
              <input
                id={`${uid}-name`}
                className="ac-input"
                value={name}
                disabled={busy || reregister !== null}
                aria-required="true"
                aria-describedby={suggestion.adopted !== null ? `${uid}-name-help` : undefined}
                onChange={(e) => {
                  touched.current.name = true;
                  setName(e.target.value);
                }}
              />
              {suggestion.adopted !== null ? <span id={`${uid}-name-help`} className="app-muted lib-field-note">{m.dialog.nameAdoptedHelp}</span> : null}
            </div>
            <Disclosure summary={m.dialog.advanced}>
              <div className="prj-fd-field">
                <label htmlFor={`${uid}-id`}>{m.dialog.id}</label>
                <input
                  id={`${uid}-id`}
                  className="ac-input ac-mono"
                  value={id}
                  disabled={busy || reregister !== null}
                  aria-invalid={idError !== null ? "true" : undefined}
                  aria-describedby={`${uid}-id-help`}
                  onChange={(e) => {
                    touched.current.id = true;
                    setId(e.target.value);
                    setIdError(null);
                  }}
                />
                <span id={`${uid}-id-help`} className="app-muted lib-field-note">{m.dialog.idHelp}</span>
                {idError === null ? null : <span className="prj-fd-error" role="alert">{idError}</span>}
              </div>
              <div className="prj-fd-field">
                <label htmlFor={`${uid}-desc`}>{m.dialog.description}</label>
                <textarea
                  id={`${uid}-desc`}
                  className="ac-input"
                  rows={2}
                  value={description}
                  disabled={busy || reregister !== null}
                  onChange={(e) => {
                    touched.current.description = true;
                    setDescription(e.target.value);
                  }}
                />
              </div>
            </Disclosure>
          </>
        ) : null}

        {problem === null ? null : (
          <Banner
            tone={problem.tone}
            actions={
              problem.reregister !== undefined ? (
                <Button size="sm" onClick={() => void reregisterNow(problem.reregister as { projectId: string; name: string })}>{m.dialog.reregisterSubmit}</Button>
              ) : problem.openId !== undefined && onOpenProject !== undefined ? (
                <Button size="sm" onClick={() => onOpenProject(problem.openId as string)}>{m.dialog.takenOpen}</Button>
              ) : undefined
            }
          >
            {problem.text}
          </Banner>
        )}
      </div>
    </Dialog>
  );
}

/** `{dir}` 자리를 고정폭 글자로 바꿔 그린다. */
function fpWithDir(template: string, dir: string): ReactNode {
  const parts = template.split("{dir}");
  return parts.flatMap((part, i) => (i === 0 ? [part] : [<code key={i}>{dir === "" ? "…" : dir}</code>, part]));
}
