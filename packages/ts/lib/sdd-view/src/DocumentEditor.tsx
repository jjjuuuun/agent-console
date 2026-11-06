import type { SpecIssue } from "@agent-console/contracts/sdd";
import { TextDiff, TextEditor, type TextEditorHandle } from "@agent-console/text-editor";
import { useEffect, useImperativeHandle, useRef, useState, type ReactNode, type Ref } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { formatMessage, resolveMessages } from "./messages";

/** 보기 방식 어휘(단축키·저장값 검사에도 쓴다) */
export const EDITOR_VIEW_MODES = ["edit", "split", "preview"] as const;
export type EditorViewMode = (typeof EDITOR_VIEW_MODES)[number];

/** `handleRef`로 받는 명령형 핸들. 단축키처럼 편집기 밖에서 오는 동작을 위한 것이다. */
export interface DocumentEditorHandle {
  /** "줄로 이동" 입력칸을 열고 포커스를 옮긴다. */
  openGoToLine: () => void;
  /** 1부터 세는 줄로 이동하고 편집기에 포커스를 둔다. 편집기가 보이지 않으면 false. */
  goToLine: (line: number) => boolean;
}

export interface DocumentEditorProps {
  /** 열린 문서. null이면 "문서를 고르세요" 빈 상태. */
  document: { id: string; title: string; file: string } | null;
  /** 편집기 내용(제어형). 저장·되돌리기는 호출자가 한다. */
  value: string;
  onChange?: (value: string) => void;
  /** Ctrl/Cmd+S 또는 [저장]. 읽기 전용·충돌·조합 중에는 부르지 않는다. */
  onSave?: () => void;
  dirty?: boolean;
  saving?: boolean;
  readOnly?: boolean;
  /** 읽기 전용인 이유(폴더 쓰기 불가 등). 서버·프로젝트 상태에서 온 문구. */
  readOnlyReason?: string;
  /** 본문 파일이 없다(404 `sdd.document_missing`). 앱은 자동으로 만들지 않고 [빈 파일로 만들기]만 준다. */
  missing?: boolean;
  onCreateMissing?: () => void;
  /** 열어 둔 사이 파일이 바뀌었다(해시 불일치·외부 변경). */
  conflict?: boolean;
  onReload?: () => void;
  onOverwrite?: () => void;
  /** 충돌·외부 변경 때 [내 변경 복사]. 클립보드는 호출자가 다룬다(없으면 버튼 없음). */
  onCopyMine?: () => void;
  /**
   * 비교 기준 본문(저장본 또는 충돌·외부 변경 때 서버본)과 그 이름. 주면 [변경 비교]가 나오고 누르면 기준 ↔ 현재 편집본 차이를 보인다.
   * 비교 보기를 처음부터 열어 두려면 `defaultCompareOpen`.
   */
  compare?: { before: string; beforeLabel?: string };
  defaultCompareOpen?: boolean;
  /**
   * 충돌은 아니지만 저장 안 된 편집이 있는 사이 서버 본문이 바뀐 상태. 안내 띠에 [변경 비교]([compare] 있을 때)·[서버 버전 불러오기]([onReload] 있을 때)가 나온다.
   * `conflict`가 있으면 충돌 띠가 우선이다.
   */
  externalChange?: boolean;
  /** 열 때 이동할 줄(1부터). 값이 바뀌면 다시 이동한다. */
  initialLine?: number;
  /** 보기 방식(제어형). 없으면 `defaultMode`에서 시작해 안에서 관리한다. */
  mode?: EditorViewMode;
  onModeChange?: (mode: EditorViewMode) => void;
  handleRef?: Ref<DocumentEditorHandle>;
  /** 저장 응답의 점검 결과(비밀 의심 등). 문구는 서버 `message` 그대로. */
  issues?: readonly SpecIssue[];
  /** 파일 언어(기본 markdown). 미리보기는 markdown일 때만 있다. */
  language?: string;
  maxBytes?: number;
  /** 처음 보기 방식(기본 split). 좁은 영역이면 앱이 edit로 준다. */
  defaultMode?: EditorViewMode;
  /** 편집기 위 도구줄 오른쪽에 붙일 것(상태 전환 메뉴 등). */
  toolbarExtra?: ReactNode;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/**
 * 문서 본문 편집기 = text-editor(CodeMirror) + react-markdown 미리보기. 저장·API를 모르고 상태는 전부 props다.
 * IME 조합 중에는 [저장]을 잠그고 안내한다(text-editor의 조합 상태 API).
 */
export function DocumentEditor(props: DocumentEditorProps) {
  const {
    document, value, onChange, onSave, dirty = false, saving = false, readOnly = false, readOnlyReason, missing = false, onCreateMissing, conflict = false,
    onReload, onOverwrite, onCopyMine, compare, defaultCompareOpen = false, externalChange = false, initialLine, mode: controlledMode, onModeChange, handleRef,
    issues = [], language = "markdown", maxBytes, defaultMode = "split", toolbarExtra, messages, className,
  } = props;
  const text = resolveMessages(messages);
  const [innerMode, setInnerMode] = useState<EditorViewMode>(defaultMode);
  const mode = controlledMode ?? innerMode;
  const setMode = (next: EditorViewMode) => {
    if (controlledMode === undefined) setInnerMode(next);
    onModeChange?.(next);
  };
  const [composing, setComposing] = useState(false);
  const [comparing, setComparing] = useState(defaultCompareOpen);
  const [gotoOpen, setGotoOpen] = useState(false);
  const [gotoText, setGotoText] = useState("");
  const [gotoBad, setGotoBad] = useState(false);
  const handle = useRef<TextEditorHandle>(null);
  const gotoInput = useRef<HTMLInputElement>(null);
  const goTo = (line: number): boolean => handle.current?.goToLine(line) ?? false;
  useImperativeHandle(
    handleRef,
    () => ({
      openGoToLine: () => {
        setGotoOpen(true);
        requestAnimationFrame(() => gotoInput.current?.focus());
      },
      goToLine: (line: number) => goTo(line),
    }),
    [],
  );
  // 열 때(또는 줄 값이 바뀔 때) 그 줄로 이동한다. 편집기가 만들어진 다음 프레임에 시도한다.
  useEffect(() => {
    if (initialLine === undefined) return;
    const id = requestAnimationFrame(() => {
      handle.current?.goToLine(initialLine);
    });
    return () => cancelAnimationFrame(id);
  }, [initialLine, document?.id]);
  const root = `ac-sdd-root ac-sdd-editor${className ? ` ${className}` : ""}`;

  if (!document) {
    return (
      <div className={`${root} ac-sdd-empty`} role="status">
        <p className="ac-sdd-empty-title">{text["editor.empty"]}</p>
      </div>
    );
  }
  if (missing) {
    return (
      <div className={`${root} ac-sdd-empty`} role="alert" data-state="missing">
        <p className="ac-sdd-empty-title">{text["editor.missing.title"]}</p>
        <p className="ac-sdd-muted">{formatMessage(text["editor.missing.body"], { file: document.file })}</p>
        {onCreateMissing ? (
          <button type="button" className="ac-sdd-btn" data-primary="" onClick={onCreateMissing} disabled={readOnly} aria-disabled={readOnly || undefined}>
            {text["editor.missing.create"]}
          </button>
        ) : null}
      </div>
    );
  }

  const locked = readOnly;
  const previewable = language === "markdown";
  const showEdit = mode !== "preview" || !previewable;
  const showPreview = previewable && mode !== "edit";
  const canSave = !locked && !conflict && !saving && dirty && !composing;
  const save = () => {
    if (!locked && !conflict && !composing) onSave?.();
  };
  const openGoto = () => {
    setGotoOpen(true);
    requestAnimationFrame(() => gotoInput.current?.focus());
  };
  const submitGoto = () => {
    const line = Number(gotoText);
    if (!Number.isInteger(line) || line < 1 || line > value.split("\n").length || !goTo(line)) {
      setGotoBad(true);
      return;
    }
    setGotoBad(false);
    setGotoOpen(false);
  };
  const modes: readonly EditorViewMode[] = previewable ? EDITOR_VIEW_MODES : ["edit"];

  return (
    <section className={root} aria-label={document.title} data-readonly={locked || undefined}>
      <div className="ac-sdd-editor-bar">
        <span className="ac-sdd-editor-title ac-sdd-ellipsis">{document.title}</span>
        <span className="ac-sdd-mono ac-sdd-muted ac-sdd-ellipsis">{document.file}</span>
        <span className="ac-sdd-spacer" />
        {previewable ? (
          <div role="group" aria-label={text["editor.mode.group"]} className="ac-sdd-segment">
            {modes.map((m) => (
              <button key={m} type="button" className="ac-sdd-btn" aria-pressed={mode === m} onClick={() => setMode(m)}>
                {text[`editor.mode.${m}`]}
              </button>
            ))}
          </div>
        ) : null}
        {compare ? (
          <button type="button" className="ac-sdd-btn" aria-pressed={comparing} onClick={() => setComparing((v) => !v)}>
            {text["editor.compare"]}
          </button>
        ) : null}
        <button type="button" className="ac-sdd-btn" aria-expanded={gotoOpen} onClick={() => (gotoOpen ? setGotoOpen(false) : openGoto())}>
          {text["editor.goto"]}
        </button>
        {toolbarExtra}
        <span className="ac-sdd-muted" role="status">
          {saving ? text["editor.saving"] : composing ? text["editor.composing"] : dirty ? text["editor.dirty"] : text["editor.saved"]}
        </span>
        <button type="button" className="ac-sdd-btn" data-primary="" onClick={save} disabled={!canSave}>
          {text["editor.save"]}
        </button>
      </div>

      {locked ? (
        <p className="ac-sdd-banner" data-tone="info" role="status">
          <strong>{text["editor.readOnly.title"]}</strong> {readOnlyReason && readOnlyReason !== "" ? readOnlyReason : text["editor.readOnly.body"]}
        </p>
      ) : null}
      {conflict ? (
        <div className="ac-sdd-banner" data-tone="warning" role="alert">
          <strong>{text["editor.conflict.title"]}</strong> {text["editor.conflict.body"]}
          <span className="ac-sdd-banner-actions">
            {onReload ? (
              <button type="button" className="ac-sdd-btn" onClick={onReload}>
                {text["editor.conflict.reload"]}
              </button>
            ) : null}
            {onOverwrite ? (
              <button type="button" className="ac-sdd-btn" onClick={onOverwrite} disabled={locked}>
                {text["editor.conflict.overwrite"]}
              </button>
            ) : null}
            {compare ? (
              <button type="button" className="ac-sdd-btn" aria-pressed={comparing} onClick={() => setComparing((v) => !v)}>
                {text["editor.compare"]}
              </button>
            ) : null}
            {onCopyMine ? (
              <button type="button" className="ac-sdd-btn" onClick={onCopyMine}>
                {text["editor.copyMine"]}
              </button>
            ) : null}
          </span>
        </div>
      ) : externalChange ? (
        <div className="ac-sdd-banner" data-tone="info" role="status" data-state="external-change">
          {text["editor.external.body"]}
          <span className="ac-sdd-banner-actions">
            {compare ? (
              <button type="button" className="ac-sdd-btn" aria-pressed={comparing} onClick={() => setComparing((v) => !v)}>
                {text["editor.compare"]}
              </button>
            ) : null}
            {onReload ? (
              <button type="button" className="ac-sdd-btn" onClick={onReload}>
                {text["editor.conflict.reload"]}
              </button>
            ) : null}
            {onCopyMine ? (
              <button type="button" className="ac-sdd-btn" onClick={onCopyMine}>
                {text["editor.copyMine"]}
              </button>
            ) : null}
          </span>
        </div>
      ) : null}
      {gotoOpen ? (
        <form
          className="ac-sdd-goto"
          onSubmit={(e) => {
            e.preventDefault();
            submitGoto();
          }}
        >
          <label>
            {text["editor.goto.label"]}{" "}
            <input
              ref={gotoInput}
                            type="number"
              min={1}
              inputMode="numeric"
              value={gotoText}
              aria-invalid={gotoBad || undefined}
              onChange={(e) => {
                setGotoText(e.target.value);
                setGotoBad(false);
              }}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  e.stopPropagation();
                  setGotoOpen(false);
                }
              }}
            />
          </label>
          <button type="submit" className="ac-sdd-btn">{text["editor.goto.go"]}</button>
          {gotoBad ? <span className="ac-sdd-muted" role="alert">{text["editor.goto.invalid"]}</span> : null}
        </form>
      ) : null}
      {comparing && compare ? (
        <div className="ac-sdd-compare" role="region" aria-label={text["editor.compare"]}>
          <div className="ac-sdd-compare-head">
            <span className="ac-sdd-muted">{formatMessage(text["editor.compare.head"], { before: compare.beforeLabel ?? text["editor.compare.before"], after: text["editor.compare.after"] })}</span>
            <button type="button" className="ac-sdd-btn" onClick={() => setComparing(false)}>{text["common.close"]}</button>
          </div>
          {compare.before === value ? (
            <p className="ac-sdd-muted" role="status">{text["editor.compare.same"]}</p>
          ) : (
            <TextDiff before={compare.before} after={value} language={language} ariaLabel={text["editor.compare"] ?? ""} maxHeight={320} />
          )}
        </div>
      ) : null}
      {issues.length > 0 ? (
        <ul className="ac-sdd-banner" data-tone="warning" role="list" aria-label={text["editor.issues"]}>
          {issues.map((issue, i) => (
            <li key={`${issue.code}:${issue.line ?? ""}:${i}`}>
              <span className="ac-sdd-mono">{issue.code}</span> {issue.message}
              {issue.line ? <span className="ac-sdd-muted"> · {formatMessage(text["tasks.detail.line"], { line: issue.line })}</span> : null}
              {issue.line && showEdit ? (
                <button type="button" className="ac-sdd-btn" onClick={() => goTo(issue.line as number)}>
                  {text["editor.goto.issue"]}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="ac-sdd-editor-body" data-mode={previewable ? mode : "edit"}>
        {showEdit ? (
          <div className="ac-sdd-editor-pane">
            <TextEditor
              value={value}
              {...(onChange ? { onChange } : {})}
              language={language}
              readOnly={locked}
              ariaLabel={formatMessage(text["editor.label"], { title: document.title })}
              onSave={save}
              {...(maxBytes !== undefined ? { maxBytes } : {})}
              onCompositionChange={setComposing}
              handleRef={handle}
              messages={{ tooLarge: text["editor.tooLarge"] ?? "" }}
            />
          </div>
        ) : null}
        {showPreview ? (
          <div className="ac-sdd-editor-pane ac-sdd-preview" role="region" aria-label={text["editor.preview"]}>
            {value.trim() === "" ? <p className="ac-sdd-muted">{text["editor.previewEmpty"]}</p> : <Markdown remarkPlugins={[remarkGfm]}>{value}</Markdown>}
          </div>
        ) : null}
      </div>
    </section>
  );
}
