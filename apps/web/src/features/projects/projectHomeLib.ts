import type { ProjectView } from "@agent-console/contracts/projects";
import type { ConversationSummary, Run } from "@agent-console/contracts";
import { KNOWN_PROJECT_STATUSES } from "@agent-console/contracts/constants";
import { folderHomeMessages as m } from "./folderHomeMessages";

/** 배너 한 개의 종류. 같은 종류는 한 화면에 하나뿐이다. */
export type BannerKind = "folder" | "records" | "manifest" | "readonly" | "gitignore" | "network" | "archived";
/** 배너 버튼이 부르는 동작. 실제 처리는 호출한 쪽(홈 화면)이 맡는다. */
export type BannerAction = "recheck" | "repath" | "setFolder" | "unregister" | "copyManifestPath" | "recreateManifest" | "copyRecordsPath" | "copyBackupPath" | "appendGitignore" | "reregister";

export interface BannerSpec {
  /** 안정된 id(키·테스트용) */
  id: string;
  kind: BannerKind;
  tone: "danger" | "warning" | "info";
  title: string;
  body: string;
  /** 앞쪽이 primary */
  actions: readonly BannerAction[];
}

const FOLDER_PROBLEMS: ReadonlySet<string> = new Set([
  KNOWN_PROJECT_STATUSES.FOLDER_MISSING,
  KNOWN_PROJECT_STATUSES.NOT_A_DIRECTORY,
  KNOWN_PROJECT_STATUSES.NO_ACCESS,
  KNOWN_PROJECT_STATUSES.FOLDER_UNSET,
  KNOWN_PROJECT_STATUSES.FOLDER_CONFLICT,
]);

/** 구성 폴더 이름(`{dir}`). 서버 값이 없으면 호출한 쪽이 준 대체 문구. */
function dirOf(view: ProjectView, fallback: string): string {
  const d = view.config_dir;
  return d === undefined || d === null || d.trim() === "" ? fallback : d;
}

/** 기록 배너의 이유별 제목. 모르는 이유는 서버 메시지 원문. */
function recordsReasonTitle(view: ProjectView): string {
  const reason = view.records_issue?.details?.["reason"];
  if (typeof reason === "string" && Object.hasOwn(m.recordsReason, reason)) return m.recordsReason[reason] ?? m.problem.recordsUnknown;
  return view.records_issue?.message ?? m.problem.recordsUnknown;
}

/** 폴더 문제 배너(상태 → 제목·본문·버튼, screen-projects §6.1 표). */
function folderBanner(view: ProjectView, dirFallback: string): BannerSpec | null {
  const path = view.project.folder ?? "";
  switch (view.status) {
    case KNOWN_PROJECT_STATUSES.FOLDER_MISSING:
      return { id: "folder", kind: "folder", tone: "danger", title: m.problem.missingTitle, body: m.problem.missingBody(path, dirOf(view, dirFallback)), actions: ["repath", "recheck", "unregister"] };
    case KNOWN_PROJECT_STATUSES.NOT_A_DIRECTORY:
      return { id: "folder", kind: "folder", tone: "danger", title: m.problem.notDirTitle, body: m.problem.notDirBody(path), actions: ["repath", "recheck", "unregister"] };
    case KNOWN_PROJECT_STATUSES.NO_ACCESS:
      return { id: "folder", kind: "folder", tone: "danger", title: m.problem.noAccessTitle, body: m.problem.noAccessBody(path), actions: ["recheck", "repath", "unregister"] };
    case KNOWN_PROJECT_STATUSES.FOLDER_UNSET:
      return { id: "folder", kind: "folder", tone: "warning", title: m.problem.unsetTitle, body: m.problem.unsetBody, actions: ["setFolder", "unregister"] };
    case KNOWN_PROJECT_STATUSES.FOLDER_CONFLICT:
      return { id: "folder", kind: "folder", tone: "warning", title: m.problem.conflictTitle, body: m.problem.conflictBody(path), actions: ["repath", "unregister"] };
    default:
      return null;
  }
}

/**
 * 프로젝트 홈의 배너 목록(위에서 아래 순서). 순서와 조건은 screen-projects §4.3:
 * 폴더 문제 → 기록 상태 → 설정 파일 오류 → 읽기 전용 → 안내 줄(.gitignore 오래됨·네트워크 드라이브).
 * 모르는 `status`는 일반 경고 하나. 같은 원인(폴더 없음)의 기록 배너는 따로 그리지 않는다. 보관된 프로젝트는 안내 한 줄뿐이다.
 */
