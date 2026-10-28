import { useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";
import { useLocation, useNavigate } from "react-router";
import type { RestClient } from "@agent-console/api-client";
import { useShortcuts, useToast } from "@agent-console/ui";
import { useWorkspaceSettings, useApiQuery } from "../../app/queries";
import { useDelayed } from "../../app/useDelayed";
import { useNow } from "../../app/useNow";
import { useMediaQuery } from "../../lib/useMediaQuery";
import { useRegisterCommands } from "../../shell/commands";
import { useEscapeLayer } from "../../shell/escapeStack";
import { activeRoute, routeServing, type RouteDef } from "../../shell/routeConfig";
import { useSetTitleSuffix } from "../../shell/titles";
import { ROUTE_ROLES } from "../library";
import { itemSpoken, indicatorAriaLabel, titleSuffixOf } from "./indicatorText";
import { resolveIndicatorSettings, resolvePlacement, splitFields } from "./indicatorSettings";
import { usageIndicatorMessages as t } from "./messages";
import { IndicatorMenu, type IndicatorMenuItem } from "./IndicatorMenu";
import { useIndicatorActions } from "./useIndicatorActions";
import { UsageIndicatorPopover } from "./UsageIndicatorPopover";
import { UsageIndicatorView, type IndicatorLayout, type IndicatorStatus } from "./UsageIndicatorView";
import {
  INDICATOR_HOVER_CLOSE_MS,
  INDICATOR_HOVER_OPEN_MS,
  INDICATOR_NARROW_MAX_ITEMS,
  INDICATOR_NARROW_QUERY,
  INDICATOR_NOW_MS,
  INDICATOR_SETTINGS_HASH,
  INDICATOR_PEEK_MS,
  INDICATOR_PEEK_SHORTCUT,
  INDICATOR_POPOVER_MAX,
  INDICATOR_SOURCES_STALE_MS,
  OFFICIAL_TRUST,
  USAGE_SETUP_HASH,
  USAGE_POLL_MS,
  USAGE_WINDOWS_KEY,
  INDICATOR_USAGE_PARTS,
  USAGE_SOURCES_KEY,
  type IndicatorHost,
} from "./usageConfig";
import { buildIndicatorItems, buildWindowGroups, sourceIndex, windowNameIndex, type IndicatorItem } from "./usageLib";
import "./usage-indicator.css";

const loadReport = (rest: RestClient) => rest.getUsage(INDICATOR_USAGE_PARTS);
const loadSources = (rest: RestClient) => rest.listUsageSources();
const NONE: readonly string[] = [];
const NO_LABELS: Readonly<Record<string, string>> = {};
/** 표시기의 두 조회는 백그라운드 갱신 실패를 토스트로 알리지 않는다(전역 `QueryCache.onError`가 이 meta를 본다). */
const SILENT_META = { silentBackgroundError: true } as const;

export interface UsageIndicatorProps {
  /** 라우트 설정 데이터(사용량 화면 경로를 `serves` 역할로 찾는다) */
  routes: readonly RouteDef[];
  /** 이 인스턴스가 꽂힌 자리. 설정의 배치가 가리키는 자리와 같을 때만 그린다 */
  host: IndicatorHost;
  /** 사이드바가 접혀(레일) 있는가 */
  collapsed?: boolean;
}

/**
 * 사용량 표시기 마운트 지점. 설정이 꺼져 있거나(`enabled=false`), 설정을 아직 못 읽었거나, 다른 자리 배치이거나,
 * 사용량 화면을 맡은 라우트가 없으면 **아무것도 마운트하지 않는다**(조회·단축키·제목 훅 없음).
 */
export function UsageIndicator({ routes, host, collapsed = false }: UsageIndicatorProps) {
  const settings = useWorkspaceSettings();
  if (settings.data === undefined) return null;
  const cfg = resolveIndicatorSettings(settings.data.value.ui?.usage_indicator);
  const { placement } = resolvePlacement(cfg.placement);
  if (!cfg.enabled || placement.host !== host) return null;
  const route = routeServing(routes, ROUTE_ROLES.usage);
  if (route === undefined) return null;
  return <ActiveIndicator routes={routes} usageRoute={route} cfg={cfg} layout={placement.layout === "chip" ? "chip" : collapsed ? "rail" : "block"} corner={placement.corner} host={host} />;
}

interface ActiveProps {
  routes: readonly RouteDef[];
  usageRoute: RouteDef;
  cfg: ReturnType<typeof resolveIndicatorSettings>;
  layout: IndicatorLayout;
  corner: string | undefined;
  host: IndicatorHost;
}

function ActiveIndicator({ routes, usageRoute, cfg, layout, corner, host }: ActiveProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const settings = useWorkspaceSettings();
  const report = useApiQuery(USAGE_WINDOWS_KEY, loadReport, { refetchInterval: USAGE_POLL_MS, meta: SILENT_META });
  const sources = useApiQuery(USAGE_SOURCES_KEY, loadSources, { staleTime: INDICATOR_SOURCES_STALE_MS, meta: SILENT_META });
  const nowMs = useNow(true, INDICATOR_NOW_MS);
  const nowSec = nowMs / 1000;
  const popId = useId();

  const usage = settings.data?.value.usage;
  const rawLabels = usage?.window_labels;
  const labels = useMemo(() => rawLabels ?? NO_LABELS, [rawLabels]);
  const rawOrder = usage?.primary_source_order;
  const order = useMemo(() => rawOrder ?? NONE, [rawOrder]);
  const staleAfter = usage?.stale_after_seconds ?? null;
  const index = useMemo(() => sourceIndex(sources.data ?? []), [sources.data]);
  const windowInfo = useMemo(() => windowNameIndex(sources.data ?? []), [sources.data]);
  const sourceInfo = useCallback(
    (id: string) => {
      const d = index.get(id)?.descriptor;
      return { title: d?.title ?? id, trust: d?.trust ?? "" };
    },
    [index],
  );
  const groups = useMemo(
    () => buildWindowGroups(report.data?.windows ?? [], order, (id) => index.get(id)?.descriptor.trust === OFFICIAL_TRUST),
    [report.data?.windows, order, index],
  );
  // 사이드바(펼침·레일)와 낭독에는 값이 있는 사용률 창만 쓴다(상태·토큰만 주는 창은 사용량 화면에서). 보일 창 수는 걸러낸 뒤에 적용한다.
  // 플로팅 칩은 설정한 창을 그대로 둔다.
  const items = useMemo(() => {
    if (layout === "chip") return buildIndicatorItems({ groups, labels, windowInfo, nowSec, staleAfterSeconds: staleAfter, colorRules: cfg.color_rules, windows: cfg.windows, maxItems: cfg.max_items });
    const ratio = buildIndicatorItems({ groups, labels, windowInfo, nowSec, staleAfterSeconds: staleAfter, colorRules: cfg.color_rules, windows: cfg.windows, maxItems: groups.length }).filter(
      (i) => i.observed && i.kind === "ratio",
    );
    return cfg.windows.length > 0 ? ratio : ratio.slice(0, cfg.max_items);
  }, [layout, groups, labels, windowInfo, nowSec, staleAfter, cfg.color_rules, cfg.windows, cfg.max_items]);
  const popItems = useMemo(
    () => buildIndicatorItems({ groups, labels, windowInfo, nowSec, staleAfterSeconds: staleAfter, colorRules: cfg.color_rules, windows: NONE, maxItems: groups.length }).filter((i) => i.observed && i.kind === "ratio").slice(0, INDICATOR_POPOVER_MAX),
    [groups, labels, windowInfo, nowSec, staleAfter, cfg.color_rules],
  );
  const { known: fields } = splitFields(cfg.fields);

  const hasData = report.data !== undefined;
  const slow = useDelayed(report.isPending);
  let status: IndicatorStatus = "ready";
  if (report.isPending) status = "loading";
  else if (report.data === undefined) status = "error-empty";
  else if (groups.length === 0 && cfg.windows.length === 0) status = "empty";
  else if (layout !== "chip" && items.length === 0) status = "empty";

  // ----- 요약 팝오버: 호버 300ms / 포커스 즉시 / 단축키 6초 고정
  const [hover, setHover] = useState(false);
  const [focus, setFocus] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [live, setLive] = useState("");
  const timers = useRef<{ open?: ReturnType<typeof setTimeout>; close?: ReturnType<typeof setTimeout>; pin?: ReturnType<typeof setTimeout> }>({});
  useEffect(() => {
    const t0 = timers.current;
    return () => {
      for (const h of [t0.open, t0.close, t0.pin]) if (h !== undefined) clearTimeout(h);
    };
  }, []);
  const open = hover || focus || pinned;
  useEscapeLayer(open, () => {
    setHover(false);
    setFocus(false);
    setPinned(false);
  });
  const onEnter = () => {
    clearTimeout(timers.current.close);
    timers.current.open = setTimeout(() => setHover(true), INDICATOR_HOVER_OPEN_MS);
  };
  const onLeave = () => {
    clearTimeout(timers.current.open);
    timers.current.close = setTimeout(() => setHover(false), INDICATOR_HOVER_CLOSE_MS);
  };

  const spoken = useMemo(() => items.map((i) => itemSpoken(i, cfg.value_mode, nowSec)).join(". "), [items, cfg.value_mode, nowSec]);
  const peek = useCallback(() => {
    setPinned(true);
    clearTimeout(timers.current.pin);
    timers.current.pin = setTimeout(() => setPinned(false), INDICATOR_PEEK_MS);
    setLive(t.peekLive(spoken === "" ? t.noData : spoken));
  }, [spoken]);
  // 켜져 있을 때만 단축키·명령이 등록된다(이 컴포넌트가 마운트된 동안). 기본 키는 표 데이터, 설정 `ui.keybindings`가 덮어쓴다.
  useShortcuts([{ ...INDICATOR_PEEK_SHORTCUT, scope: "global", modifierRequired: true, run: peek }]);
  useRegisterCommands([{ id: INDICATOR_PEEK_SHORTCUT.id, titleKey: "palette.actions.usagePeek", run: peek }]);

  // 임계 통과 알림: 아래에서 위로 넘어가는 순간에만(첫 로드와 같은 규칙에서의 반복은 낭독하지 않는다)
  const prevRules = useRef<Map<string, number> | null>(null);
  useEffect(() => {
    if (!hasData) return;
    const next = new Map<string, number>();
    for (const i of items) if (i.kind === "ratio") next.set(i.window, i.rule?.at ?? -1);
    const prev = prevRules.current;
    prevRules.current = next;
    if (prev === null) return;
    for (const i of items) {
      const before = prev.get(i.window);
      if (i.rule !== undefined && before !== undefined && before < i.rule.at) {
        setLive(t.rulePassed(i.name, Math.round(i.rule.at * 100)));
        break;
      }
    }
  }, [items, hasData]);

  // ----- 컨텍스트 메뉴: 우클릭 / Shift+F10 / ContextMenu 키
  const toast = useToast();
  const narrow = useMediaQuery(INDICATOR_NARROW_QUERY);
  const actions = useIndicatorActions({ lastFetchedAt: Math.max(report.dataUpdatedAt, sources.dataUpdatedAt) });
  const settingsRoute = routeServing(routes, ROUTE_ROLES.settings);
  const [menuAt, setMenuAt] = useState<{ x: number; y: number } | null>(null);
  const linkRef = useRef<HTMLElement | null>(null);
  const openMenu = (point: { x: number; y: number }) => {
    clearTimeout(timers.current.open);
    setHover(false);
    setPinned(false);
    setMenuAt(point);
  };
  const onContextMenu = (e: MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    linkRef.current = e.currentTarget;
    openMenu({ x: e.clientX, y: e.clientY });
  };
  const onLinkKeyDown = (e: KeyboardEvent<HTMLAnchorElement>) => {
    if (!(e.key === "ContextMenu" || (e.key === "F10" && e.shiftKey))) return;
    e.preventDefault();
    linkRef.current = e.currentTarget;
    const r = e.currentTarget.getBoundingClientRect();
    openMenu({ x: r.left, y: r.bottom });
  };
  const closeMenu = (restoreFocus: boolean) => {
    setMenuAt(null);
    if (restoreFocus) linkRef.current?.focus();
  };

  const current = activeRoute(location.pathname, routes)?.id === usageRoute.id;
  // 구독 연결 안내가 필요한 출처가 켜져 있으면, 보일 사용률이 없을 때 미니가 연결 안내(#setup)로 이어 준다
  const needsSetup = (sources.data ?? []).some((s) => s.enabled !== false && s.descriptor.needs_setup === true);
  const setupHref = needsSetup && !cfg.hide_when_empty ? `${usageRoute.path}${USAGE_SETUP_HASH}` : undefined;
  const onActivate = (e: MouseEvent<HTMLAnchorElement>) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    const target = e.currentTarget.getAttribute("href") ?? usageRoute.path;
    if (current && !target.includes("#")) document.getElementById("app-main")?.focus();
    else void navigate(target);
  };

  const menuItems: IndicatorMenuItem[] = [
    { id: "open", label: t.menu.open, onSelect: () => (current ? document.getElementById("app-main")?.focus() : void navigate(usageRoute.path)) },
    {
      id: "refresh",
      label: t.menu.refresh,
      onSelect: () => setLive(actions.refresh() ? t.menu.refreshing : t.menu.refreshTooSoon),
    },
    ...(settingsRoute === undefined ? [] : [{ id: "settings", label: t.menu.settings, onSelect: () => void navigate(`${settingsRoute.path}${INDICATOR_SETTINGS_HASH}`) }]),
    {
      id: "hide",
      label: t.menu.hide,
      onSelect: () => {
        actions.hide().then(
          () => toast({ tone: "info", text: t.menu.hidden }),
          () => toast({ tone: "danger", text: t.menu.hideFailed }),
        );
      },
    },
  ];

  const emptyText = (sources.data ?? [])
    .filter((s) => s.enabled !== false && s.descriptor.description)
    .map((s) => s.descriptor.description as string)
    .join(" ");

  const extra: string[] = [];
  if (status === "loading") extra.push(t.loading);
  if (status === "error-empty") extra.push(t.loadFailed);
  if (status === "empty") extra.push(setupHref === undefined ? t.noDataHint : t.unlinkedHint);
  if (report.isError && hasData) extra.push(t.loadFailed);
  const ariaLabel = status === "ready" ? indicatorAriaLabel(items, cfg.value_mode, nowSec, extra) : `${t.summary(extra.join(". "))}. ${t.openLabel}`;

  if (cfg.hide_when_empty && status === "empty") return null;
  if (status === "loading" && !slow) return null;

  return (
    <>
      {cfg.also_in_title ? <TitleSuffix item={items[0]} mode={cfg.value_mode} /> : null}
      <UsageIndicatorView
        items={items}
        fields={fields}
        valueMode={cfg.value_mode}
        layout={layout}
        status={status}
        hasError={report.isError && hasData}
        nowMs={nowMs}
        href={usageRoute.path}
        {...(setupHref === undefined ? {} : { setupHref })}
        current={current}
        ariaLabel={ariaLabel}
        sourceInfo={sourceInfo}
        onActivate={onActivate}
        host={host}
        {...(narrow ? { maxChipItems: INDICATOR_NARROW_MAX_ITEMS } : {})}
        {...(corner === undefined ? {} : { corner })}
        linkProps={{
          onMouseEnter: onEnter,
          onMouseLeave: onLeave,
          onFocus: () => setFocus(true),
          onBlur: () => setFocus(false),
          onContextMenu,
          onKeyDown: onLinkKeyDown,
          "aria-haspopup": "menu",
          ...(open ? { "aria-describedby": popId } : {}),
        }}
      >
        <span className="ac-sr-only" role="status" aria-live="polite">{live}</span>
        {menuAt !== null ? <IndicatorMenu label={t.menu.label} items={menuItems} point={menuAt} onClose={closeMenu} /> : null}
        {open ? (
          <UsageIndicatorPopover
            id={popId}
            items={popItems}
            valueMode={cfg.value_mode}
            nowMs={nowMs}
            emptyText={emptyText === "" ? undefined : `${t.noDataHint}. ${emptyText}`}
            side={layout === "chip" ? "up" : "right"}
          />
        ) : null}
      </UsageIndicatorView>
    </>
  );
}

/** 문서 제목 끝에 첫 항목을 붙인다(`also_in_title`일 때만 마운트). */
function TitleSuffix({ item, mode }: { item: IndicatorItem | undefined; mode: string }) {
  useSetTitleSuffix(titleSuffixOf(item, mode));
  return null;
}
