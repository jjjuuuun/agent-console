import { useMemo } from "react";
import type { UsageSourceInfo, UsageWindowSnapshot } from "@agent-console/contracts";
import { usageIndicatorMessages as t } from "./messages";
import { splitFields, type ResolvedIndicatorSettings } from "./indicatorSettings";
import { indicatorAriaLabel } from "./indicatorText";
import { UsageIndicatorView, type IndicatorLayout } from "./UsageIndicatorView";
import { OFFICIAL_TRUST } from "./usageConfig";
import { buildIndicatorItems, buildWindowGroups, pickColorRule, remainingPercent, sourceIndex, usedPercent, windowNameIndex, type IndicatorItem } from "./usageLib";

export interface UsageIndicatorPreviewProps {
  /** 설정 초안(기본값이 채워진 것) */
  settings: ResolvedIndicatorSettings;
  /** 실제 관측값(없거나 비면 "예시 값"으로 그린다. 예시는 이 미리보기 안에서만 존재한다) */
  windows: readonly UsageWindowSnapshot[];
  sources: readonly UsageSourceInfo[];
  labels?: Readonly<Record<string, string>>;
  primaryOrder?: readonly string[];
  staleAfterSeconds?: number | null;
  nowMs: number;
  href: string;
}

const SAMPLE_RATIOS = [0.63, 0.2];

function sampleItems(settings: ResolvedIndicatorSettings): IndicatorItem[] {
  return t.settings.sampleNames.slice(0, Math.max(1, settings.max_items)).map((name, i) => {
    const ratio = SAMPLE_RATIOS[i] ?? 0.5;
    const rule = pickColorRule(settings.color_rules, ratio);
    return { window: `sample-${i}`, name, kind: "ratio", observed: true, ratio, used: usedPercent(ratio), remaining: remainingPercent(ratio), overLimit: false, reset: "unknown", stale: false, ...(rule ? { rule } : {}) };
  });
}

/** 설정 화면 미리보기: 같은 `UsageIndicatorView`를 펼침·레일 두 모양으로 그린다. 링크는 이동하지 않는다. */
export function UsageIndicatorPreview({ settings, windows, sources, labels = {}, primaryOrder = [], staleAfterSeconds = null, nowMs, href }: UsageIndicatorPreviewProps) {
  const index = useMemo(() => sourceIndex(sources), [sources]);
  const windowInfo = useMemo(() => windowNameIndex(sources), [sources]);
  const real = useMemo(() => {
    const groups = buildWindowGroups(windows, primaryOrder, (id) => index.get(id)?.descriptor.trust === OFFICIAL_TRUST);
    return groups.length === 0 ? null : buildIndicatorItems({ groups, windows: settings.windows, maxItems: settings.max_items, labels, windowInfo, nowSec: nowMs / 1000, staleAfterSeconds, colorRules: settings.color_rules });
  }, [windows, primaryOrder, index, windowInfo, settings.windows, settings.max_items, settings.color_rules, labels, nowMs, staleAfterSeconds]);
  const items = real ?? sampleItems(settings);
  const { known } = splitFields(settings.fields);
  const sourceInfo = (id: string) => ({ title: index.get(id)?.descriptor.title ?? id, trust: index.get(id)?.descriptor.trust ?? "" });
  const render = (layout: IndicatorLayout, title: string) => (
    <figure className="usage-ind-preview-cell">
      <figcaption className="app-muted">{title}</figcaption>
      <div className="usage-ind-preview-frame" data-layout={layout}>
        <UsageIndicatorView
          items={items}
          fields={known}
          valueMode={settings.value_mode}
          layout={layout}
          status="ready"
          nowMs={nowMs}
          href={href}
          ariaLabel={indicatorAriaLabel(items, settings.value_mode, nowMs / 1000)}
          sourceInfo={sourceInfo}
          onActivate={(e) => e.preventDefault()}
          example={real === null}
        />
      </div>
    </figure>
  );
  return (
    <div className="usage-ind-preview" aria-label={t.settings.preview} role="group">
      {render("block", t.settings.previewExpanded)}
      {render("rail", t.settings.previewRail)}
    </div>
  );
}
