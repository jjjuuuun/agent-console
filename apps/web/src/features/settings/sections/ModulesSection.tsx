import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Link } from "react-router";
import type { ModuleInfo } from "@agent-console/contracts";
import { Banner, Button, EmptyState, Icon } from "@agent-console/ui";
import { lookupMessage, messages as m } from "../../../app/messages";
import { ModuleStatusChip, moduleAffects, MODULE_STATUS, moduleStatusLabel, useLinkPartDefs, useModules, type ModulesState } from "../../../modules";
import { DEFAULT_ROUTES } from "../../../shell/routeConfig";
import { CopyButton } from "../CopyButton";
import { countModules, FILTER_STATUSES, groupModules, moduleCommandSnippet, showsReasonCollapsed, type StatusFilter } from "../modulesView";
import { ModuleOptionsPanel } from "./ModuleOptionsPanel";
import { Skeleton } from "../Skeleton";

const t = m.modules;
const FLASH_MS = 1500;

export interface ScreenRef {
  title: string;
  path: string;
  requires: readonly string[];
}
export interface PartRef {
  id: string;
  requires: readonly string[];
}

export interface ModulesSectionViewProps {
  state: ModulesState;
  refetching: boolean;
  onRefresh: () => void;
  /** 모듈이 켜 주는 화면 목록(영향받는 화면 계산용) */
  screens: readonly ScreenRef[];
  /** 연동 부분 목록(영향받는 부분 계산용) */
  parts: readonly PartRef[];
  /** 펼친 모듈 행에 모듈 옵션(읽기 전용)을 그리는 함수. 없으면 옵션 줄이 없다(데이터 연결은 컨테이너 몫) */
  renderOptions?: (mod: ModuleInfo) => ReactNode;
}

const kindLabel = (kind: string) => (m.moduleKind as Record<string, string>)[kind] ?? kind;

function summaryRoles(roles: readonly string[]): string {
  if (roles.length === 0) return "";
  return roles.length <= 2 ? roles.join(", ") : `${roles.slice(0, 2).join(", ")} 외 ${roles.length - 2}`;
}

/** 한 줄 설명: 계약에 설명 필드가 없어 제공 연결, 없으면 화면 역할로 만든다(둘 다 서버가 준 값). */
function describeModule(mod: ModuleInfo): string {
  const provides = mod.provides ?? [];
  const roles = mod.web_roles ?? [];
  if (provides.length > 0) return t.summaryProvides(summaryRoles(provides));
  if (roles.length > 0) return t.summaryRoles(summaryRoles(roles));
  return "";
}

function Detail({ mod, screens, parts, renderOptions }: { mod: ModuleInfo; screens: readonly ScreenRef[]; parts: readonly PartRef[]; renderOptions?: ((mod: ModuleInfo) => ReactNode) | undefined }) {
  const affectedScreens = screens.filter((s) => s.requires.length > 0 && moduleAffects(mod, s.requires));
  const affectedParts = parts.filter((p) => p.requires.length > 0 && moduleAffects(mod, p.requires));
  const contracts = Object.entries(mod.contracts ?? {});
  const provides = mod.provides ?? [];
  const roles = mod.web_roles ?? [];
  const active = mod.status === MODULE_STATUS.active;
  return (
    <dl className="app-mod-detail">
      {mod.reason ? (
        <>
          <dt>{t.detail.reason}</dt>
          <dd className="app-wrap">{mod.reason}</dd>
        </>
      ) : null}
      <dt>{t.detail.version}</dt>
      <dd>{mod.version}</dd>
      {contracts.length > 0 ? (
        <>
          <dt>{t.detail.contracts}</dt>
          <dd className="app-tags">
            {contracts.map(([name, version]) => (
              <span key={name} className="ac-tag">{`${name} ${version}`}</span>
            ))}
          </dd>
        </>
      ) : null}
      {provides.length > 0 ? (
        <>
          <dt>{t.detail.provides}</dt>
          <dd className="app-tags">
            {provides.map((p) => (
              <code key={p} className="ac-tag">{p}</code>
            ))}
          </dd>
        </>
      ) : null}
      {roles.length > 0 ? (
        <>
          <dt>{t.detail.roles}</dt>
          <dd className="app-wrap">{roles.join(", ")}</dd>
        </>
      ) : null}
      {affectedScreens.length > 0 ? (
        <>
          <dt>{t.detail.screens}</dt>
          <dd className="app-wrap">
            {affectedScreens.map((s, i) => (
              <span key={s.path}>
                {i > 0 ? ", " : ""}
                {active ? <Link to={s.path}>{s.title}</Link> : s.title}
              </span>
            ))}
          </dd>
        </>
      ) : null}
      {affectedParts.length > 0 ? (
        <>
          <dt>{t.detail.parts}</dt>
          <dd className="app-wrap">{affectedParts.map((p) => (m.linkPart.names as Record<string, string>)[p.id] ?? p.id).join(", ")}</dd>
        </>
      ) : null}
      <dt>{active ? t.cmd.disableTitle : t.cmd.enableTitle}</dt>
      <dd>
        <pre className="app-mod-cmd">{moduleCommandSnippet(mod)}</pre>
        <CopyButton text={moduleCommandSnippet(mod)} label={t.cmd.copy} copiedLabel={t.cmd.copied} />
      </dd>
      {renderOptions === undefined ? null : (
        <>
          <dt>{t.options.title}</dt>
          <dd>{renderOptions(mod)}</dd>
        </>
      )}
    </dl>
  );
}

