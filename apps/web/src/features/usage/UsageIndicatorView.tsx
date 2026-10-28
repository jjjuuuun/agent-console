import { useLayoutEffect, useRef, useState, type CSSProperties, type MouseEvent, type ReactNode } from "react";
import { Gauge } from "@agent-console/ui";
import { itemFlags, itemRailValue, itemValueText } from "./indicatorText";
import { usageIndicatorMessages as t, usageMessages as u } from "./messages";
import { APPROX_TRUST, INDICATOR_FIELD as F, INDICATOR_TONES } from "./usageConfig";
import { formatResetClock } from "./resetDisplay";
import { indicatorFill, type IndicatorItem } from "./usageLib";

export type IndicatorLayout = "block" | "rail" | "chip";
export type IndicatorStatus = "loading" | "ready" | "empty" | "error-empty";

export interface UsageIndicatorViewProps {
  items: readonly IndicatorItem[];
  /** 보일 요소와 순서(알려진 값만 그려진다) */
  fields: readonly string[];
  /** 값 방향(`remaining` | `used`) */
  valueMode: string;
  layout: IndicatorLayout;
  status: IndicatorStatus;
  /** 이전 데이터를 보이는 중에 조회가 실패했는가 */
  hasError?: boolean;
  /** 지금(ms, 주입) */
  nowMs: number;
  href: string;
  /** 지금 이동할 화면에 이미 있는가 */
  current?: boolean;
  /** 링크 `aria-label`(앱이 만들어 넘긴다) */
  ariaLabel: string;
  /** 출처 id → 표시 정보(신뢰 요소용) */
  sourceInfo?: (id: string) => { title: string; trust: string };
  onActivate?: (e: MouseEvent<HTMLAnchorElement>) => void;
  /** 링크에 달 추가 속성(호버·포커스 핸들러, aria-describedby 등) */
  linkProps?: Record<string, unknown>;
  /** 링크 밖(형제)에 놓일 것: 팝오버, 라이브 영역 */
  children?: ReactNode;
  /** 가운데 데이터 속성: 호스트 이름 */
  host?: string;
  /** 플로팅 모서리 이름(스타일 훅) */
  corner?: string;
  /** 칩 배치에서 보일 최대 항목 수(좁은 화면 등). 넘친 항목은 `+N`. 폭이 모자라도 뒤 항목부터 `+N`으로 접힌다 */
  maxChipItems?: number;
  /** 미리보기에서 "예시" 칩을 붙일지 */
  example?: boolean;
  /** 주면, 보일 사용률이 하나도 없을 때 "사용률 미연결" 한 줄(별도 링크 글자 없이 줄 전체가 링크)을 그리고 링크가 이 주소(연결 안내 앵커)로 간다 */
  setupHref?: string;
}

function ToneMark({ item }: { item: IndicatorItem }) {
  const tone = item.rule === undefined ? undefined : INDICATOR_TONES[item.rule.tone];
  return tone === undefined || tone.glyph === "" ? null : <span className="usage-ind-tone" aria-hidden="true">{tone.glyph}</span>;
}

function toneStyle(item: IndicatorItem): CSSProperties | undefined {
  const tone = item.rule === undefined ? undefined : INDICATOR_TONES[item.rule.tone];
  return tone === undefined ? undefined : ({ "--ac-gauge-fill": `var(${tone.cssVar})`, "--usage-ind-tone": `var(${tone.cssVar})` } as CSSProperties);
}

type SourceInfo = UsageIndicatorViewProps["sourceInfo"];

/** 추정·비공식 출처의 값인가(퍼센트 앞 `~`, 막대 끝 점선). 등급 어휘는 데이터(`APPROX_TRUST`). */
function isApprox(item: IndicatorItem, sourceInfo: SourceInfo): boolean {
  const src = item.source !== undefined && sourceInfo !== undefined ? sourceInfo(item.source) : undefined;
  return src !== undefined && APPROX_TRUST.includes(src.trust);
}

/** 값이 없는 창의 사유(툴팁용): 상태 글자·토큰 수 등 출처가 준 사실. */
function noRatioReason(item: IndicatorItem, mode: string): string {
  if (!item.observed) return t.notObserved;
  if (item.kind === "status") return itemValueText(item, mode);
  if (item.kind === "tokens") return `${t.tokensDetail}, ${itemValueText(item, mode)}`;
  return u.cards.noValue;
}

function itemTitle(item: IndicatorItem, mode: string, approx = false): string {
  if (item.kind !== "ratio") return t.noRatioTitle(item.name, noRatioReason(item, mode));
  return [`${item.name} ${itemValueText(item, mode)}`, ...(approx ? [t.approxNote] : []), ...itemFlags(item)].join(" · ");
}

