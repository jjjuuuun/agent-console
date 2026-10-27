import { useMemo, useState } from "react";
import type { ArchitectureProfileCheckRequest, ArchitectureProfileCheckResult, Issue } from "@agent-console/contracts";
import { Button, Icon, Tooltip } from "@agent-console/ui";
import { LazyTextEditor } from "../library";
import { archSettingsMessages as t } from "./messages";
import { useProfileCheck } from "./useProfileCheck";
import { lineOfPath, parseProfileYaml } from "./yamlProfile";

export interface ProfileEditorProps {
  id: string;
  title: string;
  /** 편집을 시작한 YAML 글 */
  initialText: string;
  readOnly: boolean;
  /** 서버 검사(주입). 화면은 프로필 필드를 해석하지 않는다 */
  check: (body: ArchitectureProfileCheckRequest) => Promise<ArchitectureProfileCheckResult>;
  /** 저장(설정 초안에 반영). 이 편집기는 설정 파일을 직접 쓰지 않는다 */
  onSave: (body: Record<string, unknown>) => void;
  /** 닫기. 고친 내용이 있으면 호출자가 확인한다(`dirty`를 같이 준다) */
  onClose: (dirty: boolean) => void;
  /** 편집 내용이 바뀔 때(목록 행의 점 표시용) */
  onDirtyChange?: (dirty: boolean) => void;
  /** 검사 지연(ms, 기본 600) */
  delayMs?: number;
}

const pad = (n: number) => String(n).padStart(2, "0");
const timeText = (ms: number) => {
  const d = new Date(ms);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
};

/**
 * 프로필 YAML 편집기: 왼쪽 text-editor, 오른쪽 검사 결과. 편집이 멈추면 서버에 검사를 보내고,
 * 오류가 남아 있으면 [프로필 저장]을 끈다(경고·안내는 막지 않는다). 검사 요청이 실패하면 막지 않는다.
 */
export function ProfileEditor({ id, title, initialText, readOnly, check, onSave, onClose, onDirtyChange, delayMs }: ProfileEditorProps) {
  const [text, setText] = useState(initialText);
  const dirty = text !== initialText;
  const result = useProfileCheck(text, id, check, !readOnly, delayMs);
  const parsed = useMemo(() => parseProfileYaml(text), [text]);
  const errors = result.issues.filter((i) => i.severity === "error").length;
  const parseMessage = result.parseError === null ? null : result.parseError.message === "" ? t.editor.notMap : result.parseError.message;
  const blocked = readOnly || !parsed.ok || result.phase === "checking" || errors > 0;
  const blockReason = readOnly ? t.editor.readOnly : !parsed.ok ? t.editor.parseError : result.phase === "checking" ? t.editor.saveChecking : errors > 0 ? t.editor.saveBlocked : undefined;
  const count = result.issues.length + (result.parseError === null ? 0 : 1);
  const headId = `arch-editor-${id}`;
  const save = () => {
    if (!blocked && parsed.ok) onSave(parsed.value);
  };
  return (
    <section className="arch-settings-editor" aria-labelledby={headId} data-testid="arch-profile-editor">
      <div className="arch-settings-editor-head">
        <h3 id={headId} className="arch-settings-editor-title">{(readOnly ? t.editor.viewTitle : t.editor.title)(title, id)}</h3>
        <div className="arch-settings-editor-actions">
          {readOnly ? null : blocked && blockReason !== undefined ? (
            <Tooltip content={blockReason} align="end">
              <span tabIndex={0} role="group" aria-label={`${t.editor.save}: ${blockReason}`} className="arch-settings-save-host" data-testid="arch-save-reason">
                <Button variant="primary" size="sm" disabled onClick={save}>{t.editor.save}</Button>
              </span>
            </Tooltip>
          ) : (
            <Button variant="primary" size="sm" disabled={blocked} onClick={save}>{t.editor.save}</Button>
          )}
          <Button size="sm" onClick={() => onClose(dirty)}>{t.editor.close}</Button>
        </div>
      </div>
      {readOnly ? <p className="app-muted arch-settings-note">{t.editor.readOnly}</p> : <p className="app-muted arch-settings-note">{t.editor.saveNote}</p>}
      <div className="arch-settings-editor-body">
        <div className="arch-settings-yaml">
          <LazyTextEditor
            value={text}
            readOnly={readOnly}
            language="text"
            ariaLabel={t.editor.yamlLabel}
            height={320}
            onChange={(v) => {
              setText(v);
              onDirtyChange?.(v !== initialText);
            }}
            onSave={save}
          />
        </div>
        <div className="arch-settings-results" role="region" aria-label={t.editor.results} aria-live="polite">
          <h4 className="arch-settings-results-title">{t.editor.results}</h4>
          {readOnly ? null : <CheckBody result={result} text={text} count={count} parseMessage={parseMessage} />}
        </div>
      </div>
    </section>
  );
}

function CheckBody({ result, text, count, parseMessage }: { result: ReturnType<typeof useProfileCheck>; text: string; count: number; parseMessage: string | null }) {
  if (result.parseError !== null) {
    return (
      <ul className="arch-settings-issues" data-testid="arch-issues">
        <li className="arch-settings-issue" data-severity="error">
          <span className="app-sev" data-severity="error" role="img" aria-label={t.editor.severity["error"] ?? "error"}>{t.editor.severityGlyph["error"]}</span>
          <span className="arch-settings-issue-text">{t.editor.parseError}: {parseMessage}{result.parseError.line === null ? "" : ` (${t.editor.line(result.parseError.line)})`}</span>
        </li>
      </ul>
    );
  }
  if (result.phase === "failed") {
    return (
      <p role="status" className="arch-settings-failed">
        {t.editor.checkFailed} — <Button size="sm" variant="ghost" onClick={result.retry}>{t.list.retry}</Button>
      </p>
    );
  }
  if (result.phase === "checking" || result.phase === "idle") return <p role="status" className="app-muted">{t.editor.checking}</p>;
  return (
    <>
      {count === 0 ? (
        <p className="arch-settings-ok"><span className="app-sev" data-severity="success" aria-hidden="true"><Icon name="check" size={14} /></span> {t.editor.ok}</p>
      ) : (
        <>
          <p className="arch-settings-count">{t.editor.problems(count)}</p>
          <ul className="arch-settings-issues" data-testid="arch-issues">
            {result.issues.map((i, n) => <IssueItem key={`${i.code}:${i.path ?? ""}:${n}`} issue={i} text={text} />)}
          </ul>
        </>
      )}
      {result.checkedAt === null ? null : <p className="app-muted arch-settings-checked">{t.editor.checkedAt(timeText(result.checkedAt))}</p>}
    </>
  );
}

function IssueItem({ issue, text }: { issue: Issue; text: string }) {
  const line = issue.path ? lineOfPath(text, issue.path) : null;
  const label = t.editor.severity[issue.severity] ?? issue.severity;
  return (
    <li className="arch-settings-issue" data-severity={issue.severity}>
      <span className="app-sev" data-severity={issue.severity === "error" ? "error" : "warning"} data-glyph={issue.severity} role="img" aria-label={label}>{t.editor.severityGlyph[issue.severity] ?? t.editor.severityGlyph["warning"]}</span>
      <span className="arch-settings-issue-text">
        {issue.message}
        {issue.path ? <span className="arch-settings-issue-path"> {issue.path}</span> : null}
        {line === null ? null : <span className="app-muted"> · {t.editor.line(line)}</span>}
      </span>
    </li>
  );
}
