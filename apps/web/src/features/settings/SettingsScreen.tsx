import { useFixTarget } from "../../app/fix";
import { useEffect, useMemo, useState, type KeyboardEvent, type ReactNode } from "react";
import { useLocation } from "react-router";
import type { WorkspaceSettings } from "@agent-console/contracts";
import type { FormError } from "@agent-console/schema-form";
import { Banner, Button, Dialog, PageHeader, Spinner, useShortcuts, useToast } from "@agent-console/ui";
import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { ErrorBlock, errorDetails } from "../../app/ErrorBlock";
import { DOCUMENT_REQUIRES, PROJECT_REQUIRES } from "../../app/requirements";
import { useModuleList, useModules, useRequires, useRequiresPartition } from "../../modules";
import { countModules } from "./modulesView";
import { countSectionChanges, groupSections, sectionIdFromHash } from "./sectionState";
import { describeError } from "../../app/errors";
import { messages as m } from "../../app/messages";
import { queryKeys, useApiQuery } from "../../app/queries";
import { ConflictBanner } from "../../definition/ConflictBanner";
import { SaveStatus } from "../../definition/SaveStatus";
import { UnsavedGuard, useHasUnsaved } from "../../definition/unsaved";
import { useDefinitionEditor } from "../../definition/useDefinitionEditor";
import { usePwaUpdate } from "../../pwa/PwaContext";
import { ROUTE_ROLES, routePath } from "../library";
import { DefinitionVersionsTab } from "../versions";
import { SettingsSection } from "./SettingsSection";
import { CommonSection, DelegationTable, UserSection, type SectionEditProps } from "./sections/FormSections";
import { ModulesSection } from "./sections/ModulesSection";
import { InstallSection } from "./sections/InstallSection";
import { KeybindingsSection } from "./sections/KeybindingsSection";
import { NotificationsSection } from "./sections/NotificationsSection";
import { VersionsUiSection } from "./sections/VersionsUiSection";
import { PresetsSection } from "./sections/PresetsSection";
import { AppearanceSection } from "./sections/AppearanceSection";
import { ServerSection } from "./sections/ServerSection";
import { UsageSection } from "./sections/UsageSection";
import { LogsSection } from "./sections/LogsSection";

/** 설정 화면의 섹션 목록(데이터). `keys`는 그 섹션이 편집하는 최상위 설정 키(필드 오류를 섹션에 배정할 때 쓴다). */
export interface SectionDef {
  id: string;
  /** `messages.settings.sections`의 키 */
  titleKey: string;
  descriptionKey: string;
  keys: readonly string[];
  /** 왼쪽 목록의 묶음(`messages.settings.groups`의 키). 묶음은 첫 등장 순서로 나열된다 */
  group: string;
  /** 이 섹션이 있으려면 서버에서 켜져 있어야 하는 모듈 id 또는 역할(모두 만족해야 한다, 비면 항상 있음). 꺼지면 목록과 본문에서 사라진다 */
  requires?: readonly string[];
}