/** 미니 값 글자: 사용률만 `42%`(추정이면 `~42%`). 그 밖의 종류는 `–`. 상태·토큰 글자는 그리지 않는다. */
function miniValue(item: IndicatorItem, mode: string, approx: boolean): string {
  return item.kind === "ratio" ? `${approx ? "~" : ""}${itemRailValue(item, mode)}` : u.common.none;
}

/**
 * 사이드바 한 항목(사용자 요청 10/28): 제목·`N% 사용됨` 한 줄, 막대 한 줄, 초기화 시각 한 줄만.
 * 상태·신뢰·관측 시각·토큰 같은 부가 정보는 그리지 않는다(상세는 사용량 화면). `fields` 설정은 칩 모양에만 적용된다.
 */
function ItemBlock({ item, mode, nowMs, sourceInfo }: { item: IndicatorItem; mode: string; nowMs: number; sourceInfo: SourceInfo }) {
  const nowSec = nowMs / 1000;
  const fill = indicatorFill(item, mode);
  const dim = item.stale || item.reset === "passed";
  const reset =
    item.reset === "passed"
      ? t.resetsPassed
      : item.reset === "future" && item.resetsAt != null
        ? formatResetClock(item.resetsAt, nowSec, { today: t.resetsClockToday, other: t.resetsClockOther })
        : null;
  return (
    <div className="usage-ind-item usage-ind-simple" data-stale={dim ? "true" : undefined} data-tone={item.rule?.tone} style={toneStyle(item)} title={itemTitle(item, mode, isApprox(item, sourceInfo))}>
      <div className="usage-ind-head">
        <span className="usage-ind-label ac-ellipsis">{item.name}</span>
        <span className="usage-ind-value ac-num">
          {itemValueText(item, mode)}
          <ToneMark item={item} />
        </span>
      </div>
      <div className="usage-ind-bar" aria-hidden="true">
        <Gauge {...(fill === undefined ? {} : { value: fill })} stale={dim} label={item.name} noValueLabel="" />
      </div>
      {reset === null ? null : <div className="usage-ind-sub">{reset}</div>}
    </div>
  );
}

/** 접힘 레일 타일: 값 숫자 + 4px 막대. 이름은 툴팁(`title`)과 링크 `aria-label`이 맡는다. */
function ItemRail({ item, mode, sourceInfo }: { item: IndicatorItem; mode: string; sourceInfo: SourceInfo }) {
  const fill = indicatorFill(item, mode);
  const toneGlyph = item.rule !== undefined && (item.rule.tone === "warning" || item.rule.tone === "danger") ? (INDICATOR_TONES[item.rule.tone]?.glyph ?? "") : "";
  const mark = item.stale ? "⚠" : item.reset === "passed" || item.overLimit ? "▲" : toneGlyph;
  return (
    <div className="usage-ind-item usage-ind-rail-item" data-stale={item.stale || item.reset === "passed" ? "true" : undefined} style={toneStyle(item)} title={itemTitle(item, mode, isApprox(item, sourceInfo))}>
      <span className="usage-ind-rail-value ac-num">{itemRailValue(item, mode)}{mark === "" ? null : <span className="usage-ind-rail-mark" aria-hidden="true">{mark}</span>}</span>
      <div aria-hidden="true"><Gauge {...(fill === undefined ? {} : { value: fill })} stale={item.stale} label={item.name} noValueLabel="" /></div>
    </div>
  );
}

function ItemChip({ item, fields, mode }: { item: IndicatorItem; fields: readonly string[]; mode: string }) {
  const fill = indicatorFill(item, mode);
  return (
    <span className="usage-ind-chip-item" data-stale={item.stale ? "true" : undefined} style={toneStyle(item)} title={itemTitle(item, mode)}>
      {fields.includes(F.label) ? <span className="usage-ind-label ac-ellipsis">{item.name}</span> : null}
      {fields.includes(F.value) ? <span className="usage-ind-value ac-num" data-empty={item.kind !== "ratio" ? "true" : undefined}>{miniValue(item, mode, false)}<ToneMark item={item} /></span> : null}
      {fields.includes(F.gauge) ? <span className="usage-ind-chip-gauge" aria-hidden="true"><Gauge {...(fill === undefined ? {} : { value: fill })} label={item.name} noValueLabel="" /></span> : null}
    </span>
  );
}

/**
 * 칩 본문: 항목을 가로로 놓고, 한도(`maxItems`)나 폭(링크 `scrollWidth`)을 넘으면 뒤 항목부터 `+N`으로 접는다(툴팁에 나머지).
 * 폭 판정은 링크의 `overflow` 측정이라 레이아웃이 없는 환경(테스트)에서는 한도만 적용된다.
 */
