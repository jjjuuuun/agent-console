import type { MemoryScopeRef, MemoryVersionSummary } from "@agent-console/contracts/memory";
import { TextDiff, type TextDiffMode } from "@agent-console/text-editor";
import { formatBytes, formatTimestamp, languageForContentType } from "./format";
import { formatMessage, messageOr, resolveMessages } from "./messages";
import { formatAuthor, sameScope, type FormatAuthorOptions } from "./scopes";

/** 본문이 바뀌지 않는 계약 동작(보관·보관 해제·옮김). 비교 영역은 diff 대신 바뀐 값을 글자로 보인다. */
export const DEFAULT_BODYLESS_OPS: readonly string[] = ["archive", "unarchive", "move"];
/** 지움 동작: 본문은 직전과 같고 비교는 "지움"이라고만 쓴다. */
export const DEFAULT_DELETE_OPS: readonly string[] = ["delete"];

export type VersionCompareTarget = "prev" | "current";

export interface MemoryVersionDiffProps {
  /** 보는 버전(요약). */
  version: MemoryVersionSummary | null;
  /** 비교 대상 버전(요약): 직전 또는 현재. 없으면(첫 버전·현재와 같음) 안내만. */
  base: MemoryVersionSummary | null;
  /** 두 버전의 본문(지연 로드). undefined = 아직 없음. */
  versionContent?: string;
  baseContent?: string;
  compare: VersionCompareTarget;
  onCompareChange: (next: VersionCompareTarget) => void;
  /** 비교 보기 방식. 제어형(사용자가 바꾸면 앱이 저장). */
  layout: TextDiffMode;
  onLayoutChange: (next: "split" | "unified") => void;
  /** 이 버전이 항목의 현재 버전이면 되돌리기가 꺼진다. */
  isCurrent: boolean;
  /** 되돌리기 요청(저장 안 된 변경 확인은 앱이 한다). 생략하면 단추가 없다. */
  onRestore?: (version: number) => void;
  loading?: boolean;
  error?: boolean;
  onRetry?: () => void;
  /** 범위 라벨 글(키·범위 변경 설명). */
  scopeText?: (scope: MemoryScopeRef) => string;
  contentType?: string | null;
  authorOptions?: FormatAuthorOptions;
  bodylessOps?: readonly string[];
  deleteOps?: readonly string[];
  /** 이 항목의 한 버전 목록 길이 안내 줄에 쓰는 보관 한도. 모르면 안내 줄이 없다. */
  maxVersions?: number | null;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/**
 * 버전 비교. [직전과 | 현재와] · [나란히 | 한 줄]. 본문은 text-editor의 `TextDiff`(@codemirror/merge)로 그린다.
 * 본문이 없는 동작(보관·옮김)은 diff 대신 "본문 변경 없음" + 바뀐 값을 글자로 쓴다.
 */
export function MemoryVersionDiff({
  version, base, versionContent, baseContent, compare, onCompareChange, layout, onLayoutChange, isCurrent, onRestore, loading = false, error = false, onRetry,
  scopeText, contentType, authorOptions, bodylessOps = DEFAULT_BODYLESS_OPS, deleteOps = DEFAULT_DELETE_OPS, maxVersions = null, messages: custom, className,
}: MemoryVersionDiffProps) {
  const m = resolveMessages(custom);
  const unified = layout === "unified";
  const scopeName = (s: MemoryScopeRef) => scopeText?.(s) ?? `${s.kind}:${s.id ?? ""}`;
  const radio = (id: string, label: string, checked: boolean, onChange: () => void, group: string) => (
    <button key={id} type="button" role="radio" aria-checked={checked} className="ac-mem-seg" data-active={checked ? "" : undefined} onClick={onChange} aria-label={`${group}: ${label}`}>{label}</button>
  );

  let body: React.ReactNode;
  if (!version) body = null;
  else if (error) {
    body = (
      <div className="ac-mem-errorblock" role="alert">
        <span>{m["history.error"]}</span>
        {onRetry ? <button type="button" className="ac-mem-btn" onClick={onRetry}>{m["history.retry"]}</button> : null}
      </div>
    );
  } else if (bodylessOps.includes(version.op) || deleteOps.includes(version.op)) {
    const lines: string[] = [];
    if (deleteOps.includes(version.op)) lines.push(m["history.deletedState"] as string);
    else {
      lines.push(m["history.noBodyChange"] as string);
      if (base && base.key !== version.key) lines.push(formatMessage(m["history.keyChanged"] as string, { from: base.key, to: version.key }));
      if (base && !sameScope(base.scope, version.scope)) lines.push(formatMessage(m["history.scopeChanged"] as string, { from: scopeName(base.scope), to: scopeName(version.scope) }));
      if (version.op === "archive") lines.push(m["history.archivedNow"] as string);
      if (version.op === "unarchive") lines.push(m["history.unarchivedNow"] as string);
    }
    body = <ul className="ac-mem-nobody">{lines.map((l, i) => <li key={i}>{l}</li>)}</ul>;
  } else if (!base) {
    body = <div className="ac-mem-empty">{m["history.noBase"]}</div>;
  } else if (loading || versionContent === undefined || baseContent === undefined) {
    body = <div className="ac-mem-spinner" role="status" aria-label={m["history.loading"]} />;
  } else {
    body = (
      <TextDiff before={baseContent} after={versionContent} language={languageForContentType(contentType)} mode={layout} unifiedBelow={900} showToolbar={false}
        onModeChange={onLayoutChange} height={320}
        ariaLabel={formatMessage(m["history.diffAria"] as string, { from: `v${base.version}`, to: `v${version.version}` })}
        messages={{ unchangedLines: m["history.unchangedLines"] as string, split: m["history.sideBySide"] as string, unified: m["history.unified"] as string, toolbar: m["history.layout"] as string }} />
    );
  }

  const author = version ? formatAuthor(version.author, authorOptions) : null;
  return (
    <div className={`ac-mem-root ac-mem-diff${className ? ` ${className}` : ""}`}>
      <div className="ac-mem-diff-toolbar">
        <div role="radiogroup" aria-label={m["history.compare"]} className="ac-mem-segs">
          {radio("prev", m["history.vsPrev"] as string, compare === "prev", () => onCompareChange("prev"), m["history.compare"] as string)}
          {radio("current", m["history.vsCurrent"] as string, compare === "current", () => onCompareChange("current"), m["history.compare"] as string)}
        </div>
        <div role="radiogroup" aria-label={m["history.layout"]} className="ac-mem-segs">
          {radio("split", m["history.sideBySide"] as string, !unified, () => onLayoutChange("split"), m["history.layout"] as string)}
          {radio("unified", m["history.unified"] as string, unified, () => onLayoutChange("unified"), m["history.layout"] as string)}
        </div>
      </div>
      <div className="ac-mem-diff-body">{body}</div>
      {version && author ? (
        <div className="ac-mem-diff-foot">
          <span className="ac-mem-muted">
            {m["history.thisVersion"]} v{version.version} · {messageOr(m, `history.op.${version.op}`, version.op)} · {author.text}{author.ruleId ? ` ${author.ruleId}` : ""} · {formatTimestamp(version.at)} · {formatBytes(version.bytes, m)} · <span className="ac-mem-mono" title={version.sha256}>{version.sha256.slice(0, 8)}</span>
          </span>
          {onRestore ? (
            <button type="button" className="ac-mem-btn" data-variant="primary" disabled={isCurrent} onClick={() => onRestore(version.version)} title={isCurrent ? (m["history.isCurrent"] as string) : undefined}>
              {isCurrent ? m["history.isCurrent"] : m["history.restore"]}
            </button>
          ) : null}
        </div>
      ) : null}
      {maxVersions !== null ? <p className="ac-mem-muted ac-mem-diff-note">{formatMessage(m["history.note"] as string, { max: maxVersions })}</p> : null}
    </div>
  );
}
