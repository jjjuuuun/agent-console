import { useEffect, useMemo, useState } from "react";
import { keepPreviousData } from "@tanstack/react-query";
import type { ExporterDescriptor, ExportPlan, ExportResult, ExportRootInfo, ExportSelection } from "@agent-console/contracts";
import { ApiError } from "@agent-console/api-client";
import { useApi } from "../../app/ApiContext";
import { describeError } from "../../app/errors";
import { useApiQuery } from "../../app/queries";
import { useStorage } from "../../app/StorageContext";
import {
  STORAGE_KEYS,
  addItem,
  blockingIssues,
  buildRequest,
  checkSubdir,
  conflictPathsOf,
  mapPlanError,
  parseConflictPolicy,
  subdirErrorOf,
  type ConflictPolicy,
  type PlanErrorMap,
  type SubdirProblem,
} from "./exportLogic";
import { exportMessages as t } from "./messages";

export type Step = 1 | 2 | 3 | 4 | 5;
export type Destination = "archive" | "folder";

/** 한 번의 내보내기가 끝난 결과(보관 파일이면 파일 이름·크기, 폴더면 서버 결과). */
export type Outcome =
  | { kind: "archive"; filename: string; size: number }
  | { kind: "folder"; result: ExportResult; rootLabel: string; path: string };

const DEBOUNCE_MS = 400;

export interface ExportFlow {
  step: Step;
  goTo: (step: Step) => void;
  next: () => void;
  prev: () => void;
  canNext: boolean;
  nextReason: string | undefined;

  exporters: { loading: boolean; error: Error | null; data: ExporterDescriptor[]; refetch: () => void };
  exporter: ExporterDescriptor | undefined;
  chooseExporter: (id: string) => void;

  items: ExportSelection[];
  addItem: (item: ExportSelection) => void;
  removeItem: (index: number) => void;

  options: Record<string, unknown>;
  setOptions: (next: Record<string, unknown>) => void;
  planErrors: PlanErrorMap | undefined;

  plan: { data: ExportPlan | undefined; loading: boolean; fetching: boolean; error: Error | null; refetch: () => void };
  blocked: boolean;

  roots: ExportRootInfo[];
  rootsLoading: boolean;
  destination: Destination;
  setDestination: (d: Destination) => void;
  rootId: string;
  setRootId: (id: string) => void;
  subdir: string;
  setSubdir: (s: string) => void;
  subdirProblem: SubdirProblem | undefined;
  subdirServerError: string | undefined;
  onConflict: ConflictPolicy;
  setOnConflict: (p: ConflictPolicy) => void;

  busy: boolean;
  runError: { message: string; conflictPaths: string[] } | null;
  outcome: Outcome | null;
  /** 폴더 쓰기를 실제로 하기 전에 확인이 필요한가(덮어쓰기 + 덮어쓸 파일이 있을 때) */
  run: () => Promise<void>;
  restart: () => void;
}

/**
 * 내보내기 위저드 상태 + 서버 호출(형식 목록·미리보기·루트·보관 파일·폴더 쓰기). 화면(`ExportDialog`)은 이 값만 그린다.
 * 마지막으로 고른 형식·충돌 처리는 주입된 저장소(localStorage 래퍼)에 기억한다.
 */
