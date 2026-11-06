/**
 * 뼈대 파일 탭(screen-sdd §11.1): 문서 목록과 파일의 연결 상태(파일 없음 + [만들기] / 문서에 연결되지 않음) + 파일 트리·편집기(`MultiFileTab`).
 * 초안(`files`)은 부모가 갖고 저장도 부모가 한다. 서버·틀 id를 모른다.
 */
import { Button } from "@agent-console/ui";
import type { SpecDocument } from "@agent-console/contracts/sdd";
import { MultiFileTab, sortEntries, type FileEntry } from "../resources";
import { templateMessages as t } from "./templateMessages";

export interface TemplateFilesPanelProps {
  documents: readonly SpecDocument[];
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

export function TemplateFilesPanel({ documents, files, originFiles, onChange, errors, onDismissError, onSave, disabled }: TemplateFilesPanelProps) {
  const have = new Set(files.map((f) => f.path));
  const linked = new Set(documents.map((d) => d.file));
  const unlinked = files.filter((f) => !linked.has(f.path));
  return (
    <div className="sdd-template-files">
      <section aria-label={t.files.links}>
        <h3 className="sdd-label">{t.files.links}</h3>
        {documents.length === 0 ? (
          <p className="app-muted">{t.files.noDocuments}</p>
        ) : (
          <ul className="sdd-template-links">
            {documents.map((d) => (
              <li key={d.id} data-missing={have.has(d.file) ? undefined : "true"}>
                <span className="ac-ellipsis">{d.title}</span> <span className="sdd-mono app-muted">{d.file}</span>
                {have.has(d.file) ? null : (
                  <>
                    {" "}
                    <span data-tone="danger" role="status">{t.files.missing}</span>{" "}
                    <Button size="sm" disabled={disabled} aria-label={t.files.createFile(d.file)} onClick={() => onChange(sortEntries([...files, { path: d.file, text: "", size: 0 }]))}>{t.files.create}</Button>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
        {unlinked.length === 0 ? null : (
          <p className="app-muted" data-testid="sdd-template-unlinked">
            {t.files.unlinked}: {unlinked.map((f) => f.path).join(", ")}
          </p>
        )}
      </section>
      <MultiFileTab files={files} originFiles={originFiles} onChange={onChange} errors={errors ?? {}} {...(onDismissError === undefined ? {} : { onDismissError })} onSave={onSave} disabled={disabled} />
    </div>
  );
}
