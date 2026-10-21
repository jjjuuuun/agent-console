import { useMemo, useState, type CSSProperties } from "react";
import { Avatar } from "../shared/Avatar";
import { ChatIcon } from "../shared/Icon";
import { fill, mergeMessages, showDuration } from "../shared/util";
import { defaultChatMessages, type ChatMessages } from "./messages";
import { currentStepLabel, flattenSteps, visibleSteps } from "./progressLogic";
import type { ProgressChild, ProgressStep } from "./types";

export interface ProgressStripProps {
  steps: readonly ProgressStep[];
  /** 접힘 여부(제어형). 접히면 요약 한 줄. 단계가 8개를 넘으면 최근 3개 + "외 N단계". 세는 단위는 후손까지 편 전체 목록이다. */
  collapsed: boolean;
  onToggle: () => void;
  /** 요약 문구. 없으면 messages.progressSummary(+소요·"지금: …")로 만든다. */
  summary?: string;
  onOpen?: (step: ProgressStep) => void;
  /** 자식 실행 행의 `external-link` 아이콘 링크 클릭. 링크(`child.href`)는 그대로 열리고, 이 콜백이 있으면 기본 이동 대신 호출한다. */
  onOpenChild?: (child: ProgressChild, step: ProgressStep) => void;
  /** 펼친 칩의 키 목록(제어형). 생략하면 내부 상태(기본 접힘)로 사용자가 바꾼 것을 유지한다. */
  expandedStepKeys?: readonly string[];
  onStepToggle?: (key: string, expanded: boolean) => void;
  /** 단계가 이 값을 넘으면 접힘에서 최근 `recentWhenLong`개만 본다. */
  longThreshold?: number;
  recentWhenLong?: number;
  /** 한 단계 들여 쓰기 폭 계산에 쓰는 최대 단계(기본 4). 이보다 깊은 단계는 같은 위치에 그린다. */
  maxIndent?: number;
  messages?: Partial<ChatMessages>;
}

const isRunning = (status: string) => status === "running";

/**
 * 진행 정보: 한 줄 요약(기본) + 펼치면 트리 목록(ux-overhaul §7.4). 방식 라벨·이름·배지는 전부 props 문자열이다.
 * 모든 행이 같은 규칙(`depth × --ac-progress-indent`)으로 들여 쓰고, 칩 윤곽선은 쓰지 않는다. 소요 시간은 1초 이상일 때만 그린다.
 */