export function problemBanners(view: ProjectView, dirFallback: string): BannerSpec[] {
  if (view.project.archived === true) {
    return [{ id: "archived", kind: "archived", tone: "info", title: m.problem.archivedNote, body: "", actions: ["reregister"] }];
  }
  const out: BannerSpec[] = [];
  const known = FOLDER_PROBLEMS.has(view.status) || view.status === KNOWN_PROJECT_STATUSES.READY || view.status === KNOWN_PROJECT_STATUSES.MANIFEST_INVALID;
  const folder = folderBanner(view, dirFallback);
  if (folder !== null) out.push(folder);
  else if (!known) {
    out.push({ id: "folder", kind: "folder", tone: "warning", title: m.problem.unknownTitle(view.status), body: view.status_detail ?? "", actions: ["recheck", "repath", "unregister"] });
  }

  const reason = view.records_issue?.details?.["reason"];
  const sameCause = folder !== null && reason === "folder_missing";
  const state = view.records_state ?? "ready";
  if (!sameCause && (state === "newer" || (state !== "absent" && state !== "ready"))) {
    if (state === "newer") {
      out.push({ id: "records", kind: "records", tone: "warning", title: m.problem.recordsNewerTitle, body: m.problem.recordsNewerBody, actions: [] });
    } else {
      const actions: BannerAction[] = [];
      if (reason === "folder_missing") actions.push("repath", "recheck");
      else if (reason === "corrupt") actions.push(...(view.records_issue?.details?.["path"] ? (["copyRecordsPath"] as const) : []), "recheck");
      else if (reason === "migration_failed") actions.push(...(view.records_issue?.details?.["backup_path"] ? (["copyBackupPath"] as const) : []), "recheck");
      else if (reason === "link_disabled") {
        /* 안내만 */
      } else actions.push("recheck");
      out.push({
        id: "records",
        kind: "records",
        tone: reason === "link_disabled" ? "info" : "danger",
        title: recordsReasonTitle(view),
        body: reason === "corrupt" || reason === "migration_failed" ? "" : (view.records_issue?.message ?? ""),
        actions,
      });
    }
  }

  if (view.status === KNOWN_PROJECT_STATUSES.MANIFEST_INVALID) {
    out.push({
      id: "manifest",
      kind: "manifest",
      tone: "danger",
      title: m.problem.manifestTitle,
      body: m.problem.manifestBody(dirOf(view, dirFallback), view.status_detail ?? null),
      actions: ["recheck", "copyManifestPath", "recreateManifest"],
    });
  }
  if (view.status === KNOWN_PROJECT_STATUSES.READY && view.config_writable === false) {
    out.push({ id: "readonly", kind: "readonly", tone: "warning", title: m.problem.readonlyTitle, body: m.problem.readonlyBody(dirOf(view, dirFallback)), actions: ["recheck", "repath"] });
  }

  for (const issue of view.issues ?? []) {
    if (issue.code === "project.gitignore_outdated") {
      out.push({ id: "gitignore", kind: "gitignore", tone: "info", title: m.problem.gitignoreOutdated(dirOf(view, dirFallback)), body: "", actions: ["appendGitignore"] });
    } else if (issue.code === "project.network_fs") {
      out.push({ id: "network", kind: "network", tone: "info", title: m.problem.networkFs, body: "", actions: [] });
    }
  }
  return out;
}

/** 한 번에 펼쳐 보이는 배너 수(나머지는 "외 n건"). */
export const MAX_VISIBLE_BANNERS = 3;

/** 설정 파일(매니페스트) 전체 경로: `<폴더>/<구성 폴더>/project.yaml`. 구분자는 폴더 경로가 쓴 것을 따른다. */
export function manifestPath(view: ProjectView): string | null {
  const folder = view.project.folder;
  const dir = view.config_dir;
  if (folder === null || folder === "" || dir === undefined || dir === null || dir === "") return null;
  const sep = folder.includes("\\") && !folder.includes("/") ? "\\" : "/";
  return `${folder.replace(/[\\/]+$/, "")}${sep}${dir}${sep}project.yaml`;
}

/** 기록·구성 같은 읽기를 막는 상태인가(폴더를 읽을 수 없음): 구성 표를 한 줄 안내로 바꾼다. */
export function configUnreadable(view: ProjectView): boolean {
  return FOLDER_PROBLEMS.has(view.status);
}

/** 상대 시간("방금"·"5분 전"·"3시간 전"·"2일 전"). 한 달이 넘으면 날짜. 입력은 초 단위 시각. */
export function relativeTime(nowMs: number, epochSeconds: number | null | undefined): string {
  if (epochSeconds === null || epochSeconds === undefined) return "";
  const diff = Math.max(0, Math.floor((nowMs - epochSeconds * 1000) / 1000));
  if (diff < 45) return m.home.relative.now;
  if (diff < 3600) return m.home.relative.minutes(Math.max(1, Math.round(diff / 60)));
  if (diff < 86400) return m.home.relative.hours(Math.round(diff / 3600));
  if (diff < 86400 * 30) return m.home.relative.days(Math.round(diff / 86400));
  return new Date(epochSeconds * 1000).toLocaleDateString("ko");
}

/** 최근 활동 한 줄(채팅·실행을 합친 목록). */
export interface ActivityRow {
  key: string;
  origin: "chat" | "run";
  title: string;
  at: number;
  /** 실행의 공용 상태 문자열(서버 값 그대로) */
  status?: string;
  /** 상세로 가는 경로 이름: 채팅은 대화 id, 실행은 run id */
  id: string;
}

/** 채팅과 실행을 시간 내림차순으로 합치고 `limit`개로 자른다. */
export function mergeActivity(chats: readonly ConversationSummary[], runs: readonly Run[], limit = 8): ActivityRow[] {
  const rows: ActivityRow[] = [
    ...chats.map((c): ActivityRow => ({ key: `chat:${c.id}`, origin: "chat", id: c.id, title: c.title ?? "", at: c.updated_at })),
    ...runs.map((r): ActivityRow => ({ key: `run:${r.id}`, origin: "run", id: r.id, title: r.graph_id ?? r.id, at: r.started_at ?? r.created_at, status: r.status })),
  ];
  return rows.sort((a, b) => b.at - a.at).slice(0, limit);
}
