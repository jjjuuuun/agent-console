import { useState, type ReactNode } from "react";
import type { ExportFile, Issue } from "@agent-console/contracts";
import { useLanguageCode } from "../../i18n";
import { Badge, FileTree, type FileTreeItem } from "@agent-console/ui";
import { formatBytes } from "../../lib/bytes";
import { useIssueMessage } from "../../app/appMessages";
import { ACTION_LOOKS, summarizeFiles } from "./exportLogic";
import { useExportMessages } from "./messages";

const TONES = { success: "success", warning: "warning", danger: "danger" } as const;

/** 동작 배지: 아이콘 + 텍스트(색 단독 금지). 모르는 값은 원문 + 중립. */
export function ActionBadge({ action }: { action: string | undefined }) {
  const t = useExportMessages();
  const value = action ?? "create";
  const look = Object.hasOwn(ACTION_LOOKS, value) ? ACTION_LOOKS[value] : undefined;
  const label = Object.hasOwn(t.preview.byAction, value) ? t.preview.byAction[value] : value;
  const tone = look === undefined || look.tone === "neutral" ? undefined : TONES[look.tone];
  return (
    <Badge {...(tone === undefined ? {} : { tone })} data-action={value}>
      <span aria-hidden="true">{look?.icon ?? "·"}</span> {label}
    </Badge>
  );
}

/** "파일 n개 · 합계 s · 새로 만듦 a · …" 요약 줄. 모르는 동작도 원문 이름으로 센다. */
export function PlanSummaryLine({ files }: { files: readonly ExportFile[] }) {
  const t = useExportMessages();
  const s = summarizeFiles(files);
  const known = Object.keys(t.preview.byAction);
  const actions = [...known.filter((k) => (s.byAction[k] ?? 0) > 0), ...Object.keys(s.byAction).filter((k) => !known.includes(k))];
  return (
    <p className="exp-summary ac-num" role="status">
      {t.preview.summary(s.count, formatBytes(s.bytes))}
      {actions.map((k) => ` · ${Object.hasOwn(t.preview.byAction, k) ? t.preview.byAction[k] : k} ${s.byAction[k]}`).join("")}
    </p>
  );
}

/** 파일 목록(트리/평면 전환). 행 = 경로 + 크기 + 미디어 타입 + 동작 배지. */
export function FilesView({ files, ariaLabel }: { files: readonly ExportFile[]; ariaLabel?: string }) {
  const languageCode = useLanguageCode();
  const t = useExportMessages();
  const label = ariaLabel ?? t.preview.files;
  const [view, setView] = useState<"tree" | "flat">("tree");
  const items: FileTreeItem[] = files.map((f) => ({
    path: f.path,
    trailing: (
      <>
        <span className="ac-num">{formatBytes(f.size)}</span>
        {f.media_type ? <span className="app-muted exp-media">{f.media_type}</span> : null}
        <ActionBadge action={f.action} />
      </>
    ),
  }));
  return (
    <div className="exp-files">
      <div role="group" aria-label={t.preview.viewLabel} className="exp-view-toggle">
        {(["tree", "flat"] as const).map((v) => (
          <button key={v} type="button" className="ac-btn" data-size="sm" data-variant={view === v ? "primary" : "secondary"} aria-pressed={view === v} onClick={() => setView(v)}>
            <span className="ac-btn-label">{v === "tree" ? t.preview.treeView : t.preview.flatView}</span>
          </button>
        ))}
      </div>
      <FileTree items={items} ariaLabel={label} view={view} locale={languageCode} />
    </div>
  );
}

const SEVERITY_ICON: Record<string, string> = { error: "✕", warning: "⚠", info: "ℹ" };

/** 서버 이슈 목록: 메시지는 가공하지 않고, 코드는 mono 보조. 심각도는 아이콘 + 텍스트. */
export function IssueRows({ issues, ariaLabel }: { issues: readonly Issue[]; ariaLabel: string }): ReactNode {
  const issueMessage = useIssueMessage();
  const t = useExportMessages();
  if (issues.length === 0) return null;
  return (
    <ul className="exp-issues" aria-label={ariaLabel}>
      {issues.map((issue, i) => (
        <li key={i} data-severity={issue.severity}>
          <span className="exp-sev">
            <span aria-hidden="true">{SEVERITY_ICON[issue.severity] ?? "·"}</span> {t.severity[issue.severity] ?? issue.severity}
          </span>{" "}
          <span className="app-wrap">{issueMessage(issue)}</span> <span className="lib-mono app-muted">{issue.code}</span>
        </li>
      ))}
    </ul>
  );
}
