import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RUN_ORIGINS, type GraphSummary, type PortDef, type Run } from "@agent-console/contracts";
import { ApiError } from "@agent-console/api-client";
import { createProjectsText, projectAbilities, statusInfo } from "@agent-console/projects";
import { Banner, Button, Dialog } from "@agent-console/ui";
import { describeError } from "../../app/errors";
import { FixButtons } from "../../app/fix";
import { messages as appMessages } from "../../app/messages";
import { useApi } from "../../app/ApiContext";
import { useStorage } from "../../app/StorageContext";
import { useGraphLoginGate } from "../backendChoice";
import { DEFINITION_KINDS, ROUTE_ROLES, routePath } from "../library";
import { ProjectTargetPicker, startErrorView, targetPickerMessages as pm, useCopyDialog, useProjects, type StartErrorView, type TargetOption } from "../projects";
import { GraphIssuesPreview, ValidationChip, blocksRun, hasEntry } from "../teams";
import { RunInputForm } from "./RunInputForm";
import { buildRunInput, initialInputValues, inputIssues, serverInputErrors } from "./runInputLib";
import { clearRunDraft, readRunDraft, writeRunDraft } from "./runDraft";
import { runStartMessages as t } from "./runStartMessages";

const text = createProjectsText();

/** 웹 [실행]이 보내는 시작 경로(`RUN_ORIGINS`의 한 값, 새 origin을 만들지 않는다). */
const WEB_ORIGIN: (typeof RUN_ORIGINS)[number] = "web";
/** 마지막으로 실행한 구성 id를 기억하는 저장 키 */
export const LAST_RUN_GRAPH_KEY = "ac.run.lastGraph";

export interface RunStartDialogProps {
  /** 처음 고를 구성 id(없으면 마지막으로 실행한 구성) */
  preselected?: string | undefined;
  /** 대화상자가 처음 가리킬 프로젝트(없으면 현재 프로젝트) */
  initialProject?: string | undefined;
  onClose: () => void;
  /** 실행이 시작됐다(상세로 이동은 호출자가 한다) */
  onStarted: (run: Run) => void;
}

/**
 * 새 실행 대화상자(screen-run-start §3): 폴더 줄 + 구성 라디오 + 구성의 입력 칸 + [실행 시작].
 * 입력 칸은 선택한 구성의 `Graph.inputs`에서 그린다. 열려 있을 때만 마운트한다.
 */
