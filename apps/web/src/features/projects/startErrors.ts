import { ApiError } from "@agent-console/api-client";
import { ERROR_CODES } from "@agent-console/contracts";
import { NODE_PATH_SEPARATOR } from "../../lib/nodePath";
import { targetPickerMessages as m } from "./targetPickerMessages";

/** 시작 오류 배너가 붙이는 해결 버튼 종류. 화면이 이 값을 보고 동작을 연결한다(서버가 준 `fix`는 따로 그대로 그린다). */
export type StartFix = "pickProject" | "importAndRun" | "toLibrary" | "repath" | "checkInHome" | "retry" | "openSettings" | "none";

export interface StartErrorView {
  tone: "warning" | "danger" | "info";
  message: string;
  fix: StartFix;
  /** 422 `project.not_imported`의 대상(가져와서 실행에 쓴다) */
  /** `project.outside_folder`의 문제 노드(`details.paths[0].node_id`). 경로형이면 `head`가 팀 노드, `rest`가 안쪽 경로 */
  node?: { id: string; head: string; rest: string };
  notImported?: { projectId: string | undefined; kind: string | undefined; id: string | undefined; inLibrary: boolean };
}

/** 폴더 문제로 시작할 수 없는 코드들(409). 서버 코드 문자열은 `ERROR_CODES`에서 읽는다. */
const FOLDER_CODES: ReadonlySet<string> = new Set([ERROR_CODES.PROJECT_FOLDER_MISSING]);

const str = (v: unknown): string | undefined => (typeof v === "string" && v !== "" ? v : undefined);

/** `project.records_unavailable`의 `details.reason` → 배너(표 하나, screen-projects §5.4 시작·실행 오류 표). */
const RECORDS_REASONS: Readonly<Record<string, Omit<StartErrorView, "notImported">>> = {
  readonly: { tone: "warning", message: m.error.recordsReadonly, fix: "repath" },
  folder_missing: { tone: "warning", message: m.error.recordsFolderMissing, fix: "repath" },
  newer: { tone: "warning", message: m.error.recordsNewer, fix: "none" },
  busy: { tone: "warning", message: m.error.recordsBusy, fix: "retry" },
  link_disabled: { tone: "info", message: m.error.recordsBroken, fix: "checkInHome" },
};
const RECORDS_BROKEN: Omit<StartErrorView, "notImported"> = { tone: "danger", message: m.error.recordsBroken, fix: "checkInHome" };

/**
 * 시작·실행 요청이 실패했을 때 배너로 보일 내용. 알려진 프로젝트 오류만 풀고 나머지는 null(호출자가 서버 메시지를 그대로 보인다).
 * 서버 이슈 코드의 문구는 만들지 않고, 위 표의 문구와 해결 버튼 종류만 정한다.
 * @param nameOf `project.not_imported` 배너에 보일 구성 이름(종류·id로 찾는다, 없으면 id)
 */
export function startErrorView(error: unknown, nameOf: (kind: string | undefined, id: string | undefined) => string = (_k, id) => id ?? ""): StartErrorView | null {
  if (!(error instanceof ApiError)) return null;
  const d = error.details;
  switch (error.code) {
    case ERROR_CODES.PROJECT_REQUIRED:
      return { tone: "warning", message: m.error.required, fix: "pickProject" };
    case ERROR_CODES.PROJECT_NOT_IMPORTED: {
      const inLibrary = d["in_library"] === true;
      const kind = str(d["kind"]);
      const id = str(d["id"]);
      const name = nameOf(kind, id);
      return {
        tone: inLibrary ? "warning" : "danger",
        message: inLibrary ? m.error.notImportedInLibrary(name) : m.error.notImportedMissing(name),
        fix: inLibrary ? "importAndRun" : "toLibrary",
        notImported: { projectId: str(d["project_id"]), kind, id, inLibrary },
      };
    }
    case ERROR_CODES.PROJECT_MANIFEST_INVALID:
      return { tone: "danger", message: m.error.manifestInvalid, fix: "checkInHome" };
    case ERROR_CODES.PROJECT_RECORDS_UNAVAILABLE: {
      const reason = str(d["reason"]);
      return RECORDS_REASONS[reason ?? ""] ?? RECORDS_BROKEN;
    }
    case ERROR_CODES.PROJECT_CONFIG_READONLY:
      return { tone: "warning", message: m.error.configReadonly, fix: "repath" };
    case ERROR_CODES.PROJECT_OUTSIDE_FOLDER: {
      // details.paths[]{value, resolved, pointer, layer, node_id}: 첫 항목을 보이고 나머지는 서버 메시지에 있다
      const first = Array.isArray(d["paths"]) ? (d["paths"][0] as Record<string, unknown> | undefined) : undefined;
      const nodeId = str(first?.["node_id"]);
      const at = nodeId?.indexOf(NODE_PATH_SEPARATOR) ?? -1;
      const node = nodeId === undefined ? undefined : at > 0 ? { id: nodeId, head: nodeId.slice(0, at), rest: nodeId.slice(at + 1) } : { id: nodeId, head: nodeId, rest: "" };
      const base = m.error.outsideFolder(str(first?.["value"]) ?? "", str(first?.["layer"]) ?? "");
      return { tone: "danger", message: node !== undefined && node.rest !== "" ? base + m.error.outsideFolderAt(node.id) : base, fix: "openSettings", ...(node === undefined ? {} : { node }) };
    }
    default:
      return FOLDER_CODES.has(error.code) ? { tone: "danger", message: m.error.folderUnusable, fix: "repath" } : null;
  }
}