export const SETTINGS_SECTIONS: readonly SectionDef[] = [
  // 테마는 이 브라우저의 값이라 서버·설정 문서 없이 항상 있다.
  { id: "appearance", titleKey: "appearance", descriptionKey: "appearance", keys: [], group: "frequent", requires: [] },
  // 설정 문서를 쓰는 폼 섹션은 설정 문서를 책임지는 기능이 켜져 있어야 한다.
  { id: "chat", titleKey: "chat", descriptionKey: "chat", keys: ["chat"], group: "frequent", requires: DOCUMENT_REQUIRES },
  { id: "usage", titleKey: "usage", descriptionKey: "usage", keys: ["usage"], group: "frequent", requires: [...DOCUMENT_REQUIRES, "usage"] },
  { id: "notifications", titleKey: "notifications", descriptionKey: "notifications", keys: ["ui/notifications"], group: "frequent", requires: DOCUMENT_REQUIRES },
  { id: "shortcuts", titleKey: "shortcuts", descriptionKey: "shortcuts", keys: ["ui/keybindings"], group: "frequent", requires: DOCUMENT_REQUIRES },
  { id: "common", titleKey: "common", descriptionKey: "common", keys: ["agent_defaults"], group: "defaults", requires: DOCUMENT_REQUIRES },
  { id: "delegation", titleKey: "delegation", descriptionKey: "delegation", keys: ["delegation"], group: "defaults", requires: DOCUMENT_REQUIRES },
  { id: "interaction", titleKey: "interaction", descriptionKey: "interaction", keys: ["interaction"], group: "defaults", requires: DOCUMENT_REQUIRES },
  { id: "merge-rules", titleKey: "mergeRules", descriptionKey: "mergeRules", keys: ["settings_merge"], group: "defaults", requires: DOCUMENT_REQUIRES },
  { id: "editor", titleKey: "editor", descriptionKey: "editor", keys: ["editor"], group: "defaults", requires: DOCUMENT_REQUIRES },
  { id: "logs", titleKey: "logs", descriptionKey: "logs", keys: ["logs"], group: "data", requires: [...DOCUMENT_REQUIRES, "logs"] },
  // 프로젝트 관리는 프로젝트 기능이 꺼져 있으면 섹션째 사라진다. 새 정의의 기본 범위(`projects` 설정)도 여기서 고친다.
  { id: "projects", titleKey: "projects", descriptionKey: "projects", keys: ["projects"], group: "data", requires: [...DOCUMENT_REQUIRES, ...PROJECT_REQUIRES] },
  { id: "presets", titleKey: "presets", descriptionKey: "presets", keys: [], group: "data", requires: ["presets"] },
  { id: "versions-ui", titleKey: "versionsUi", descriptionKey: "versionsUi", keys: ["ui/versions"], group: "data", requires: [...DOCUMENT_REQUIRES, "versions"] },
  { id: "versions", titleKey: "versions", descriptionKey: "versions", keys: [], group: "data", requires: [...DOCUMENT_REQUIRES, "versions"] },
  { id: "install", titleKey: "install", descriptionKey: "install", keys: [], group: "system", requires: [] },
  // 기능 모듈 목록은 아무 기능도 없는 서버에서도 원인을 알 수 있어야 하므로 항상 있다.
  { id: "modules", titleKey: "modules", descriptionKey: "modules", keys: [], group: "system", requires: [] },
  { id: "server", titleKey: "server", descriptionKey: "server", keys: [], group: "system", requires: [] },
];

/** 설정 화면에서 기능 모듈 섹션의 앵커 id */
const MODULES_SECTION_ID = "modules";

const sectionTitle = (d: SectionDef) => (m.settings.sections as Record<string, string>)[d.titleKey] ?? d.id;
const sectionDescription = (d: SectionDef) => (m.settings.sectionDescription as Record<string, string>)[d.descriptionKey];

/** 서버가 준 필드 오류를 섹션별로 나눈다. `agent_defaults` 아래 오류는 공통 폼 기준 경로로 바꾼다. */
export function errorsForSection(def: SectionDef, errors: readonly FormError[]): FormError[] {
  return errors
    .filter((e) => def.keys.some((k) => e.path === `/${k}` || e.path.startsWith(`/${k}/`)))
    .map((e) => (def.id === "common" ? { ...e, path: e.path.slice("/agent_defaults".length) } : e));
}

/** 설정 화면(컨테이너): 설정 한 문서를 읽고 섹션별 폼에 나눠 주며, 한 번에 저장한다(`PUT /settings` + `If-Match`). */
export interface SettingsScreenProps {
  /** 본문을 다른 기능이 그리는 섹션(섹션 id -> 렌더러). 설정 기능이 그 기능을 import하지 않게 앱 조립 층이 준다 */
  sectionRenderers?: Readonly<Record<string, () => ReactNode>>;
}

