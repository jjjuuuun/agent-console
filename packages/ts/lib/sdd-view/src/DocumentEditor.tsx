import type { SpecIssue } from "@agent-console/contracts/sdd";
import { TextEditor, type TextEditorHandle } from "@agent-console/text-editor";
import { useRef, useState, type ReactNode } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { formatMessage, resolveMessages } from "./messages";

export type EditorViewMode = "edit" | "preview" | "split";

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
    onReload, onOverwrite, issues = [], language = "markdown", maxBytes, defaultMode = "split", toolbarExtra, messages, className,
  } = props;
  const text = resolveMessages(messages);
  const [mode, setMode] = useState<EditorViewMode>(defaultMode);
  const [composing, setComposing] = useState(false);
  const handle = useRef<TextEditorHandle>(null);
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
  const modes: EditorViewMode[] = previewable ? ["edit", "split", "preview"] : ["edit"];

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
          </span>
        </div>
      ) : null}
      {issues.length > 0 ? (
        <ul className="ac-sdd-banner" data-tone="warning" role="list" aria-label={text["editor.issues"]}>
          {issues.map((issue, i) => (
            <li key={`${issue.code}:${issue.line ?? ""}:${i}`}>
              <span className="ac-sdd-mono">{issue.code}</span> {issue.message}
              {issue.line ? <span className="ac-sdd-muted"> · {formatMessage(text["tasks.detail.line"], { line: issue.line })}</span> : null}
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