function ChipBody({ items, fields, mode, maxItems }: { items: readonly IndicatorItem[]; fields: readonly string[]; mode: string; maxItems: number | undefined }) {
  const cap = Math.max(1, Math.min(maxItems ?? items.length, items.length));
  const key = `${cap}|${items.map((i) => i.window).join(",")}|${fields.join(",")}`;
  const [fit, setFit] = useState<{ key: string; n: number }>({ key, n: cap });
  const shown = fit.key === key ? Math.min(fit.n, cap) : cap;
  const probe = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    const link = probe.current?.parentElement;
    if (link && shown > 1 && link.scrollWidth > link.clientWidth + 1) setFit({ key, n: shown - 1 });
  }, [key, shown]);
  const rest = items.slice(shown);
  return (
    <>
      <span ref={probe} hidden />
      {items.slice(0, shown).map((i) => <ItemChip key={i.window} item={i} fields={fields} mode={mode} />)}
      {rest.length > 0 ? <span className="usage-ind-chip-more" aria-hidden="true" data-more={rest.length} title={rest.map((i) => itemTitle(i, mode)).join("\n")}>{t.chipMore(rest.length)}</span> : null}
    </>
  );
}

/**
 * 사용량 표시기(표현 전용). 데이터 조회·라우터·단축키를 모른다: 항목 목록과 모양만 props로 받는다.
 * 링크 하나(탭 정지 1개)이며 값은 `aria-label`로 읽히고 게이지는 `aria-hidden`이다.
 */
export function UsageIndicatorView(p: UsageIndicatorViewProps) {
  let body: ReactNode;
  const unlinked = p.layout === "block" && (p.status === "ready" || p.status === "empty") && p.setupHref !== undefined && !p.items.some((i) => i.kind === "ratio");
  // 접힘 레일에는 값이 있는 창만 그린다(빈 타일 금지). 보일 것이 없으면 아무것도 그리지 않는다.
  const railItems = p.layout === "rail" ? p.items.filter((i) => i.observed && i.kind === "ratio") : p.items;
  if (p.layout === "rail" && (p.status === "loading" || p.status === "empty" || (p.status === "ready" && railItems.length === 0))) return null;
  // 사이드바(펼침·레일)는 보일 내용이 있을 때만 그린다: 로딩 중(스켈레톤 상자가 빈 상자로 남던 결함)과
  // 보일 사용률도 연결 안내도 없을 때는 컨테이너(배경·테두리·여백)를 남기지 않는다. 칩은 기존대로.
  if (p.layout === "block" && !unlinked && (p.status === "loading" || p.status === "empty" || (p.status === "ready" && !p.items.some((i) => i.observed && i.kind === "ratio")))) return null;
  if (p.status === "loading") {
    body = <div className="usage-ind-skeleton app-skeleton-row" aria-hidden="true" />;
  } else if (p.status === "error-empty") {
    body = <div className="usage-ind-msg"><span aria-hidden="true">! </span>{p.layout === "rail" ? "" : t.loadFailed}</div>;
  } else if (unlinked) {
    body = (
      <div className="usage-ind-msg" title={t.unlinkedHint}>{t.unlinked}</div>
    );
  } else if (p.status === "empty") {
    body = <div className="usage-ind-msg">{p.layout === "rail" ? u.common.none : t.noData}</div>;
  } else if (p.layout === "rail") {
    body = railItems.map((i) => <ItemRail key={i.window} item={i} mode={p.valueMode} sourceInfo={p.sourceInfo} />);
  } else if (p.layout === "chip") {
    body = <ChipBody items={p.items} fields={p.fields} mode={p.valueMode} maxItems={p.maxChipItems} />;
  } else {
    const rows = p.items.filter((i) => i.observed && i.kind === "ratio");
    body = rows.length === 0 ? <div className="usage-ind-msg">{t.noData}</div> : rows.map((i) => <ItemBlock key={i.window} item={i} mode={p.valueMode} nowMs={p.nowMs} sourceInfo={p.sourceInfo} />);
  }
  return (
    <div className="usage-ind" data-layout={p.layout} data-host={p.host} data-corner={p.corner} data-status={p.status} data-error={p.hasError ? "true" : undefined}>
      <a
        className="usage-ind-link"
        href={unlinked && p.setupHref !== undefined ? p.setupHref : p.href}
        aria-label={p.ariaLabel}
        aria-busy={p.status === "loading" ? "true" : undefined}
        {...(p.current ? { "aria-current": "page" as const } : {})}
        onClick={p.onActivate}
        {...p.linkProps}
      >
        {body}
        {p.hasError ? <span className="usage-ind-err" aria-hidden="true" title={t.loadFailed}>!</span> : null}
        {p.example ? <span className="usage-ind-example">{t.example}</span> : null}
      </a>
      {p.children}
    </div>
  );
}