export function RunStartDialog(props: RunStartDialogProps) {
  const p = useProjects();
  const { rest, space } = useApi();
  const storage = useStorage();
  const queryClient = useQueryClient();
  const copy = useCopyDialog();
  const uid = useId();
  const bodyRef = useRef<HTMLDivElement>(null);

  const active = useMemo(() => p.views.filter((v) => v.project.archived !== true), [p.views]);
  const [projectId, setProjectId] = useState<string | null>(() => {
    const wanted = props.initialProject ?? p.current;
    return wanted !== null && wanted !== undefined && active.some((v) => v.project.id === wanted) ? wanted : (active[0]?.project.id ?? null);
  });
  const view = active.find((v) => v.project.id === projectId);
  const [picked, setPicked] = useState<string | undefined>(props.preselected ?? storage.get(LAST_RUN_GRAPH_KEY) ?? undefined);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [touched, setTouched] = useState<ReadonlySet<string>>(new Set());
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ raw: unknown; view: StartErrorView | null } | null>(null);
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});

  const graphs = useQuery({
    queryKey: ["list", "graphs", "space", projectId] as const,
    queryFn: () => space(projectId).listGraphs(),
    enabled: projectId !== null,
    retry: false,
  });

  const abilities = view === undefined ? undefined : projectAbilities(view, { recordsWritable: view.records_writable !== false });
  const startBlockRef = abilities?.start_run.allowed === false ? abilities.start_run.reason : null;
  const info = view === undefined ? undefined : statusInfo(view);


  const graphPath = routePath(ROUTE_ROLES.graph);
  const options: TargetOption[] = useMemo(
    () =>
      (graphs.data ?? []).map((g: GraphSummary) => {
        const noEntry = hasEntry(g) === false;
        const blocked = noEntry || blocksRun(g.validation);
        const hasIssues = g.validation != null && (blocksRun(g.validation) || (g.validation.error_count ?? 0) > 0 || (g.validation.warning_count ?? 0) > 0);
        return {
          id: g.id,
          name: g.name,
          description: g.description,
          meta: pm.config.nodes(g.node_count),
          blocked,
          reason: hasIssues ? <ValidationChip summary={g.validation as NonNullable<GraphSummary["validation"]>} /> : noEntry ? <span>{pm.config.notSelectable}</span> : undefined,
          expanded: hasIssues ? <GraphIssuesPreview graph={g} project={projectId} /> : undefined,
          editHref: projectId === null ? undefined : `${graphPath}/${encodeURIComponent(g.id)}?prj=${encodeURIComponent(projectId)}`,
        };
      }),
    [graphs.data, graphPath, projectId],
  );
  const selected = picked !== undefined && options.some((o) => o.id === picked && o.blocked !== true) ? picked : options.find((o) => o.blocked !== true)?.id;

  // 선택한 구성의 입력 포트(`Graph.inputs`) — 정의 조회 한 번
  const definition = useQuery({
    queryKey: ["definition", "graph", projectId, selected] as const,
    queryFn: () => space(projectId).getGraph(selected as string),
    enabled: projectId !== null && selected !== undefined,
    retry: false,
  });
  const { signedOut } = useGraphLoginGate(definition.data?.graph, projectId);
  const ports: readonly PortDef[] = useMemo(() => definition.data?.graph.inputs ?? [], [definition.data]);
  const portsReady = definition.isSuccess && definition.data !== undefined;

  // 구성(또는 프로젝트)이 바뀌어 포트가 오면 값을 다시 짠다: 같은 이름의 값은 옮기고, 초안이 있으면 복원한다
  const portsKey = definition.data === undefined ? null : `${projectId}/${selected}/${definition.data.version_hash}`;
  // 렌더 중 상태 보정(React 권장 패턴): 키가 바뀐 그 렌더에서 값을 다시 짠다
  const [formKey, setFormKey] = useState<string | null>(null);
  if (portsKey !== formKey) {
    setFormKey(portsKey);
    if (portsKey !== null && projectId !== null && selected !== undefined) {
      const draft = readRunDraft(storage, projectId, selected);
      setValues((prev) => initialInputValues(ports, { ...prev, ...(draft ?? {}) }));
      setTouched(new Set());
      setSubmitted(false);
      setServerErrors({});
    }
  }
  useEffect(() => {
    if (portsKey === null || projectId === null || selected === undefined || busy) return;
    writeRunDraft(storage, projectId, selected, values);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [values]);

  const issues = useMemo(() => inputIssues(ports, values), [ports, values]);
  const fieldErrors = useMemo(() => {
    const out: Record<string, string> = { ...serverErrors };
    for (const [name, issue] of Object.entries(issues)) {
      if (!submitted && !touched.has(name)) continue;
      out[name] = issue.kind === "required" ? t.inputRequired : t.inputInvalidJson;
    }
    return out;
  }, [issues, serverErrors, submitted, touched]);

  const blockText =
    startBlockRef !== null && startBlockRef !== undefined
      ? text(startBlockRef)
      : signedOut
        ? pm.blocked.signedOut
        : selected === undefined
          ? t.blockedConfig
          : !portsReady
            ? definition.isError
              ? t.inputLoadError
              : t.inputLoading
            : Object.keys(issues).length > 0
              ? t.blockedInput
              : null;
  const canStart = blockText === null && !busy && projectId !== null && selected !== undefined;

  const start = async (graphId = selected, inputPorts = ports, inputValues = values) => {
    if (graphId === undefined || projectId === null) return;
    setSubmitted(true);
    if (Object.keys(inputIssues(inputPorts, inputValues)).length > 0) {
      bodyRef.current?.querySelector<HTMLElement>("[aria-invalid='true'], textarea, input")?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    setServerErrors({});
    try {
      const run = await rest.createRun({ graph_id: graphId, input: buildRunInput(inputPorts, inputValues), project_id: projectId, origin: WEB_ORIGIN });
      storage.set(LAST_RUN_GRAPH_KEY, graphId);
      clearRunDraft(storage, projectId, graphId);
      if (projectId !== p.current) p.setCurrent(projectId);
      void queryClient.invalidateQueries({ queryKey: ["list", "runs"] });
      props.onStarted(run);
    } catch (e) {
      const fieldMap = e instanceof ApiError && e.status === 422 ? serverInputErrors(e.details, inputPorts) : {};
      if (Object.keys(fieldMap).length > 0) setServerErrors(fieldMap);
      else setError({ raw: e, view: startErrorView(e, (_kind, id) => options.find((o) => o.id === id)?.name ?? id ?? "") });
    } finally {
      setBusy(false);
    }
  };

  const importFromLibrary = (items?: { kind: string; id: string }[], runAfter?: string) => {
    if (projectId === null) return;
    // 자동 재시도는 지금 입력 그대로 보낸다(가져온 구성의 포트를 모르므로 같은 이름 값만 쓴다)
    const snapshot = values;
    copy.open({
      direction: "import",
      project: projectId,
      start: items === undefined ? "pick" : "plan",
      ...(items === undefined ? {} : { items }),
      ...(runAfter === undefined ? {} : { submitStyle: "run" as const }),
      onApplied: (o) => {
        void graphs.refetch();
        if (o.first !== null && o.first.kind === DEFINITION_KINDS.graph) setPicked(o.first.id);
        if (runAfter !== undefined && o.allOk && o.first !== null) {
          const id = o.first.id;
          void space(projectId).getGraph(id).then((g) => start(id, g.graph.inputs ?? [], initialInputValues(g.graph.inputs ?? [], snapshot)));
        }
      },
    });
  };

  const fix = error?.view;
  const fixButtons = (() => {
    if (fix == null || projectId === null) return null;
    switch (fix.fix) {
      case "pickProject":
        return <Button size="sm" variant="primary" onClick={() => p.setSwitcherOpen(true)}>{pm.error.pickProject}</Button>;
      case "importAndRun": {
        const n = fix.notImported;
        const items = [{ kind: n?.kind ?? DEFINITION_KINDS.graph ?? "", id: n?.id ?? selected ?? "" }];
        return (
          <>
            <Button size="sm" variant="primary" onClick={() => importFromLibrary(items, items[0]?.id ?? "")}>{pm.error.importAndRun}</Button>
            <Button size="sm" variant="secondary" onClick={() => setError(null)}>{pm.error.dismiss}</Button>
          </>
        );
      }
      case "toLibrary":
        return <Link className="ac-btn" data-variant="secondary" data-size="sm" to={graphPath} onClick={props.onClose}>{pm.error.toLibrary}</Link>;
      case "repath":
        return <Button size="sm" variant="secondary" onClick={() => p.requestRepath(projectId)}>{pm.error.repath}</Button>;
      case "checkInHome":
        return <Button size="sm" variant="secondary" onClick={() => { props.onClose(); p.openHome(projectId); }}>{pm.error.checkInHome}</Button>;
      case "retry":
        return <Button size="sm" variant="secondary" onClick={() => void start()}>{pm.error.retry}</Button>;
      case "openSettings":
        return error?.raw !== undefined && (error.raw as { fix?: unknown }).fix != null ? (
          <FixButtons fix={(error.raw as { fix: Parameters<typeof FixButtons>[0]["fix"] }).fix} onNavigate={props.onClose} />
        ) : (
          <Link className="ac-btn" data-variant="secondary" data-size="sm" to={routePath(ROUTE_ROLES.settings)} onClick={props.onClose}>{pm.error.openSettings}</Link>
        );
      default:
        return null;
    }
  })();

  const onKey = (e: React.KeyboardEvent) => {
    // 한글 조합 중 Ctrl+Enter는 제출하지 않는다
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !e.nativeEvent.isComposing && e.nativeEvent.keyCode !== 229 && canStart) {
      e.preventDefault();
      void start();
    }
  };

  const reasonId = `${uid}-reason`;
  return (
    <>
      <Dialog
        open
        title={t.title}
        size="md"
        onClose={() => {
          if (!busy) props.onClose();
        }}
        actions={
          <>
            <span className="run-start-hint app-muted">{t.hintShortcut}</span>
            <Button onClick={props.onClose} disabled={busy}>{appMessages.common.cancel}</Button>
            <Button variant="primary" loading={busy} aria-disabled={canStart ? undefined : "true"} aria-describedby={blockText !== null && !busy ? reasonId : undefined} onClick={() => canStart && void start()}>
              {busy ? t.busy : t.submit}
            </Button>
          </>
        }
      >
        <div className="run-start" ref={bodyRef} onKeyDown={onKey}>
          {signedOut ? <Banner tone="warning">{pm.blocked.signedOut}</Banner> : null}
          {error === null ? null : error.view !== null ? (
            <Banner tone={error.view.tone}>
              <span>{error.view.message}</span>
              <div className="app-fix-actions">{fixButtons}</div>
            </Banner>
          ) : (
            <Banner tone="danger" actions={<Button size="sm" onClick={() => void start()}>{t.retry}</Button>}>
              <strong>{t.error}</strong> {describeError(error.raw, t.error).message}
            </Banner>
          )}
          <ProjectTargetPicker
            project={view === undefined ? undefined : { id: view.project.id, name: view.project.name, dir: view.project.folder ?? "" }}
            projects={active.map((v) => ({ id: v.project.id, name: v.project.name, dir: v.project.folder ?? "" }))}
            onProjectChange={(id) => { setProjectId(id); setPicked(undefined); setError(null); }}
            switchesCurrent={projectId !== null && projectId !== p.current}
            folderProblem={info === undefined || info.plain ? (startBlockRef == null || view === undefined ? undefined : { text: text(startBlockRef), tone: "warning" }) : { text: startBlockRef != null ? text(startBlockRef) : text(info.label), tone: info.tone === "danger" ? "danger" : "warning" }}
            onRepath={projectId === null ? undefined : () => p.requestRepath(projectId)}
            options={options}
            loading={graphs.isLoading}
            error={graphs.isError}
            onRetry={() => void graphs.refetch()}
            value={selected}
            onChange={setPicked}
            onImport={() => importFromLibrary()}
            importBlockedReason={abilities?.copy_in.allowed === false && abilities.copy_in.reason !== null ? text(abilities.copy_in.reason) : undefined}
            createHref={projectId === null ? undefined : `${graphPath}?prj=${encodeURIComponent(projectId)}`}
            onNavigate={props.onClose}
            listLabel={t.configLabel}
          >
            {selected === undefined ? null : (
              <section className="run-start-input" aria-labelledby={`${uid}-input`}>
                <h3 id={`${uid}-input`} className="run-start-input-title">{t.input}</h3>
                {definition.isPending ? (
                  <div className="app-skeleton" role="status" aria-busy="true" aria-label={t.inputLoading}>
                    <div className="app-skeleton-row" />
                    <div className="app-skeleton-row" />
                  </div>
                ) : definition.isError ? (
                  <div className="run-start-load-error" role="alert">
                    <span className="run-input-error">{t.inputLoadError}</span>
                    <Button size="sm" onClick={() => void definition.refetch()}>{t.retry}</Button>
                  </div>
                ) : (
                  <RunInputForm
                    ports={ports}
                    values={values}
                    errors={fieldErrors}
                    disabled={busy}
                    idPrefix={`${uid}-port`}
                    onChange={(name, v) => { setValues((prev) => ({ ...prev, [name]: v })); setServerErrors((prev) => (name in prev ? Object.fromEntries(Object.entries(prev).filter(([k]) => k !== name)) : prev)); }}
                    onBlurPort={(name) => setTouched((prev) => new Set(prev).add(name))}
                  />
                )}
              </section>
            )}
          </ProjectTargetPicker>
          {blockText !== null && !busy ? <p id={reasonId} className="app-muted tp-block-reason" role="status">{blockText}</p> : null}
        </div>
      </Dialog>
      {copy.dialog}
    </>
  );
}