export function ProgressStrip({ steps, collapsed, onToggle, summary, onOpen, onOpenChild, expandedStepKeys, onStepToggle, longThreshold = 8, recentWhenLong = 3, maxIndent = 4, messages }: ProgressStripProps) {
  const m = mergeMessages(defaultChatMessages, messages);
  const [own, setOwn] = useState<ReadonlySet<string>>(new Set());
  const expanded = useMemo<ReadonlySet<string>>(() => (expandedStepKeys ? new Set(expandedStepKeys) : own), [expandedStepKeys, own]);
  const flat = useMemo(() => flattenSteps(steps), [steps]);
  if (flat.length === 0) return null;
  const toggleStep = (key: string, open: boolean) => {
    if (!expandedStepKeys) {
      setOwn((prev) => {
        const next = new Set(prev);
        if (open) next.add(key);
        else next.delete(key);
        return next;
      });
    }
    onStepToggle?.(key, open);
  };
  const totalMs = flat.reduce((a, f) => a + (f.step.durationMs ?? 0), 0);
  const total = showDuration(totalMs, m.units);
  const runningStep = [...flat].reverse().find((f) => isRunning(f.step.status))?.step;
  const nowText = runningStep ? fill(m.progressNow, { name: `${runningStep.toLabel} ${runningStep.statusLabel ?? m.stepStatus[runningStep.status] ?? runningStep.status}` }) : undefined;
  const base = total ? fill(m.progressSummaryDuration, { n: flat.length, duration: total }) : fill(m.progressSummary, { n: flat.length });
  const text = summary ?? (nowText ? `${base} · ${nowText}` : base);
  const long = flat.length > longThreshold;
  const currentRow = runningStep ? flat.filter((f) => f.step.key === runningStep.key) : [];
  const shown = collapsed ? (long ? flat.slice(-recentWhenLong) : currentRow) : visibleSteps(flat, expanded);
  const hiddenCount = collapsed && long ? flat.length - shown.length : 0;
  return (
    <div role="group" aria-label={m.progressLabel} className="ac-chat-progress">
      <button type="button" className="ac-chat-progress-summary" aria-expanded={!collapsed} onClick={onToggle}>
        <ChatIcon name={collapsed ? "chevron-right" : "chevron-down"} size={12} />
        <span className="ac-ellipsis">{text}</span>
      </button>
      {hiddenCount > 0 || shown.length > 0 ? (
        <ul className="ac-chat-tree">
          {hiddenCount > 0 ? <li className="ac-chat-muted">{fill(m.moreSteps, { n: hiddenCount })}</li> : null}
          {shown.map(({ step, indent }) => {
            const statusText = step.statusLabel ?? m.stepStatus[step.status] ?? step.status;
            const dur = step.status === "succeeded" || step.status === "completed" ? showDuration(step.durationMs, m.units) : null;
            const clickable = !!onOpen || !!step.href;
            const hasKids = !!step.children?.length;
            const open = expanded.has(step.key);
            const name = step.solo ? step.toLabel : `${step.fromLabel} ${step.toLabel}`;
            const kidsText = hasKids && !open ? currentStepLabel(step, isRunning) : undefined;
            const progressText = step.child?.progress ? fill(m.childProgress, step.child.progress) : undefined;
            const warn = step.tone === "warning";
            const content = (
              <>
                <span className="ac-status-icon" data-status={step.status} data-size="14" aria-hidden="true" />
                {warn ? <span aria-hidden="true">▲</span> : null}
                {warn ? <span className="ac-sr-only">{m.stepWarning}</span> : null}
                {step.solo ? null : (
                  <>
                    {step.fromAvatar ? <Avatar agentId={step.fromAvatar.id} name={step.fromAvatar.name} size={16} avatar={step.fromAvatar} /> : null}
                    <span className="ac-ellipsis">{step.fromLabel}</span>
                    <span aria-hidden="true" className="ac-chat-edge" data-dashed={step.methodDashed ? "true" : undefined} />
                    <span className="ac-chat-muted">{step.methodLabel}</span>
                    <span aria-hidden="true">→</span>
                  </>
                )}
                {step.toAvatar ? <Avatar agentId={step.toAvatar.id} name={step.toAvatar.name} size={16} avatar={step.toAvatar} /> : null}
                <span className="ac-ellipsis">{step.toLabel}</span>
                {step.iterationLabel ? <span className="ac-chat-muted" data-part="iteration">{step.iterationLabel}</span> : null}
                {step.callLabel ? <span className="ac-chat-muted" data-part="call">{step.callLabel}</span> : null}
                <span className="ac-chat-muted">
                  {statusText}
                  {dur ? ` ${dur}` : ""}
                  {progressText ? ` · ${progressText}` : ""}
                  {kidsText ? ` · ${fill(m.childCurrent, { name: kidsText })}` : ""}
                </span>
                {step.badge ? (
                  <span className="ac-badge" data-part="badge">
                    {step.badge}
                  </span>
                ) : null}
              </>
            );
            const tip = step.hint ?? (indent > 0 && !step.badge && !step.child ? m.sameSession : undefined);
            const main = hasKids ? (
              <button type="button" className="ac-chat-row-main" aria-expanded={open} aria-label={fill(m.childToggle, { name })} title={tip} onClick={() => toggleStep(step.key, !open)}>
                <ChatIcon name={open ? "chevron-down" : "chevron-right"} size={12} />
                {content}
              </button>
            ) : clickable ? (
              step.href ? (
                <a href={step.href} className="ac-chat-row-main" title={tip} onClick={onOpen ? (e) => { e.preventDefault(); onOpen(step); } : undefined}>
                  {content}
                </a>
              ) : (
                <button type="button" className="ac-chat-row-main" title={tip} onClick={() => onOpen?.(step)}>
                  {content}
                </button>
              )
            ) : (
              <span className="ac-chat-row-main" title={tip}>
                {content}
              </span>
            );
            const child = step.child;
            const rowStyle = { "--ac-depth": Math.min(indent, maxIndent) } as CSSProperties;
            return (
              <li key={step.key} className="ac-chat-row" data-step={step.key} data-indent={indent} data-tone={warn ? "warning" : undefined} style={rowStyle}>
                {main}
                {child ? (
                  <a
                    href={child.href}
                    className="ac-chat-row-link"
                    data-part="child-link"
                    aria-label={fill(m.childOpen, { name: child.nodeLabel })}
                    title={m.childOpenTip}
                    onClick={onOpenChild ? (e) => { e.preventDefault(); onOpenChild(child, step); } : undefined}
                  >
                    <ChatIcon name="external-link" />
                  </a>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
