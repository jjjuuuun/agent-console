import { useEffect, useMemo, useRef, useState } from "react";
import type { UsageSetupSnippet } from "@agent-console/contracts";
import { Markdown } from "@agent-console/chat";
import { Button, Disclosure, Icon, Tabs } from "@agent-console/ui";
import { formatRelative } from "../../lib/format";
import { usageMessages as t } from "./messages";
import { groupSetupSnippets } from "./usageLib";

/** 연결 상태: 받은 값이 있다 / 다른 출처 값은 있으나 이 출처는 없다 / 값이 전혀 없다 */
export type SetupGuideState = "connected" | "missing" | "empty";

export interface UsageSetupGuideProps {
  /** 출처 디스크립터의 연결 조각(서버가 경로를 이미 채워 준다) */
  snippets: readonly UsageSetupSnippet[];
  /** 출처 설명(마크다운). 없으면 생략 */
  help?: string | null | undefined;
  /** 패널 안에 함께 보일 한 줄 안내(예전 상단 배너) */
  note?: string | undefined;
  state: SetupGuideState;
  /** 출처에서 마지막으로 값을 받은 시각(epoch 초) */
  lastReceivedAt?: number | null | undefined;
  nowMs: number;
  open: boolean;
  onOpenChange(open: boolean): void;
  onRecheck(): void;
  rechecking?: boolean;
  /** 복사 구현 주입(기본: 클립보드 API). 실패하면 reject */
  copyText?(text: string): Promise<void>;
  /** 복사됨 표시 유지 시간(ms) */
  copiedMs?: number;
}

const defaultCopy = (text: string): Promise<void> =>
  navigator.clipboard?.writeText ? navigator.clipboard.writeText(text) : Promise.reject(new Error("clipboard unavailable"));

function SnippetBody({ items, copyText, copiedMs }: { items: readonly UsageSetupSnippet[]; copyText: (text: string) => Promise<void>; copiedMs: number }) {
  const [shell, setShell] = useState(items[0]?.shell ?? "");
  const [status, setStatus] = useState<"idle" | "copied" | "failed">("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  const shells = useMemo(() => [...new Set(items.map((i) => i.shell))].filter((s) => s !== ""), [items]);
  const current = items.find((i) => i.shell === shell) ?? items[0];
  if (current === undefined) return null;
  const copy = () => {
    clearTimeout(timer.current);
    copyText(current.text).then(
      () => setStatus("copied"),
      () => setStatus("failed"),
    ).finally(() => {
      timer.current = setTimeout(() => setStatus("idle"), copiedMs);
    });
  };
  return (
    <div className="usage-snippet">
      <div className="usage-snippet-bar">
        {shells.length > 1 ? (
          <label className="usage-snippet-shell">
            <span className="app-muted">{t.setup.shell}</span>
            <select value={current.shell} onChange={(e) => setShell(e.target.value)}>
              {shells.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
        ) : <span />}
        <Button size="sm" onClick={copy}>
          <Icon name={status === "copied" ? "check" : "copy"} size={14} /> {status === "copied" ? t.setup.copied : t.setup.copy}
        </Button>
      </div>
      <pre className="usage-snippet-code app-mono" tabIndex={0} aria-label={t.setup.codeLabel(current.title)} data-language={current.language || undefined}><code>{current.text}</code></pre>
      <span className="app-muted" role="status" aria-live="polite">{status === "failed" ? t.setup.copyFailed : ""}</span>
    </div>
  );
}

/**
 * 출처 연결 안내 패널(복사 가능한 조각). 조각·설명은 모두 서버 데이터이고 이 컴포넌트는 출처 id를 모른다.
 * 열림은 호출자가 정한다(값이 없으면 펼치고 값이 생기면 접는 규칙은 컨테이너 몫).
 */
export function UsageSetupGuide({ snippets, help, note, state, lastReceivedAt, nowMs, open, onOpenChange, onRecheck, rechecking = false, copyText = defaultCopy, copiedMs = 2000 }: UsageSetupGuideProps) {
  const groups = useMemo(() => groupSetupSnippets(snippets), [snippets]);
  const received = lastReceivedAt != null ? t.setup.lastReceived(formatRelative(lastReceivedAt, nowMs)) : t.setup.neverReceived;
  const summaryText = state === "connected" ? t.setup.summaryConnected(lastReceivedAt != null ? formatRelative(lastReceivedAt, nowMs) : "–") : state === "empty" ? t.setup.summaryEmpty : t.setup.summaryMissing;
  return (
    <section className="usage-guide" aria-label={t.setup.region} data-state={state}>
      <Disclosure
        open={open}
        onOpenChange={onOpenChange}
        summary={<span className="usage-guide-summary"><span>{summaryText}</span> <span className="app-muted">{t.setup.toggle}</span></span>}
      >
        <div className="usage-guide-body">
          {help ? <Markdown text={help} /> : null}
          {note ? <p className="app-muted usage-guide-note">{note}</p> : null}
          {groups.length > 0 ? (
            <Tabs
              ariaLabel={t.setup.tabsLabel}
              tabs={groups.map((g) => ({ id: g.title, label: g.title, content: <SnippetBody items={g.items} copyText={copyText} copiedMs={copiedMs} /> }))}
            />
          ) : null}
          <div className="usage-guide-foot">
            <span className="app-muted">{received}</span>
            <Button size="sm" loading={rechecking} onClick={onRecheck}>{rechecking ? t.setup.rechecking : t.setup.recheck}</Button>
          </div>
        </div>
      </Disclosure>
    </section>
  );
}