export function useExportFlow(initialItems: readonly ExportSelection[], onDownload: (blob: Blob, filename: string) => void): ExportFlow {
  const { rest } = useApi();
  const storage = useStorage();
  const exportersQuery = useApiQuery(["list", "exporters"], (r) => r.listExporters(), { retry: false });
  const rootsQuery = useApiQuery(["list", "export-roots"], (r) => r.listExportRoots(), { retry: false });
  const exporters = useMemo(() => exportersQuery.data ?? [], [exportersQuery.data]);
  const roots = useMemo(() => rootsQuery.data ?? [], [rootsQuery.data]);

  const [step, setStep] = useState<Step>(1);
  const [exporterId, setExporterId] = useState<string | null>(() => storage.get(STORAGE_KEYS.exporter));
  const [items, setItems] = useState<ExportSelection[]>(() => [...initialItems]);
  const [options, setOptionsState] = useState<Record<string, unknown>>({});
  const [destination, setDestination] = useState<Destination>("archive");
  const [rootChoice, setRootChoice] = useState("");
  const [subdir, setSubdirState] = useState("");
  const [subdirServerError, setSubdirServerError] = useState<string | undefined>(undefined);
  const [onConflict, setOnConflictState] = useState<ConflictPolicy>(() => parseConflictPolicy(storage.get(STORAGE_KEYS.onConflict)));
  const [busy, setBusy] = useState(false);
  const [runError, setRunError] = useState<ExportFlow["runError"]>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [planErrors, setPlanErrors] = useState<PlanErrorMap | undefined>(undefined);

  // 고른 형식: 기억한 값이 목록에 있으면 그것, 아니면 첫 형식(1개면 미리 선택)
  const exporter = exporters.find((e) => e.id === exporterId) ?? (exporters.length === 1 ? exporters[0] : undefined);
  const rootId = roots.some((r) => r.id === rootChoice) ? rootChoice : (roots[0]?.id ?? "");
  const subdirProblem = checkSubdir(subdir);

  // 미리보기 요청: ④에서 폴더를 골랐을 때만 목적지를 싣는다.
  const withDestination = step === 4 && destination === "folder" && rootId !== "" && subdirProblem === undefined;
  const request = useMemo(
    () =>
      exporter === undefined
        ? undefined
        : buildRequest({ exporter: exporter.id, items, options, ...(withDestination ? { root: rootId, subdir } : {}) }),
    [exporter, items, options, withDestination, rootId, subdir],
  );
  const requestKey = JSON.stringify(request ?? null);
  const [debounced, setDebounced] = useState(request);
  useEffect(() => {
    const handle = setTimeout(() => setDebounced(request), DEBOUNCE_MS);
    return () => clearTimeout(handle);
    // requestKey가 내용 비교를 맡는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey]);
  // 처음 미리보기로 들어올 때는 기다리지 않는다.
  const effective = step === 3 && debounced === undefined ? request : debounced;
  const planEnabled = step >= 3 && step <= 4 && effective !== undefined && items.length > 0;
  const planQuery = useApiQuery<ExportPlan>(["export-plan", JSON.stringify(effective ?? null)], (r) => r.planExport(effective!), {
    enabled: planEnabled,
    retry: false,
    staleTime: 0,
    placeholderData: keepPreviousData,
  });

  // 서버가 옵션·항목을 거부(422)하면 위치를 연결해 ②로 돌려보낸다.
  const planError = planQuery.error;
  const [seenError, setSeenError] = useState<Error | null>(null);
  if (planError !== null && planError !== seenError) {
    setSeenError(planError);
    if (planError instanceof ApiError && planError.status === 422) {
      const mapped = mapPlanError(planError);
      setPlanErrors(mapped);
      if (mapped.routable && step === 3) setStep(2);
    }
  }

  const blocked = blockingIssues(planQuery.data?.warnings).length > 0;

  const nextReason = (() => {
    if (step === 1) return exporter === undefined ? t.exporter.label : undefined;
    if (step === 2) return items.length === 0 ? t.items.none : undefined;
    if (step === 3) {
      if (planQuery.isLoading || planQuery.data === undefined) return t.preview.loading;
      if (blocked) return t.preview.blocked;
      if (planQuery.data.files?.length === 0) return t.preview.empty;
    }
    return undefined;
  })();
  const unsupported = exporter !== undefined && items.some((i) => !(exporter.kinds ?? []).includes(i.kind));
  const canNext = step < 4 && nextReason === undefined && !(step === 2 && unsupported);

  const setOptions = (next: Record<string, unknown>) => {
    setOptionsState(next);
    setPlanErrors(undefined);
  };

  const run = async () => {
    if (exporter === undefined || busy) return;
    setBusy(true);
    setRunError(null);
    setSubdirServerError(undefined);
    try {
      if (destination === "archive") {
        const archive = await rest.downloadExportArchive(buildRequest({ exporter: exporter.id, items, options }));
        onDownload(archive.blob, archive.filename);
        setOutcome({ kind: "archive", filename: archive.filename, size: archive.blob.size });
      } else {
        const result = await rest.writeExport({
          exporter: exporter.id,
          items,
          options,
          root: rootId,
          subdir: subdir.trim(),
          on_conflict: onConflict,
        });
        const root = roots.find((r) => r.id === rootId);
        setOutcome({ kind: "folder", result, rootLabel: root?.label || rootId, path: root?.path ?? "" });
      }
      setStep(5);
    } catch (e) {
      const sub = subdirErrorOf(e);
      if (sub !== undefined) setSubdirServerError(sub);
      const view = describeError(e, t.dest.failed);
      setRunError({ message: sub === undefined ? view.message : t.dest.failed, conflictPaths: conflictPathsOf(e) });
    } finally {
      setBusy(false);
    }
  };

  return {
    step,
    goTo: (s) => {
      if (!busy && s < step && step <= 4) setStep(s);
    },
    next: () => {
      if (canNext) setStep((step + 1) as Step);
    },
    prev: () => {
      if (!busy && step > 1 && step <= 4) setStep((step - 1) as Step);
    },
    canNext,
    nextReason,
    exporters: { loading: exportersQuery.isLoading, error: exportersQuery.error, data: exporters, refetch: () => void exportersQuery.refetch() },
    exporter,
    chooseExporter: (id) => {
      setExporterId(id);
      setOptionsState({});
      setPlanErrors(undefined);
      storage.set(STORAGE_KEYS.exporter, id);
    },
    items,
    addItem: (item) => setItems((cur) => addItem(cur, item)),
    removeItem: (index) => setItems((cur) => cur.filter((_, i) => i !== index)),
    options,
    setOptions,
    planErrors,
    plan: { data: planQuery.data, loading: planQuery.isLoading && planEnabled, fetching: planQuery.isFetching, error: planQuery.error, refetch: () => void planQuery.refetch() },
    blocked,
    roots,
    rootsLoading: rootsQuery.isLoading,
    destination,
    setDestination,
    rootId,
    setRootId: setRootChoice,
    subdir,
    setSubdir: (s) => {
      setSubdirState(s);
      setSubdirServerError(undefined);
    },
    subdirProblem,
    subdirServerError,
    onConflict,
    setOnConflict: (p) => {
      setOnConflictState(p);
      storage.set(STORAGE_KEYS.onConflict, p);
    },
    busy,
    runError,
    outcome,
    run,
    restart: () => {
      setOutcome(null);
      setRunError(null);
      setStep(1);
    },
  };
}
