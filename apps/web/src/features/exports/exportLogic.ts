import { ApiError } from "@agent-console/api-client";
import type { ExporterDescriptor, ExportFile, ExportRequest, ExportSelection, Issue } from "@agent-console/contracts";
import type { FormError } from "@agent-console/schema-form";

/** localStorage 키(마지막으로 고른 형식·충돌 처리). */
export const STORAGE_KEYS = { exporter: "ac.export.exporter", onConflict: "ac.export.on_conflict" } as const;

/** 폴더 쓰기 충돌 처리 선택지(계약 `ExportConflictPolicy`). 기본은 데이터를 잃지 않는 쪽. */
export const CONFLICT_POLICIES = ["fail", "skip", "overwrite"] as const;
export type ConflictPolicy = (typeof CONFLICT_POLICIES)[number];
export const DEFAULT_CONFLICT_POLICY: ConflictPolicy = "fail";

export function parseConflictPolicy(raw: string | null | undefined): ConflictPolicy {
  return CONFLICT_POLICIES.find((p) => p === raw) ?? DEFAULT_CONFLICT_POLICY;
}

/** 동작 값(계약 `ExportFileAction`) -> 표시 어휘(아이콘 + 톤). 모르는 값은 원문 + 중립(호출 측이 처리). */
export const ACTION_LOOKS: Readonly<Record<string, { icon: string; tone: "success" | "warning" | "neutral" | "danger" }>> = {
  create: { icon: "＋", tone: "success" },
  overwrite: { icon: "↻", tone: "warning" },
  skip: { icon: "⊘", tone: "neutral" },
  conflict: { icon: "⚠", tone: "danger" },
};

export interface PlanSummary {
  count: number;
  bytes: number;
  /** 동작별 개수(모르는 동작도 키로 들어간다) */
  byAction: Record<string, number>;
}

export function summarizeFiles(files: readonly ExportFile[]): PlanSummary {
  const byAction: Record<string, number> = {};
  let bytes = 0;
  for (const f of files) {
    const action = f.action ?? "create";
    byAction[action] = (byAction[action] ?? 0) + 1;
    bytes += f.size;
  }
  return { count: files.length, bytes, byAction };
}

/** 덮어쓰기 확인에 보일 개수: 덮어씀 + 충돌. */
export function overwriteCount(files: readonly ExportFile[]): number {
  return files.filter((f) => f.action === "overwrite" || f.action === "conflict").length;
}

/** `severity=error` 이슈가 있으면 내보낼 수 없다(서버가 그렇게 말한 것). */
export function blockingIssues(warnings: readonly Issue[] | undefined): Issue[] {
  return (warnings ?? []).filter((w) => w.severity === "error");
}

export function exporterSupports(descriptor: Pick<ExporterDescriptor, "kinds"> | undefined, kind: string): boolean {
  return descriptor?.kinds?.includes(kind) ?? false;
}

export type SubdirProblem = "absolute" | "dotdot" | "empty_segment" | "forbidden_char";

/** 하위 폴더 즉시 검사(최종 판단은 서버). 빈 값은 루트 바로 아래라 문제 없다. */
export function checkSubdir(subdir: string): SubdirProblem | undefined {
  const value = subdir.trim();
  if (value === "") return undefined;
  if (/^([/\\]|[A-Za-z]:([/\\]|$))/.test(value)) return "absolute";
  if (/[<>:"|?*]/.test(value)) return "forbidden_char";
  const segments = value.replace(/\\/g, "/").split("/");
  if (segments.includes("..")) return "dotdot";
  // 끝의 `/`는 허용하지 않는다(빈 구성요소)
  if (segments.some((s) => s === "")) return "empty_segment";
  return undefined;
}

export interface FlowInput {
  exporter: string;
  items: readonly ExportSelection[];
  options: Record<string, unknown>;
  root?: string | undefined;
  subdir?: string | undefined;
}

/** 미리보기·보관 파일 요청. 폴더 목적지는 둘 다 있을 때만 싣는다. */
export function buildRequest(input: FlowInput): ExportRequest {
  const request: ExportRequest = { exporter: input.exporter, items: [...input.items], options: input.options };
  if (input.root !== undefined && input.root !== "") {
    request.root = input.root;
    request.subdir = (input.subdir ?? "").trim();
  }
  return request;
}

export interface PlanErrorMap {
  /** 옵션 폼 필드 오류(경로는 옵션 객체 기준) */
  options: FormError[];
  /** 항목 인덱스 -> 서버 메시지 */
  items: Map<number, string>;
  /** 위치를 모르는 서버 메시지 */
  other: string[];
  /** 옵션·항목에 연결돼 ②로 보낼 만한가 */
  routable: boolean;
}

/** 422 `details.issues[]`(path `/options/<키>`, `/items/<i>/kind`)를 화면 위치에 연결한다. */
export function mapPlanError(error: unknown): PlanErrorMap {
  const out: PlanErrorMap = { options: [], items: new Map(), other: [], routable: false };
  if (!(error instanceof ApiError)) return out;
  const raw = error.details["issues"];
  const issues = Array.isArray(raw) ? (raw as Partial<Issue>[]) : [];
  if (issues.length === 0) {
    out.other.push(error.message);
    return out;
  }
  for (const issue of issues) {
    const message = typeof issue.message === "string" ? issue.message : error.message;
    const path = typeof issue.path === "string" ? issue.path : "";
    const item = /^\/items\/(\d+)(\/|$)/.exec(path);
    if (path.startsWith("/options")) {
      out.options.push({ path: path.slice("/options".length), message, severity: issue.severity === "warning" ? "warning" : "error" });
      out.routable = true;
    } else if (item?.[1] !== undefined) {
      out.items.set(Number(item[1]), message);
      out.routable = true;
    } else out.other.push(message);
  }
  return out;
}

/** 쓰기 오류 -> 하위 폴더 필드 오류 문구(서버 422 path가 `/subdir`일 때). 아니면 undefined. */
export function subdirErrorOf(error: unknown): string | undefined {
  if (!(error instanceof ApiError) || error.status !== 422) return undefined;
  const raw = error.details["issues"];
  if (!Array.isArray(raw)) return undefined;
  const hit = (raw as Partial<Issue>[]).find((i) => i.path === "/subdir");
  return hit?.message ?? undefined;
}

/** 409 `already_exists`의 충돌 경로 목록. */
export function conflictPathsOf(error: unknown): string[] {
  if (!(error instanceof ApiError)) return [];
  const paths = error.details["paths"];
  return Array.isArray(paths) ? paths.filter((p): p is string => typeof p === "string") : [];
}

/** 항목 목록에서 중복 없이 더한다(종류+id 기준). */
export function addItem(items: readonly ExportSelection[], item: ExportSelection): ExportSelection[] {
  return items.some((i) => i.kind === item.kind && i.id === item.id) ? [...items] : [...items, item];
}