/**
 * 설정의 "기능 모듈" 섹션(읽기 전용): 서버에 설치된 기능과 연동의 상태·이유를 보인다.
 * 켜고 끄는 스위치는 없다(설치자가 설정 파일로 한다). 데이터와 콜백은 props로 받는 표현 컴포넌트다.
 */
export function ModulesSectionView({ state, refetching, onRefresh, screens, parts, renderOptions }: ModulesSectionViewProps) {
  const modules = useMemo(() => (state.phase === "ready" ? state.modules : []), [state]);
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [text, setText] = useState("");
  const [openRows, setOpenRows] = useState<ReadonlySet<string>>(new Set());
  const [closedGroups, setClosedGroups] = useState<ReadonlySet<string>>(new Set());
  const [focusKey, setFocusKey] = useState<string | undefined>(undefined);
  const [flash, setFlash] = useState<ReadonlySet<string>>(new Set());
  const searchRef = useRef<HTMLInputElement>(null);
  const treeRef = useRef<HTMLUListElement>(null);
  const prevStatus = useRef<Map<string, string> | null>(null);

  const counts = useMemo(() => countModules(modules), [modules]);
  const groups = useMemo(() => groupModules(modules, filter, text), [modules, filter, text]);

  // 상태가 바뀐 행은 잠깐 강조한다(처음 받은 목록은 강조하지 않는다)
  useEffect(() => {
    const next = new Map(modules.map((x) => [x.id, x.status]));
    const prev = prevStatus.current;
    prevStatus.current = next;
    if (prev === null || state.phase !== "ready") return;
    const changed = new Set([...next].filter(([id, status]) => prev.get(id) !== status).map(([id]) => id));
    if (changed.size === 0 || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    setFlash(changed);
    const h = setTimeout(() => setFlash(new Set()), FLASH_MS);
    return () => clearTimeout(h);
  }, [modules, state.phase]);

  // 화면에 보이는 항목의 순서(화살표 이동용): 그룹 머리 -> (펼친 그룹이면) 그 그룹의 행들
  const navKeys = useMemo(() => groups.flatMap((g) => [`g:${g.kind}`, ...(closedGroups.has(g.kind) ? [] : g.modules.map((x) => `m:${x.id}`))]), [groups, closedGroups]);
  const activeKey = focusKey !== undefined && navKeys.includes(focusKey) ? focusKey : navKeys[0];

  const toggleRow = (id: string) =>
    setOpenRows((cur) => {
      const next = new Set(cur);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  const toggleGroup = (kind: string) =>
    setClosedGroups((cur) => {
      const next = new Set(cur);
      if (!next.delete(kind)) next.add(kind);
      return next;
    });

  const focusItem = (key: string | undefined) => {
    if (key === undefined) return;
    setFocusKey(key);
    requestAnimationFrame(() => treeRef.current?.querySelector<HTMLElement>(`[data-nav-key="${CSS.escape(key)}"]`)?.focus());
  };

  const onTreeKey = (e: KeyboardEvent<HTMLUListElement>) => {
    const key = (e.target as HTMLElement).closest<HTMLElement>("[data-nav-key]")?.dataset["navKey"];
    if (key === undefined || (e.target as HTMLElement).closest("a") !== null) return;
    const at = navKeys.indexOf(key);
    const isGroup = key.startsWith("g:");
    const id = key.slice(2);
    const open = isGroup ? !closedGroups.has(id) : openRows.has(id);
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        focusItem(navKeys[Math.min(navKeys.length - 1, at + 1)]);
        break;
      case "ArrowUp":
        e.preventDefault();
        focusItem(navKeys[Math.max(0, at - 1)]);
        break;
      case "Home":
        e.preventDefault();
        focusItem(navKeys[0]);
        break;
      case "End":
        e.preventDefault();
        focusItem(navKeys[navKeys.length - 1]);
        break;
      case "ArrowRight":
        e.preventDefault();
        if (!open) (isGroup ? toggleGroup : toggleRow)(id);
        else if (isGroup) focusItem(navKeys[at + 1]);
        break;
      case "ArrowLeft":
        e.preventDefault();
        if (open) (isGroup ? toggleGroup : toggleRow)(id);
        else if (!isGroup) focusItem([...navKeys.slice(0, at)].reverse().find((k) => k.startsWith("g:")));
        break;
      case "Enter":
        e.preventDefault();
        (isGroup ? toggleGroup : toggleRow)(id);
        break;
    }
  };

  // 섹션 안에서 `/`는 검색 입력으로(입력 중에는 글자로 처리)
  const onSectionKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    if (e.key === "/" && !e.ctrlKey && !e.metaKey && !e.altKey && !target.matches("input, textarea, select")) {
      e.preventDefault();
      searchRef.current?.focus();
    }
  };

  const refresh = (
    <Button size="sm" loading={refetching} onClick={onRefresh} className="app-mod-refresh">
      {t.refresh}
    </Button>
  );

  if (state.phase === "loading") {
    return (
      <div role="status" aria-busy="true" aria-label={t.loadingRows}>
        <Skeleton rows={6} />
      </div>
    );
  }
  if (state.phase === "unavailable") {
    const failed = state.reason === "failed";
    return (
      <div className="app-mod-section">
        <Banner tone={failed ? "danger" : "info"} actions={failed ? <Button size="sm" loading={refetching} onClick={onRefresh}>{t.retry}</Button> : refresh}>
          {failed ? t.fetchFailed : t.noEndpoint}
        </Banner>
      </div>
    );
  }
  if (modules.length === 0) {
    return (
      <div className="app-mod-section">
        <EmptyState title={t.empty} description={t.emptyBody} action={refresh} />
      </div>
    );
  }

  const filters: { value: StatusFilter; label: string; count: number }[] = [
    { value: "all", label: t.filterAll, count: counts.total },
    ...FILTER_STATUSES.map((s) => ({ value: s, label: moduleStatusLabel(s), count: counts.byStatus[s] ?? 0 })),
  ];

  return (
    <div className="app-mod-section" onKeyDown={onSectionKey}>
      <div className="app-mod-top">
        <p className="app-mod-summary" aria-live="polite">
          {t.summary.total} <strong>{counts.total}</strong>
          {t.summary.unit} — {t.summary.active} <strong>{counts.active}</strong> · {t.summary.off} <strong>{counts.disabled}</strong> ·{" "}
          <span className={counts.problems > 0 ? "app-mod-problems" : "app-muted"} data-failed={counts.hasFailed ? "true" : undefined}>
            {t.summary.problems} <strong>{counts.problems}</strong>
          </span>
        </p>
        {refresh}
      </div>
      <div className="app-mod-filters">
        <div
          role="radiogroup"
          aria-label={t.filterLabel}
          className="app-mod-chips"
          onKeyDown={(e) => {
            if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
            const radios = Array.from(e.currentTarget.querySelectorAll<HTMLElement>('[role="radio"]'));
            const at = radios.indexOf(document.activeElement as HTMLElement);
            if (at < 0) return;
            e.preventDefault();
            radios[(at + (e.key === "ArrowRight" ? 1 : -1) + radios.length) % radios.length]?.focus();
          }}
        >
          {filters.map((f) => (
            <button
              key={f.value}
              type="button"
              role="radio"
              aria-checked={filter === f.value}
              tabIndex={filter === f.value ? 0 : -1}
              className="app-mod-filter"
              data-empty={f.count === 0 ? "true" : undefined}
              onClick={() => setFilter(f.value)}
            >
              {f.label} {f.count}
            </button>
          ))}
        </div>
        <input
          ref={searchRef}
          type="search"
          className="app-mod-search"
          aria-label={t.searchLabel}
          placeholder={`${t.search}  /`}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.stopPropagation();
              setText("");
              e.currentTarget.blur();
            }
          }}
        />
      </div>

      {groups.length === 0 ? (
        <EmptyState
          title={t.noMatch}
          action={
            <Button
              onClick={() => {
                setFilter("all");
                setText("");
              }}
            >
              {t.clearFilter}
            </Button>
          }
        />
      ) : (
        <ul ref={treeRef} role="tree" aria-label={t.list} className="app-mod-tree" onKeyDown={onTreeKey}>
          {groups.map((g) => {
            const groupOpen = !closedGroups.has(g.kind);
            const gKey = `g:${g.kind}`;
            return (
              <li key={g.kind} role="none">
                <div
                  role="treeitem"
                  aria-level={1}
                  aria-expanded={groupOpen}
                  data-nav-key={gKey}
                  tabIndex={activeKey === gKey ? 0 : -1}
                  className="app-mod-group"
                  onClick={() => {
                    setFocusKey(gKey);
                    toggleGroup(g.kind);
                  }}
                  onFocus={() => setFocusKey(gKey)}
                >
                  <Icon name={groupOpen ? "chevronDown" : "chevronRight"} size={16} />
                  <span>{t.group(kindLabel(g.kind), g.modules.length)}</span>
                </div>
                {groupOpen ? (
                  <ul role="group" className="app-mod-rows">
                    {g.modules.map((mod) => {
                      const rKey = `m:${mod.id}`;
                      const open = openRows.has(mod.id);
                      const roles = mod.web_roles ?? [];
                      return (
                        <li key={mod.id} role="none" className="app-mod-item" data-status={mod.status} data-flash={flash.has(mod.id) ? "true" : undefined}>
                          <div
                            role="treeitem"
                            aria-level={2}
                            aria-expanded={open}
                            aria-label={`${mod.id}, ${moduleStatusLabel(mod.status)}`}
                            data-nav-key={rKey}
                            tabIndex={activeKey === rKey ? 0 : -1}
                            className="app-mod-row"
                            onClick={() => {
                              setFocusKey(rKey);
                              toggleRow(mod.id);
                            }}
                            onFocus={() => setFocusKey(rKey)}
                          >
                            <Icon name={open ? "chevronDown" : "chevronRight"} size={16} />
                            <span className="app-mod-main">
                              <code className="app-mod-id" title={mod.id}>{mod.id}</code>
                              {showsReasonCollapsed(mod) ? <span className="app-mod-reason app-muted">{mod.reason}</span> : describeModule(mod) === "" ? null : <span className="app-mod-reason app-muted">{describeModule(mod)}</span>}
                            </span>
                            <ModuleStatusChip status={mod.status} />
                            <span className="app-muted app-mod-version">{mod.version}</span>
                            <span className="app-muted app-mod-roles" title={roles.join(", ")}>{summaryRoles(roles)}</span>
                          </div>
                          {open ? <Detail mod={mod} screens={screens} parts={parts} renderOptions={renderOptions} /> : null}
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/** 컨테이너: 모듈 목록 상태와 화면·연동 부분 데이터를 연결한다. */
export function ModulesSection() {
  const { state, refetch, refetching } = useModules();
  const partDefs = useLinkPartDefs();
  const screens = useMemo<ScreenRef[]>(() => DEFAULT_ROUTES.map((r) => ({ title: lookupMessage(r.titleKey), path: r.path, requires: r.requires ?? [] })), []);
  const parts = useMemo<PartRef[]>(() => partDefs.map((p) => ({ id: p.id, requires: p.requires })), [partDefs]);
  return <ModulesSectionView state={state} refetching={refetching} onRefresh={() => void refetch()} screens={screens} parts={parts} renderOptions={(mod) => <ModuleOptionsPanel id={mod.id} />} />;
}
