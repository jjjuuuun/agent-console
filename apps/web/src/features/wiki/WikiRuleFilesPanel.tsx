/**
 * 본문 파일 탭(screen-wiki §10.3): 규칙이 가리키는 파일(지침·페이지 틀)의 연결 상태(파일 없음 + [만들기] / 규칙에 연결되지 않음) + 파일 트리·편집기(`MultiFileTab`).
 * 초안(`files`)은 부모가 갖고 저장도 부모가 한다. 서버·규칙 id를 모른다.
 */
import { Button } from "@agent-console/ui";
import { MultiFileTab, sortEntries, type FileEntry } from "../resources";
import { wikiRulesMessages } from "./rulesScreenMessages";

const t = wikiRulesMessages.files;

/** 규칙이 가리키는 본문 파일 하나(종류별 표시 이름은 호출자가 안다). */
export interface RuleFileLink {
  /** 본문 폴더 안 상대 경로 */
  file: string;
  kind: "instructions" | "template";
  /** 페이지 틀의 id·표시 이름(지침이면 없음) */
  label?: string;
}

export interface WikiRuleFilesPanelProps {
  links: readonly RuleFileLink[];
  files: readonly FileEntry[];
  originFiles: readonly FileEntry[];
  onChange: (next: FileEntry[]) => void;
  /** 저장 실패한 파일의 서버 메시지(경로 → 메시지) */
  errors?: Readonly<Record<string, string>>;
  onDismissError?: (path: string) => void;
  onSave: () => void;
  /** 편집을 막는다(읽기 전용·저장 중) */
  disabled: boolean;
}

export function WikiRuleFilesPanel({ links, files, originFiles, onChange, errors, onDismissError, onSave, disabled }: WikiRuleFilesPanelProps) {
  const have = new Set(files.map((f) => f.path));
  const linked = new Set(links.map((l) => l.file));
  const unlinked = files.filter((f) => !linked.has(f.path));
  const hasInstructions = links.some((l) => l.kind === "instructions");
  const hasTemplates = links.some((l) => l.kind === "template");
  return (
    <div className="wiki-rule-files">
      <section aria-label={t.links}>
        <h3 className="wiki-label">{t.links}</h3>
        {links.length === 0 ? (
          <p className="app-muted">{t.noLinks}</p>
        ) : (
          <ul className="wiki-rule-links">
            {links.map((l) => (
              <li key={`${l.kind}:${l.file}`} data-missing={have.has(l.file) ? undefined : "true"}>
                <span className="app-muted">{l.kind === "instructions" ? t.instructions : t.template}</span>{" "}
                {l.label === undefined ? null : <span className="ac-ellipsis">{l.label}</span>} <span className="wiki-mono app-muted">{l.file}</span>
                {have.has(l.file) ? null : (
                  <>
                    {" "}
                    <span data-tone="danger" role="status">{t.missing}</span>{" "}
                    <Button size="sm" disabled={disabled} aria-label={t.createFile(l.file)} onClick={() => onChange(sortEntries([...files, { path: l.file, text: "", size: 0 }]))}>{t.create}</Button>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
        {unlinked.length === 0 ? null : (
          <p className="app-muted" data-testid="wiki-rule-unlinked">
            {t.unlinked}: {unlinked.map((f) => f.path).join(", ")}
          </p>
        )}
        {hasInstructions ? <p className="app-muted wiki-hint" data-testid="wiki-rule-instructions-note">{t.instructionsNote}</p> : null}
        {hasTemplates ? <p className="app-muted wiki-hint">{t.templateNote}</p> : null}
      </section>
      <MultiFileTab files={files} originFiles={originFiles} onChange={onChange} errors={errors ?? {}} {...(onDismissError === undefined ? {} : { onDismissError })} onSave={onSave} disabled={disabled} />
    </div>
  );
}
