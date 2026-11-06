/**
 * 작업 실행 흐름(컨테이너 훅): 연동 동작 하나를 눌러 시작하고 결과를 화면 안내로 바꾼다.
 * 결과는 세 갈래다 — 시작함(토스트 + 실행 열기), 관문에 막힘(`GateNotice`), 실패(오류 안내 + 해결 버튼).
 * 프로젝트에 구성이 없고 공용에 있으면(`project.not_imported`의 `in_library`) [가져와서 실행]으로 복사 계획 대화상자를 열고, 다 가져오면 같은 동작을 다시 시도한다.
 * 연동 id·동작 id·프로필 이름은 `TaskAction`의 데이터이고 이 파일에 없다.
 */
import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@agent-console/api-client";
import { ERROR_CODES } from "@agent-console/contracts";
import type { Issue } from "@agent-console/contracts";
import { KNOWN_TASK_ACTION_STATUSES } from "@agent-console/contracts/constants";
import { useToast } from "@agent-console/ui";
import type { ParsedTask, SddGateBlockedDetails, SddTaskChangedDetails, TaskAction, TaskActionResult } from "@agent-console/contracts/sdd";
import { startErrorView, useCopyDialog, type StartErrorView } from "../projects";
import { ROUTE_ROLES, routePath } from "../library";
import { sddMessages as m } from "./messages";
import { sddKeys, useSddSpace } from "./useSddApi";
import type { SddContext } from "./useSddContext";

/** 화면에 한 번에 하나만 둔다(새 것이 이전 것을 대체). */
export type RunNotice =
  | { kind: "gate"; details: SddGateBlockedDetails }
  | { kind: "error"; message: string; view: StartErrorView | null; task: ParsedTask; action: TaskAction };

export interface TaskRunner {
  /** 이 작업에서 이 동작을 시작한다. 결과는 토스트·`notice`로 나온다. */
  run: (task: ParsedTask, action: TaskAction) => Promise<void>;
  /** 막힌 동작 항목의 이슈를 안내로 올린다(관문이면 `GateNotice`) */
  showIssue: (issue: Issue) => void;
  notice: RunNotice | null;
  dismiss: () => void;
  /** 지금 시작 중인 작업 키 */
  busyKey: string | null;
  /** 가져와서 실행: 해당 구성을 공용에서 가져오고 같은 동작을 다시 시도한다 */
  importAndRun: (notice: Extract<RunNotice, { kind: "error" }>) => void;
  /** 복사 계획 대화상자(화면 어디든 한 번 그린다) */
  dialog: ReactNode;
}

const str = (v: unknown): string | undefined => (typeof v === "string" && v !== "" ? v : undefined);

/** 이슈에서 관문 상세를 만든다(서버가 `details`에 `gate_id`·`document_ids`를 싣는다). */
export function gateOf(issue: Issue): SddGateBlockedDetails {
  const d = issue.details ?? {};
  const docs = Array.isArray(d["document_ids"]) ? (d["document_ids"] as unknown[]).filter((x): x is string => typeof x === "string") : [];
  return { gate_id: str(d["gate_id"]) ?? "", message: issue.message, ...(docs.length > 0 ? { document_ids: docs } : {}) };
}

export interface TaskRunnerOptions {
  specId: string;
  ctx: SddContext;
  /** 줄이 바뀌었다는 409를 받았을 때(작업 표를 최신 줄로 다시 그린다) */
  onTaskChanged?: (task: ParsedTask, details: SddTaskChangedDetails) => void;
}

export function useTaskRunner({ specId, ctx, onTaskChanged }: TaskRunnerOptions): TaskRunner {
  const space = useSddSpace();
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const copy = useCopyDialog();
  const [notice, setNotice] = useState<RunNotice | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const refresh = () => qc.invalidateQueries({ queryKey: sddKeys.root });

  const fail = (task: ParsedTask, action: TaskAction, error: unknown, issue?: Issue) => {
    const err = error instanceof ApiError ? error : issue !== undefined ? new ApiError(422, { code: issue.code, message: issue.message, details: issue.details ?? {} }) : undefined;
    const view = err === undefined ? null : startErrorView(err);
    const message = view?.message ?? (err !== undefined && err.message !== "" ? err.message : error instanceof Error && error.message !== "" ? error.message : m.run.failed);
    setNotice({ kind: "error", message, view, task, action });
  };

  const run = async (task: ParsedTask, action: TaskAction): Promise<void> => {
    setNotice(null);
    setBusyKey(task.key);
    try {
      const result: TaskActionResult = await space.client.runTaskAction(specId, task.key, action.integration, action.id);
      if (result.status === KNOWN_TASK_ACTION_STATUSES.STARTED) {
        const runId = result.run_id ?? undefined;
        toast({
          tone: "success",
          text: m.run.started(task.title ?? task.key),
          durationMs: 8000,
          ...(runId === undefined ? {} : { action: { label: m.run.open, onClick: () => void navigate(`${routePath(ROUTE_ROLES.runs)}/${encodeURIComponent(runId)}`) } }),
        });
        void refresh();
      } else if (result.status === KNOWN_TASK_ACTION_STATUSES.BLOCKED && result.issue != null) {
        setNotice({ kind: "gate", details: gateOf(result.issue) });
      } else {
        fail(task, action, undefined, result.issue ?? undefined);
      }
    } catch (e) {
      if (e instanceof ApiError && e.code === ERROR_CODES.SDD_GATE_BLOCKED) setNotice({ kind: "gate", details: e.details as unknown as SddGateBlockedDetails });
      else if (e instanceof ApiError && e.code === ERROR_CODES.SDD_TASK_CHANGED) {
        onTaskChanged?.(task, e.details as unknown as SddTaskChangedDetails);
        void refresh();
      } else fail(task, action, e);
    } finally {
      setBusyKey(null);
    }
  };

  const showIssue = (issue: Issue) => {
    if (issue.code === ERROR_CODES.SDD_GATE_BLOCKED) setNotice({ kind: "gate", details: gateOf(issue) });
  };

  const importAndRun = (n: Extract<RunNotice, { kind: "error" }>) => {
    if (ctx.projectId === null) return;
    const target = n.view?.notImported;
    const items = target?.kind !== undefined && target.id !== undefined ? [{ kind: target.kind, id: target.id }] : undefined;
    copy.open({
      direction: "import",
      project: ctx.projectId,
      start: items === undefined ? "pick" : "plan",
      ...(items === undefined ? {} : { items }),
      submitStyle: "run",
      onApplied: (outcome) => {
        if (outcome.allOk) {
          setNotice(null);
          void run(n.task, n.action);
        }
      },
    });
  };

  return { run, showIssue, notice, dismiss: () => setNotice(null), busyKey, importAndRun, dialog: copy.dialog };
}