export function SettingsScreen({ sectionRenderers }: SettingsScreenProps) {
  const toast = useToast();
  const queryClient = useQueryClient();
  // 서버 모듈이 꺼서 쓸 수 없는 섹션은 목록과 본문에서 사라진다. 설정 문서 기능이 꺼지면 폼·저장 줄도 사라진다.
  const { met: shownSections } = useRequiresPartition(SETTINGS_SECTIONS);
  const documentPhase = useRequires(DOCUMENT_REQUIRES).phase;
  const documentOn = documentPhase !== "unmet";
  // 설정 문서는 기능이 켜진 것이 확인된 뒤에만 읽는다(목록 확인 중에는 부르지 않는다).
  const documentMet = documentPhase === "met";
  const modules = useModuleList();
  const counts = useMemo(() => countModules(modules), [modules]);
  const editor = useDefinitionEditor<WorkspaceSettings>({
    enabled: documentMet,
    queryKey: queryKeys.settings(),
    load: (rest) => rest.getSettingsVersioned(),
    save: (rest, value, hash) => rest.putSettingsVersioned(value, hash),
  });
  const ids = useMemo(() => shownSections.map((s) => s.id), [shownSections]);
  // 섹션은 한 번에 하나만 보인다. 가리킨 섹션이 없거나 사라졌으면 첫 섹션이다.
  const [picked, setPicked] = useState<string | undefined>(undefined);
  const [seenTarget, setSeenTarget] = useState("");
  // 주소 해시(`#modules` 등)가 가리키는 섹션으로 간다. 사라진 섹션을 가리키면 첫 섹션으로 조용히 보낸다.
  const { hash } = useLocation();
  // 해결 버튼으로 열렸으면 `?section=<섹션>&focus=<필드>`가 붙어 있다(해시가 없을 때 섹션으로 쓴다)
  const fixTarget = useFixTarget();
  const { state: modulesState } = useModules();
  const hashTarget = sectionIdFromHash(hash) || (fixTarget.section ?? "");
  // 주소가 바뀌면(해시·해결 버튼) 그 섹션을 연다(렌더 중 파생 상태 갱신)
  if (seenTarget !== hashTarget) {
    setSeenTarget(hashTarget);
    if (hashTarget !== "") setPicked(hashTarget);
  }
  const active = ids.includes(picked ?? "") ? (picked as string) : ids.includes(hashTarget) ? hashTarget : (ids[0] ?? "");
  const activeDef = shownSections.find((d) => d.id === active);
  // 목록이 확정된 뒤에도 해시가 사라진 섹션을 가리키면 첫 섹션 해시로 조용히 바꾼다
  useEffect(() => {
    if (hashTarget === "" || modulesState.phase === "loading" || ids.includes(hashTarget) || ids[0] === undefined) return;
    window.history.replaceState(null, "", `#${ids[0]}`);
  }, [hashTarget, ids, modulesState.phase]);
  const refreshing = useIsFetching() > 0;
  const update = usePwaUpdate();
  const hasUnsaved = useHasUnsaved();
  const [confirmUpdate, setConfirmUpdate] = useState(false);

  // 프리셋 적용 때 이미 있는 id를 알려 주려는 목록이라 프리셋 섹션이 있을 때만 읽는다.
  const presetsShown = shownSections.some((x) => x.id === "presets");
  const agents = useApiQuery(["list", "agents"], (rest) => rest.listAgents(), { enabled: presetsShown });
  const graphs = useApiQuery(["list", "graphs"], (rest) => rest.listGraphs(), { enabled: presetsShown });
  const resources = useApiQuery(["list", "resources"], (rest) => rest.listResources(), { enabled: presetsShown });
  const existingIds = useMemo(
    () => new Set<string>([...(agents.data ?? []).map((a) => a.id), ...(graphs.data ?? []).map((g) => g.id), ...(resources.data ?? []).map((r) => r.id)]),
    [agents.data, graphs.data, resources.data],
  );
  const links = useMemo(
    () => [
      { to: routePath(ROUTE_ROLES.graph), label: m.settings.presets.toTeams },
      { to: routePath(ROUTE_ROLES.agent), label: m.settings.presets.toAgents },
    ],
    [],
  );

  const onSave = () => {
    void editor.save().then((ok) => {
      if (ok) toast({ tone: "success", text: `${m.definition.savedToast}. ${m.settings.savedNextRun}` });
    });
  };
  useShortcuts([{ id: "settings.save", scope: "settings", keys: "Mod+S", titleKey: "shortcuts.save", modifierRequired: true, run: onSave }]);

  if (documentOn && editor.status === "error") {
    const view = describeError(editor.error, m.settings.loadFailed);
    return (
      <div className="app-screen-frame" data-screen="settings">
        <PageHeader title={m.settings.title} />
        <div className="app-screen-body">
          <ErrorBlock title={m.settings.loadFailed} message={view.message} fix={view.fix} details={errorDetails(view)} detailsLabel={m.common.details} retryLabel={m.common.retry} onRetry={editor.reload} />
        </div>
      </div>
    );
  }

  const value = editor.draft;
  const ready = value !== undefined;
  const editProps: SectionEditProps | null = ready ? { value, onChange: editor.setDraft, disabled: editor.savePhase === "saving" } : null;
  const render = (def: SectionDef) => {
    switch (def.id) {
      case "presets":
        return <PresetsSection existingIds={existingIds} links={links} />;
      case "appearance":
        return <AppearanceSection />;
      case "install":
        return <InstallSection onApplyUpdate={() => (hasUnsaved ? setConfirmUpdate(true) : update.apply())} />;
      case "modules":
        return <ModulesSection />;
      case "server":
        return <ServerSection />;
      case "versions":
        return (
          <DefinitionVersionsTab
            model="WorkspaceSettings"
            currentHash={editor.versionHash}
            dirty={editor.dirty}
            onRestored={() => {
              editor.revert();
              void queryClient.invalidateQueries({ queryKey: queryKeys.settings() });
            }}
          />
        );
    }
    if (editProps === null) return null;
    const props = { ...editProps, errors: errorsForSection(def, editor.fieldErrors), ...(fixTarget.focus && hashTarget === def.id ? { focusPath: fixTarget.focus } : {}) };
    switch (def.id) {
      case "common":
        return <CommonSection {...props} />;
      case "usage":
        return <UsageSection {...props} />;
      case "logs":
        return <LogsSection {...props} dirty={editor.dirty} />;
      case "shortcuts":
        return <KeybindingsSection {...props} />;
      case "notifications":
        return <NotificationsSection {...props} />;
      case "versions-ui":
        return <VersionsUiSection {...props} />;
      case "delegation":
        return (
          <>
            <UserSection {...props} sections={def.keys} />
            <DelegationTable />
          </>
        );
      case "projects":
        return (
          <>
            {sectionRenderers?.[def.id]?.()}
            <UserSection {...props} sections={def.keys} />
          </>
        );
      default:
        return <UserSection {...props} sections={def.keys} />;
    }
  };
  // 서버 정보·프리셋·앱 설치는 설정 문서와 무관해 설정 로딩 중에도 보인다.
  const independent = new Set(["appearance", "presets", "install", "modules", "server", "versions"]);

  const goTo = (id: string) => {
    window.history.replaceState(null, "", `#${id}`);
    setPicked(id);
  };
  const changeCount = (def: SectionDef) => (editor.base === undefined || editor.draft === undefined ? 0 : countSectionChanges(def.keys, editor.base, editor.draft));
  const navGroups = groupSections(shownSections);
  const groupTitle = (g: string) => (m.settings.groups as Record<string, string>)[g] ?? g;
  const onNavKey = (e: KeyboardEvent<HTMLElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const links = Array.from(e.currentTarget.querySelectorAll<HTMLElement>("a"));
    const i = links.indexOf(document.activeElement as HTMLElement);
    if (i < 0) return;
    e.preventDefault();
    links[(i + (e.key === "ArrowDown" ? 1 : -1) + links.length) % links.length]?.focus();
  };

  return (
    <div className="app-screen-frame" data-screen="settings">
      <UnsavedGuard dirty={editor.dirty} />
      <PageHeader
        title={m.settings.title}
        status={
          <>
            {documentOn ? <SaveStatus dirty={editor.dirty} phase={editor.savePhase} onRetry={onSave} /> : null}
            {refreshing ? <span role="status" className="app-refresh"><Spinner /><span className="ac-sr-only">{m.common.refreshing}</span></span> : null}
          </>
        }
        actions={!documentOn ? undefined : (
          <>
            <Button onClick={editor.revert} disabled={!editor.dirty || editor.savePhase === "saving"}>
              {m.settings.revert}
            </Button>
            <Button
              variant="primary"
              loading={editor.savePhase === "saving"}
              disabled={!editor.dirty || editor.conflict !== null}
              title={editor.conflict !== null ? m.definition.conflict.saveDisabled : "Ctrl+S"}
              onClick={onSave}
            >
              {m.settings.save}
            </Button>
          </>
        )}
      />
      {editor.conflict === null ? null : (
        <ConflictBanner details={editor.conflict} busy={editor.savePhase === "saving"} onLoadServer={() => void editor.loadServerVersion()} onOverwrite={() => void editor.overwrite()} />
      )}
      {editor.saveError !== null && editor.fieldErrors.length === 0 ? <Banner tone="danger">{editor.saveError}</Banner> : null}
      <div className="app-settings-layout">
        <nav className="app-settings-nav" aria-label={m.settings.sectionNav} onKeyDown={onNavKey}>
          {navGroups.map((g) => (
            <div key={g.group} className="app-settings-navgroup">
              <h3 id={`settings-group-${g.group}`} className="app-settings-grouptitle">{groupTitle(g.group)}</h3>
              <ul aria-labelledby={`settings-group-${g.group}`}>
                {g.items.map((def) => {
                  const failed = errorsForSection(def, editor.fieldErrors).length > 0;
                  const changed = changeCount(def);
                  return (
                    <li key={def.id}>
                      <a
                        href={`#${def.id}`}
                        aria-current={active === def.id ? "location" : undefined}
                        onClick={(e) => {
                          e.preventDefault();
                          goTo(def.id);
                        }}
                      >
                        {sectionTitle(def)}
                        {failed ? <span className="app-sev" data-severity="error" aria-label={m.settings.sectionNavError}> ●</span> : null}
                        {changed > 0 ? <span className="app-settings-changed" role="img" title={m.settings.changedDot} aria-label={m.settings.changedDot} /> : null}
                        {def.id === MODULES_SECTION_ID && counts.problems > 0 ? (
                          <span className="app-sev" data-severity={counts.hasFailed ? "error" : "warning"} role="img" aria-label={m.modules.dotLabel}> ●</span>
                        ) : null}
                      </a>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>
        <div className="app-settings-body">
          {ready && editor.versionHash === undefined ? <Banner tone="info">{m.settings.emptyHint}</Banner> : null}
          {activeDef === undefined ? null : (
            <SettingsSection
              key={activeDef.id}
              id={activeDef.id}
              title={sectionTitle(activeDef)}
              {...(sectionDescription(activeDef) === undefined ? {} : { description: sectionDescription(activeDef) as string })}
              status={changeCount(activeDef) > 0 ? m.settings.changes(changeCount(activeDef)) : undefined}
              hasError={errorsForSection(activeDef, editor.fieldErrors).length > 0}
              loading={!ready && !independent.has(activeDef.id)}
            >
              {render(activeDef)}
            </SettingsSection>
          )}
        </div>
      </div>
      <Dialog
        open={confirmUpdate}
        title={m.pwa.updateConfirmTitle}
        onClose={() => setConfirmUpdate(false)}
        actions={
          <>
            <Button onClick={() => setConfirmUpdate(false)}>{m.common.cancel}</Button>
            <Button variant="danger" onClick={() => update.apply()}>{m.pwa.updateConfirmYes}</Button>
          </>
        }
      >
        <p className="ac-text">{m.pwa.updateConfirmBody}</p>
      </Dialog>
    </div>
  );
}
