import { memo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import type { GraphEditorMessages } from "../messages";
import { defaultMessages, format } from "../messages";
import type { PortView } from "../logic/ports";
import { SIDE_GLYPH } from "../logic/layout";
import type { Side } from "../shapes/types";
import type { BindSummary, NodeRunBadge, NodeStateView, PortHandleRenderer } from "../types";
import { ResourceChips } from "./ResourceChips";
import type { ResourceChip } from "../logic/team";

export interface NodeCardProps {
  label: string;
  typeTitle: string;
  /** 분류색 막대 색(CSS 값). 호출자가 hints/카테고리 해시로 정한다 */
  accent: string;
  /** 아바타 텍스트(1~2자). 호출자가 hints/제목 첫 글자로 정한다 */
  iconText: string;
  /** 아바타 배경색(CSS 값). 없으면 `accent`. 막대 색(분류)과 따로 정할 때 쓴다 */
  avatarColor?: string;
  inputs: readonly PortView[];
  outputs: readonly PortView[];
  state?: NodeStateView;
  issueCount?: { error: number; warning: number };
  selected?: boolean;
  width?: number;
  /** 디스크립터를 찾지 못한 노드(tokens 4.5) */
  unknownType?: string;
  portsLoading?: boolean;
  portsFailed?: boolean;
  /** 포트 행 안에 핸들을 꽂는 슬롯(편집기가 React Flow Handle을 넘김). 단독 사용 시 생략 */
  renderPortHandle?: PortHandleRenderer;
  messages?: GraphEditorMessages;
  /** 칩 카드(compact): 헤더 한 줄 + 가장자리 핸들(포트 행 없음, 실행 상태 영역 없음). 디스크립터가 정한다 */
  compact?: boolean;
  /** 상황 배지 문구(입구·답변·묻기 등, 호출자가 messages로 만든 문자열) 최대 3개 + `+N` */
  badges?: readonly string[];
  /** 선언형 칩(디스크립터 `ui_hints.chips`) 문구 */
  hintChips?: readonly string[];
  /** 리소스 칩 줄(리소스 보기를 껐을 때) */
  resourceChips?: readonly ResourceChip[];
  onResourceChipsClick?: () => void;
  /** "응답 대기 12초" 같은 한 줄(호출자가 만든 문자열) */
  waitingText?: string;
  /** `auto`: 연결된 포트·호버·선택·포커스일 때만 포트 라벨을 보인다 */
  portLabels?: "auto" | "always";
  /** 점선 외곽(디스크립터 `ui_hints.dashed`) */
  dashed?: boolean;
  /** 겹친 카드 모양(디스크립터 `ui_hints.shape`). 뒤에 같은 크기 사각형 두 장이 어긋나 보인다 */
  stacked?: boolean;
  /** 정의를 바인딩한 노드의 요약(부제·본문 한 줄·배지·[열기]) */
  bind?: BindSummary;
  /** 실행 상세용 회차·호출 배지 */
  runBadge?: NodeRunBadge;
  /** 반복 영역 윤곽(연결을 선택·포커스하는 동안) */
  loopRegion?: boolean;
  /** 노드 가장자리 띠 슬롯(편집기가 React Flow Handle을 넘김, 선택된 노드에서만). 단독 사용 시 생략 */
  edgeBands?: ReactNode;
}

/** 노드 접근성 이름: "노드 {label}, 타입 {typeTitle}, 상태 {라벨}, 검증 오류 {n}건". */
export function nodeAriaLabel(
  p: Pick<NodeCardProps, "label" | "typeTitle" | "state" | "issueCount" | "bind" | "runBadge">,
  m: GraphEditorMessages = defaultMessages,
): string {
  const status = p.state === undefined ? "" : `, 상태 ${statusLabel(p.state.status, m)}`;
  const ic = p.issueCount;
  const errors = ic !== undefined && ic.error + ic.warning > 0 ? `, ${issueAriaText(ic, m)}` : "";
  // 정의 바인딩: ", {부제} {이름}, {본문}, {배지들}"(버전 고정 등은 배지 전문)
  const bind =
    p.bind === undefined
      ? ""
      : `, ${format(m.bindAria, { subtitle: p.bind.subtitle ?? "", title: p.bind.title }).trim()}` +
        (p.bind.meta ? `, ${p.bind.meta}` : "") +
        (p.bind.missing ? `, ${m.bindMissing}` : "") +
        (p.bind.badges ?? []).map((b) => `, ${b.fullTitle ?? b.title}`).join("");
  const run = p.runBadge === undefined ? "" : `, ${p.runBadge.ariaLabel}`;
  return format(m.nodeAria, { label: p.label, typeTitle: p.typeTitle, status }) + bind + run + errors;
}

/** 이슈 배지 접근성 이름: "검증 오류 N건, 경고 M건"(0인 쪽은 생략). */
export function issueAriaText(c: { error: number; warning: number }, m: GraphEditorMessages): string {
  if (c.error > 0 && c.warning > 0) return format(m.issueAria, { error: c.error, warning: c.warning });
  if (c.error > 0) return format(m.issueAriaErrorOnly, { error: c.error });
  return format(m.issueAriaWarningOnly, { warning: c.warning });
}

export function statusLabel(status: string, m: GraphEditorMessages): string {
  return m.statusLabels[status] ?? status;
}

const sideOfPort = (p: PortView, io: "in" | "out"): Side => p.side ?? (io === "in" ? "left" : "right");
const portKey = (io: "in" | "out", p: PortView): string => `${io}:${p.id}`;

interface HotProps {
  hot: string | null;
  setHot: (key: string | null) => void;
}

function PortRow({ port, side, render, m, hot, setHot }: { port: PortView; side: "in" | "out"; render?: PortHandleRenderer; m: GraphEditorMessages } & HotProps) {
  const placed = port.offset !== undefined;
  const key = portKey(side, port);
  const title = port.missing ? `${port.label} — ${m.portMissing}` : port.schemaSummary ? `${port.label} (${port.schemaSummary})` : port.label;
  return (
    <div
      className={`ac-ge-port ac-ge-port--${side}`}
      data-port={port.id}
      data-missing={port.missing ? "true" : undefined}
      data-connected={port.connected ? "true" : undefined}
      data-placed={placed ? "true" : undefined}
      data-hot={placed && hot === key ? "true" : undefined}
      onMouseEnter={placed ? () => setHot(key) : undefined}
      onMouseLeave={placed ? () => setHot(null) : undefined}
      title={title}
    >
      {!placed && render?.(port, side)}
      <span className="ac-ge-port-label ac-ellipsis">{port.label}</span>
      {placed && (
        <span className="ac-ge-port-glyph" aria-hidden="true">
          {SIDE_GLYPH[sideOfPort(port, side)]}
        </span>
      )}
    </div>
  );
}

/**
 * 노드 하나의 모양. React Flow에 의존하지 않는 순수 표현 컴포넌트.
 * 모든 표시 값은 props(디스크립터·노드 데이터 유래)이며 타입별 분기가 없다.
 * 상태는 `data-status`만 단다(색·테두리·아이콘은 tokens.css 규칙).
 */
export const NodeCard = memo(function NodeCard(props: NodeCardProps) {
  const m = props.messages ?? defaultMessages;
  const { state, unknownType } = props;
  const [hot, setHot] = useState<string | null>(null);
  const hotProps: HotProps = { hot, setHot };
  // 기본 배치(포트 행 옆)가 아닌 핸들은 층으로 옮겨 그린다: 좌·우 면은 포트 영역 층, 위·아래 면은 노드 층.
  const placedAll = [
    ...props.inputs.map((p) => ({ io: "in" as const, p })),
    ...props.outputs.map((p) => ({ io: "out" as const, p })),
  ].filter((a) => a.p.offset !== undefined);
  const isEdgeSide = (s: Side) => s === "top" || s === "bottom";
  const edgeLayer = placedAll.filter((a) => isEdgeSide(sideOfPort(a.p, a.io)));
  const portsLayer = placedAll.filter((a) => !isEdgeSide(sideOfPort(a.p, a.io)));
  const slot = (a: { io: "in" | "out"; p: PortView }) => {
    const side = sideOfPort(a.p, a.io);
    const key = portKey(a.io, a.p);
    const style: CSSProperties = isEdgeSide(side) ? { left: a.p.offset } : { top: a.p.offset };
    return (
      <span
        key={key}
        className={`ac-ge-handle-slot ac-ge-handle-slot--${side}`}
        style={style}
        data-hot={hot === key ? "true" : undefined}
        data-connected={a.p.connected ? "true" : undefined}
        onMouseEnter={() => setHot(key)}
        onMouseLeave={() => setHot(null)}
      >
        {props.renderPortHandle?.(a.p, a.io)}
        {isEdgeSide(side) && (
          <span className="ac-ge-port-chip ac-ellipsis" aria-hidden="true">
            {a.p.label}
          </span>
        )}
      </span>
    );
  };
  const rows = Math.max(props.inputs.length, props.outputs.length);
  const style = { "--ac-ge-accent": props.accent, width: props.width } as CSSProperties;
  const showAttempt = state?.attempt !== undefined && state.attempt > 1;
  const badges = props.badges ?? [];
  const shownBadges = badges.slice(0, 3);
  const hiddenBadges = badges.length - shownBadges.length;
  /** 칩 카드의 좌·우 면 핸들(위·아래 면은 노드 층). 기본 구성에서는 입력이 왼쪽·출력이 오른쪽 */
  const chipHandles = (side: "left" | "right") => [
    ...props.inputs.filter((p) => sideOfPort(p, "in") === side && p.offset === undefined).map((p) => <span key={`i:${p.id}`}>{props.renderPortHandle?.(p, "in")}</span>),
    ...props.outputs.filter((p) => sideOfPort(p, "out") === side && p.offset === undefined).map((p) => <span key={`o:${p.id}`}>{props.renderPortHandle?.(p, "out")}</span>),
  ];
  return (
    <div
      className="ac-ge-node ac-status-box ac-text"
      style={style}
      data-selected={props.selected ? "true" : undefined}
      data-unknown-type={unknownType !== undefined ? "true" : undefined}
      data-status={state?.status}
      data-compact={props.compact ? "true" : undefined}
      data-dashed={props.dashed ? "true" : undefined}
      data-stacked={props.stacked ? "true" : undefined}
      data-loop-region={props.loopRegion ? "true" : undefined}
      data-missing={props.bind?.missing ? "true" : undefined}
      data-labels={props.portLabels ?? "auto"}
    >
      <span className="ac-ge-node-bar ac-status-keep" aria-hidden="true" />
      {props.edgeBands}
      <div className="ac-ge-node-header ac-status-header">
        <span className="ac-ge-avatar" aria-hidden="true" style={props.avatarColor !== undefined ? ({ "--ac-ge-avatar": props.avatarColor } as CSSProperties) : undefined}>
          {props.iconText}
        </span>
        <div className="ac-ge-node-titles">
          <div className="ac-ge-node-label ac-clamp-2" title={props.label}>
            {props.label}
          </div>
          <div
            className={unknownType !== undefined ? "ac-ge-node-type ac-ellipsis ac-mono-wrap" : "ac-ge-node-type ac-ellipsis"}
            title={unknownType !== undefined ? format(m.unknownType, { type: unknownType }) : (props.bind?.subtitle ?? props.typeTitle)}
          >
            {unknownType !== undefined ? format(m.unknownType, { type: unknownType }) : (props.bind?.subtitle ?? props.typeTitle)}
          </div>
        </div>
        {shownBadges.length > 0 && (
          <span className="ac-ge-badges">
            {shownBadges.map((b, i) => (
              <span key={`${b}:${i}`} className="ac-ge-badge">
                {b}
              </span>
            ))}
            {hiddenBadges > 0 && (
              <span className="ac-ge-badge" title={badges.slice(3).join(", ")}>
                +{hiddenBadges}
              </span>
            )}
          </span>
        )}
        {props.runBadge !== undefined &&
          (props.runBadge.onClick !== undefined ? (
            <button
              type="button"
              className="ac-ge-run-badge nodrag nopan"
              data-picked={props.runBadge.picked ? "true" : undefined}
              aria-label={props.runBadge.ariaLabel}
              title={props.runBadge.ariaLabel}
              onClick={(e) => {
                e.stopPropagation();
                props.runBadge?.onClick?.();
              }}
            >
              {props.runBadge.text}
            </button>
          ) : (
            <span className="ac-ge-run-badge" data-picked={props.runBadge.picked ? "true" : undefined} role="img" aria-label={props.runBadge.ariaLabel} title={props.runBadge.ariaLabel}>
              {props.runBadge.text}
            </span>
          ))}
        {showAttempt && (
          <span className="ac-ge-attempt" title={`attempt ${state.attempt}`}>
            {format(m.attemptBadge, { n: state.attempt as number })}
          </span>
        )}
        {state !== undefined && (
          <span className="ac-ge-status" data-status={state.status} title={statusLabel(state.status, m)}>
            <span className="ac-status-icon" aria-hidden="true" />
            <span className="ac-ge-status-label ac-ellipsis">{statusLabel(state.status, m)}</span>
          </span>
        )}
        {props.issueCount !== undefined && props.issueCount.error + props.issueCount.warning > 0 && (
          <span className="ac-ge-issues" role="img" aria-label={issueAriaText(props.issueCount, m)} title={issueAriaText(props.issueCount, m)}>
            {props.issueCount.error > 0 && (
              <span className="ac-ge-issue" data-severity="error">
                <span aria-hidden="true">✕</span>
                <span aria-hidden="true">{props.issueCount.error}</span>
              </span>
            )}
            {props.issueCount.warning > 0 && (
              <span className="ac-ge-issue" data-severity="warning">
                <span aria-hidden="true">▲</span>
                <span aria-hidden="true">{props.issueCount.warning}</span>
              </span>
            )}
          </span>
        )}
      </div>
      {props.bind !== undefined && (props.bind.meta || (props.bind.badges?.length ?? 0) > 0) && (
        <div className="ac-ge-bind">
          {props.bind.meta && (
            <div className="ac-ge-bind-meta ac-ellipsis" title={props.bind.meta}>
              {props.bind.meta}
            </div>
          )}
          {(props.bind.badges?.length ?? 0) > 0 && (
            <div className="ac-ge-bind-badges">
              {props.bind.badges?.map((b) => (
                <span key={b.key} className="ac-ge-hint-chip" data-tone={b.tone ?? "neutral"} data-dashed={b.dashed ? "true" : undefined} title={b.fullTitle ?? b.title}>
                  {b.title}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
      {props.compact && (
        <>
          <span className="ac-ge-chip-handles ac-ge-chip-handles--in">{chipHandles("left")}</span>
          <span className="ac-ge-chip-handles ac-ge-chip-handles--out">{chipHandles("right")}</span>
        </>
      )}
      {props.waitingText !== undefined && (
        <div className="ac-ge-waiting ac-ellipsis" role="status" title={props.waitingText}>
          {props.waitingText}
        </div>
      )}
      {(props.portsLoading || props.portsFailed) && (
        <div className="ac-ge-port-note ac-ellipsis" role="status" data-failed={props.portsFailed ? "true" : undefined}>
          {props.portsFailed ? m.portsFailed : m.portsLoading}
        </div>
      )}
      {!props.compact && rows > 0 && (
        <div className="ac-ge-ports">
          {Array.from({ length: rows }, (_, i) => (
            <div className="ac-ge-port-row" key={i}>
              {props.inputs[i] !== undefined ? <PortRow port={props.inputs[i] as PortView} side="in" render={props.renderPortHandle} m={m} {...hotProps} /> : <span />}
              {props.outputs[i] !== undefined ? <PortRow port={props.outputs[i] as PortView} side="out" render={props.renderPortHandle} m={m} {...hotProps} /> : <span />}
            </div>
          ))}
          {portsLayer.length > 0 && <div className="ac-ge-handle-layer ac-ge-handle-layer--ports">{portsLayer.map(slot)}</div>}
        </div>
      )}
      {edgeLayer.length > 0 && <div className="ac-ge-handle-layer ac-ge-handle-layer--edges">{edgeLayer.map(slot)}</div>}
      {props.hintChips !== undefined && props.hintChips.length > 0 && (
        <div className="ac-ge-hint-chips">
          {props.hintChips.map((c) => (
            <span key={c} className="ac-ge-hint-chip">
              {c}
            </span>
          ))}
        </div>
      )}
      {props.resourceChips !== undefined && props.resourceChips.length > 0 && (
        <ResourceChips chips={props.resourceChips} {...(props.onResourceChipsClick !== undefined ? { onClick: props.onResourceChipsClick } : {})} messages={m} />
      )}
      {state !== undefined && (state.errorSummary !== undefined || state.summary !== undefined) && (
        <div className="ac-ge-summary ac-ellipsis" title={state.errorSummary ?? state.summary}>
          {state.errorSummary ?? state.summary}
        </div>
      )}
      {props.bind?.open !== undefined && (
        <div className="ac-ge-bind-actions">
          <button
            type="button"
            className="ac-ge-btn ac-ge-bind-open nodrag nopan"
            aria-disabled={props.bind.open.disabledReason !== undefined ? "true" : undefined}
            title={props.bind.open.disabledReason ?? props.bind.open.label}
            onClick={(e) => {
              e.stopPropagation();
              if (props.bind?.open?.disabledReason === undefined) props.bind?.open?.onOpen();
            }}
          >
            {props.bind.open.label} <span aria-hidden="true">↗</span>
          </button>
        </div>
      )}
    </div>
  );
});
