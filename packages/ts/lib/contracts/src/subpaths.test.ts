import { describe, expect, expectTypeOf, it } from "vitest";

import * as architecture from "@agent-console/contracts/architecture";
import type {
  ArchitectureEdge,
  ArchitectureEdgeView,
  ArchitectureMetric,
  ArchitectureView,
} from "@agent-console/contracts/architecture";
import * as chat from "@agent-console/contracts/chat";
import * as constants from "@agent-console/contracts/constants";
import type { Conversation as ChatConversation } from "@agent-console/contracts/chat";
import type { EdgeLayout, NodeLayout, ObserveSettings, WorkspaceSettings } from "@agent-console/contracts/definitions";
import * as logs from "@agent-console/contracts/logs";
import * as memory from "@agent-console/contracts/memory";
import type { MemoryEventPayload, MemoryScopeRef } from "@agent-console/contracts/memory";
import type { LogEvent, LogLane, LogSettings, LogTimeline, LogWidget } from "@agent-console/contracts/logs";
import * as modules from "@agent-console/contracts/modules";
import type { LogsIngestedMessage, ModuleInfo } from "@agent-console/contracts/modules";
import * as projects from "@agent-console/contracts/projects";
import type {
  DefinitionMove,
  FolderCheck,
  FolderCheckRequest,
  CopyApplyItem,
  CopyPlanItem,
  FolderPickResult,
  Project,
  ProjectManifest,
  ProjectNotImportedDetails,
  ProjectView,
} from "@agent-console/contracts/projects";
import type { SpaceRef } from "@agent-console/contracts/common";
import type { ConversationSessions, PostMessageRequest, QueuedMessage } from "@agent-console/contracts/chat";
import type { Run } from "@agent-console/contracts/runs";
import type { MemoryCopyRequest } from "@agent-console/contracts/memory";
import type { UsageReport } from "@agent-console/contracts/usage";

import packageJson from "../package.json";
import {
  CONTRACT_VERSIONS,
  ERROR_CODES,
  HTTP_STATUS_BY_ERROR_CODE,
  KNOWN_ISSUE_CODES,
  KNOWN_SUGGESTION_IDS,
  LOG_EVENT_ORDERS,
  LOG_PROJECT_UNGROUPED,
  USAGE_REPORT_PARTS,
  X_UI,
  X_UI_TIERS,
  contractsSchema,
  type Agent,
  type Conversation,
  type ErrorInfo,
  type Fix,
  type UsageIndicatorSettings,
} from "./index";

const pkg = packageJson as { version: string; exports: Record<string, unknown> };
const modulesOf = contractsSchema["x-modules"] as Record<string, string[]>;

describe("계약 하위 경로(@agent-console/contracts/<하위 모듈>)", () => {
  it("하위 모듈마다 package.json exports 하위 경로가 있다", () => {
    expect(Object.keys(modulesOf)).toEqual(Object.keys(CONTRACT_VERSIONS));
    for (const name of Object.keys(CONTRACT_VERSIONS)) {
      expect(pkg.exports[`./${name}`]).toEqual({
        development: `./src/generated/${name}.ts`,
        types: `./dist/src/generated/${name}.d.ts`,
        default: `./dist/src/generated/${name}.js`,
      });
    }
  });

  it("하위 경로는 그 하위 모듈의 이름·버전을 내보낸다", () => {
    expect(chat.CONTRACT_MODULE).toBe("chat");
    expect(chat.CONTRACT_VERSION).toBe(CONTRACT_VERSIONS.chat);
    expect(modules.CONTRACT_MODULE).toBe("modules");
    expect(modulesOf["chat"]).toContain("Conversation");
    expect(modulesOf["modules"]).toContain("ModuleInfo");
  });

  it("하위 경로 타입은 루트 타입과 같다", () => {
    expectTypeOf<ChatConversation>().toEqualTypeOf<Conversation>();
    expectTypeOf<ModuleInfo["status"]>().toEqualTypeOf<string>();
    expectTypeOf<NodeLayout["direction"]>().toEqualTypeOf<string | null | undefined>();
    expectTypeOf<EdgeLayout["waypoints"]>().toEqualTypeOf<{ x: number; y: number }[] | null | undefined>();
    // 요청하지 않은 부분은 null
    expectTypeOf<UsageReport["rollups"]>().toExtend<unknown[] | null | undefined>();
  });

  it("계약 버전은 패키지 버전과 같고 사용량 부분 이름은 상수다", () => {
    expect(contractsSchema["x-constants"]).toMatchObject({ CONTRACTS_VERSION: pkg.version });
    expect(USAGE_REPORT_PARTS).toEqual(["windows", "tokens"]);
  });

  it("logs 하위 경로(0.6.0): 이벤트·설정 타입과 WS logs.ingested", () => {
    expect(logs.CONTRACT_MODULE).toBe("logs");
    expect(logs.CONTRACT_VERSION).toBe(CONTRACT_VERSIONS.logs);
    expect(modulesOf["logs"]).toEqual(expect.arrayContaining(["LogEvent", "LogSettings", "LogArchive"]));
    // `from`은 JSON 키 그대로, 범주·위젯 종류는 열린 문자열
    expectTypeOf<LogEvent["from"]>().toEqualTypeOf<string[] | undefined>();
    expectTypeOf<LogEvent["category"]>().toEqualTypeOf<string>();
    expectTypeOf<LogWidget["kind"]>().toEqualTypeOf<string>();
    expectTypeOf<WorkspaceSettings["logs"]>().toEqualTypeOf<LogSettings | undefined>();
    expectTypeOf<ObserveSettings["hook_probe"]>().toEqualTypeOf<boolean | null | undefined>();
    expectTypeOf<LogsIngestedMessage["type"]>().toEqualTypeOf<"logs.ingested">();
    expectTypeOf<LogTimeline["lanes"]>().toEqualTypeOf<LogLane[] | undefined>();
    expect(LOG_EVENT_ORDERS).toEqual(["asc", "desc"]);
    expect(LOG_PROJECT_UNGROUPED).toBe("~ungrouped");
  });

  it("projects 하위 경로(0.8.0): 프로젝트·옮기기 계획, 정의 범위·오류 해결 데이터", () => {
    expect(projects.CONTRACT_MODULE).toBe("projects");
    expect(projects.CONTRACT_VERSION).toBe(CONTRACT_VERSIONS.projects);
    expect(modulesOf["projects"]).toEqual(expect.arrayContaining(["Project", "MovePlan", "DeletePlan"]));
    expect(modulesOf["definitions"]).toContain("ProjectPreferences");
    // 2.0.0(0.11.0): working_directory → folder(필수 키, 옛 파일은 null)
    expectTypeOf<Project["folder"]>().toEqualTypeOf<string | null>();
    // `from`은 JSON 키 그대로
    expectTypeOf<DefinitionMove["from"]>().toEqualTypeOf<string | null | undefined>();
    expectTypeOf<Agent["project"]>().toEqualTypeOf<string | null | undefined>();
    expectTypeOf<ErrorInfo["fix"]>().toEqualTypeOf<Fix | null | undefined>();
    expectTypeOf<UsageIndicatorSettings["value_mode"]>().toEqualTypeOf<"remaining" | "used" | undefined>();
    expect(ERROR_CODES.BACKEND_UNRESOLVED).toBe("backend.unresolved");
    expect(HTTP_STATUS_BY_ERROR_CODE["backend.unresolved"]).toBe(422);
    expect(X_UI).toBe("x-ui");
    expect(X_UI_TIERS).toEqual(["basic", "advanced"]);
  });

  it("architecture 하위 경로(0.9.0): 구조도 프로필·투영 결과, 지표 null은 0이 아니다", () => {
    expect(architecture.CONTRACT_MODULE).toBe("architecture");
    expect(architecture.CONTRACT_VERSION).toBe("1.0.0");
    expect(modulesOf["architecture"]).toEqual(
      expect.arrayContaining(["ArchitectureSettings", "ArchitectureProfile", "ArchitectureView", "ArchitectureMembership"]),
    );
    // `from`은 JSON 키 그대로, 좌표는 두 수, 지표 값은 null 가능
    expectTypeOf<ArchitectureEdge["from"]>().toEqualTypeOf<string>();
    expectTypeOf<ArchitectureEdgeView["label_at"]>().toEqualTypeOf<[number, number] | null | undefined>();
    expectTypeOf<ArchitectureMetric["value"]>().toEqualTypeOf<number | null | undefined>();
    expectTypeOf<ArchitectureMetric["status"]>().toEqualTypeOf<"observed" | "inferred" | "not_collected">();
    expectTypeOf<ArchitectureView["max_seq"]>().toEqualTypeOf<number | null | undefined>();
    expect(ERROR_CODES.ARCHITECTURE_SCOPE_TOO_LARGE).toBe("architecture.scope_too_large");
    expect(HTTP_STATUS_BY_ERROR_CODE["architecture.profile_not_found"]).toBe(404);
  });

  it("memory 하위 경로(0.10.0): 이벤트 payload에 본문·검색어 원문이 없다", () => {
    expect(memory.CONTRACT_MODULE).toBe("memory");
    expect(memory.CONTRACT_VERSION).toBe(CONTRACT_VERSIONS.memory);
    expect(modulesOf["memory"]).toEqual(
      expect.arrayContaining(["MemorySettings", "MemoryAccessConfig", "MemoryEntry", "MemoryEventPayload", "MemoryChanged"]),
    );
    expectTypeOf<MemoryScopeRef["kind"]>().toEqualTypeOf<string>();
    // 본문·검색어 원문 필드가 없다(크기·해시만)
    expectTypeOf<Extract<keyof MemoryEventPayload, "content" | "query" | "text">>().toBeNever();
    expectTypeOf<MemoryEventPayload["query_sha256"]>().toEqualTypeOf<string | null | undefined>();
    expect(constants.KNOWN_MEMORY_EVENT_TYPES).toEqual(["memory.read", "memory.search", "memory.write", "memory.delete"]);
    expect(constants.KNOWN_RUN_EVENT_TYPES).not.toContain("memory.write");
    expect(HTTP_STATUS_BY_ERROR_CODE["memory.secret_rejected"]).toBe(422);
    expect(KNOWN_ISSUE_CODES.TOOLS_DUPLICATE_NAME).toBe("tools.duplicate_name");
  });

  it("constants 하위 경로: x-constants 값만 다시 내보낸다(루트와 같은 객체)", () => {
    expect(pkg.exports["./constants"]).toEqual({
      development: "./src/generated/constants.ts",
      types: "./dist/src/generated/constants.d.ts",
      default: "./dist/src/generated/constants.js",
    });
    const xConstants = contractsSchema["x-constants"] as Record<string, unknown>;
    expect(Object.keys(constants).sort()).toEqual(Object.keys(xConstants).sort());
    for (const [name, value] of Object.entries(xConstants)) {
      expect((constants as Record<string, unknown>)[name]).toEqual(value);
    }
    expect(constants.KNOWN_ISSUE_CODES).toBe(KNOWN_ISSUE_CODES);
  });

  it("알려진 이슈 코드·제안 id(5.2R.3 후속): 열린 문자열의 이름 → 값 표", () => {
    expect(KNOWN_ISSUE_CODES.PROJECT_REFERENCES_UNAVAILABLE).toBe("project.references_unavailable");
    expect(KNOWN_ISSUE_CODES.PROJECT_DEFINITIONS_UNAVAILABLE).toBe("project.definitions_unavailable");
    expect(KNOWN_ISSUE_CODES.BACKEND_UNRESOLVED).toBe(ERROR_CODES.BACKEND_UNRESOLVED);
    expect(KNOWN_SUGGESTION_IDS.PROJECT_MOVE_TO_SHARED).toBe("project.move_to_shared");
  });

  it("프로젝트 2.0(0.11.0, 5.7R.33c)·3.0(0.12.0, 5.7R.33c2): 폴더·이슈 코드", () => {
    expect(projects.CONTRACT_VERSION).toMatch(/^3\./);
    expect(modulesOf["projects"]).toEqual(
      expect.arrayContaining(["ProjectView", "FolderCheck", "FolderListing", "AssignProjectRequest", "ProjectCounts"]),
    );
    expectTypeOf<FolderCheckRequest["exclude_project_id"]>().toEqualTypeOf<string | null | undefined>();
    expectTypeOf<FolderCheck["nearest_existing"]>().toEqualTypeOf<string | null | undefined>();
    const codes: Record<string, [string, number]> = {
      PROJECT_REQUIRED: ["project.required", 422],
      PROJECT_NOT_IMPORTED: ["project.not_imported", 422],
      PROJECT_FOLDER_MISSING: ["project.folder_missing", 409],
      PROJECT_FOLDER_TAKEN: ["project.folder_taken", 409],
      PROJECT_FOLDER_OVERLAPS: ["project.folder_overlaps", 409],
      PROJECT_OUTSIDE_FOLDER: ["project.outside_folder", 422],
      FOLDERS_REMOTE_DISABLED: ["folders.remote_disabled", 403],
    };
    for (const [name, [code, status]] of Object.entries(codes)) {
      expect((KNOWN_ISSUE_CODES as Record<string, string>)[name]).toBe(code);
      expect((ERROR_CODES as Record<string, string>)[name]).toBe(code);
      expect((HTTP_STATUS_BY_ERROR_CODE as Record<string, number>)[code]).toBe(status);
    }
    expect(constants.KNOWN_PROJECT_STATUSES.FOLDER_MISSING).toBe("folder_missing");
    expect(constants.X_PATH).toBe("x-path");
  });

  it("프로젝트 3.0(0.12.0, 5.7R.33c2): uses 삭제, 매니페스트·공간·복사·폴더 선택·메모리 복사", () => {
    expect(modulesOf["projects"]).toEqual(
      expect.arrayContaining([
        "ProjectRegistration",
        "ProjectManifest",
        "CopyPlanRequest",
        "CopyPlan",
        "CopyApplyRequest",
        "CopyApplyResult",
        "FolderCapabilities",
        "FolderPickRequest",
        "FolderPickResult",
      ]),
    );
    for (const gone of ["ProjectUse", "ProjectUsesUpdate", "UseCopyRequest", "LegacyUsesPlan"]) {
      expect(modulesOf["projects"]).not.toContain(gone);
    }
    expect(modulesOf["common"]).toContain("SpaceRef");
    expect(modulesOf["memory"]).toEqual(expect.arrayContaining(["MemoryCopyRequest", "MemoryCopyResult"]));
    expect(memory.CONTRACT_VERSION).toBe("1.1.0");
    expect(CONTRACT_VERSIONS.common).toMatch(/^1\.([6-9]|\d\d)\./);
    expectTypeOf<ProjectNotImportedDetails["in_library"]>().toEqualTypeOf<boolean | undefined>();
    expectTypeOf<ProjectView["config_writable"]>().toEqualTypeOf<boolean | undefined>();
    expectTypeOf<ProjectView["kinds"]>().toEqualTypeOf<string[] | undefined>();
    expectTypeOf<ProjectManifest["id"]>().toEqualTypeOf<string>();
    expectTypeOf<SpaceRef["project_id"]>().toEqualTypeOf<string | null | undefined>();
    expectTypeOf<CopyPlanItem["target_state"]>().toEqualTypeOf<string>();
    expectTypeOf<CopyApplyItem["action"]>().toEqualTypeOf<string>();
    expectTypeOf<FolderPickResult["status"]>().toEqualTypeOf<string>();
    expectTypeOf<MemoryCopyRequest["source"]>().toEqualTypeOf<SpaceRef>();
    expect(constants.KNOWN_COPY_ACTIONS.RENAME).toBe("rename");
    expect(constants.KNOWN_COPY_TARGET_STATES.DIFFERENT).toBe("different");
    expect(constants.KNOWN_COPY_STATUSES.CONFLICT).toBe("conflict");
    expect(constants.KNOWN_FOLDER_PICK_STATUSES.BUSY).toBe("busy");
    expect(constants.KNOWN_PROJECT_STATUSES.MANIFEST_INVALID).toBe("manifest_invalid");
    expect(constants.PROJECT_MANIFEST_FORMAT).toBe(1);
    const codes: Record<string, [string, number]> = {
      PROJECT_NOT_FOUND: ["project.not_found", 404],
      PROJECT_MANIFEST_INVALID: ["project.manifest_invalid", 409],
      PROJECT_CONFIG_READONLY: ["project.config_readonly", 409],
      PROJECT_COPY_CONFLICT: ["project.copy_conflict", 409],
      FOLDERS_DIALOG_UNAVAILABLE: ["folders.dialog_unavailable", 409],
      FOLDERS_DIALOG_BUSY: ["folders.dialog_busy", 409],
      FOLDERS_DIALOG_TIMEOUT: ["folders.dialog_timeout", 409],
    };
    for (const [name, [code, status]] of Object.entries(codes)) {
      expect((KNOWN_ISSUE_CODES as Record<string, string>)[name]).toBe(code);
      expect((ERROR_CODES as Record<string, string>)[name]).toBe(code);
      expect((HTTP_STATUS_BY_ERROR_CODE as Record<string, number>)[code]).toBe(status);
    }
    expect(KNOWN_ISSUE_CODES.PROJECT_MEMORY_NETWORK_FS).toBe("project.memory_network_fs");
  });

  it("0.12.1(5.7R.33c3): 기록 공간·폴더 확인 보강 — 더하기만, 새 필드는 선택", () => {
    expect(constants.CONTRACTS_VERSION).toBe("0.12.1");
    expect(projects.CONTRACT_VERSION).toBe("3.1.0");
    expect(chat.CONTRACT_VERSION).toBe("1.2.0");
    expect(CONTRACT_VERSIONS.runs).toBe("1.5.0");
    expect(CONTRACT_VERSIONS.common).toBe("1.7.0");
    expect(modulesOf["projects"]).toEqual(
      expect.arrayContaining([
        "ExistingProjectProbe",
        "ManifestResetRequest",
        "ManifestResetResult",
        "ProjectRecordsUnavailableDetails",
        "RecordsMoveRequest",
        "RecordsMoveResult",
      ]),
    );
    expect(modulesOf["chat"]).toEqual(expect.arrayContaining(["ConversationSessions", "SessionStatus"]));
    expectTypeOf<ProjectView["records_state"]>().toEqualTypeOf<string | undefined>();
    expectTypeOf<ProjectView["records_writable"]>().toEqualTypeOf<boolean | undefined>();
    expectTypeOf<ProjectView["config_dir"]>().toEqualTypeOf<string | null | undefined>();
    expectTypeOf<FolderCheck["suggested_id"]>().toEqualTypeOf<string | null | undefined>();
    expectTypeOf<NonNullable<FolderCheck["existing"]>["definitions"]>().toEqualTypeOf<number | undefined>();
    expectTypeOf<Run["host_id"]>().toEqualTypeOf<string | null | undefined>();
    expectTypeOf<PostMessageRequest["on_missing_session"]>().toEqualTypeOf<"fail" | "fresh" | undefined>();
    expectTypeOf<QueuedMessage["held_reason"]>().toEqualTypeOf<string | null | undefined>();
    expectTypeOf<ConversationSessions["continuable"]>().toEqualTypeOf<boolean>();
    expect(constants.KNOWN_PROJECT_RECORDS_STATES.NEWER).toBe("newer");
    expect(constants.KNOWN_RECORDS_UNAVAILABLE_REASONS.LINK_DISABLED).toBe("link_disabled");
    expect(constants.KNOWN_EXISTING_PROJECT_STATES.INVALID).toBe("invalid");
    expect(constants.KNOWN_SESSION_STATES.NOT_APPLICABLE).toBe("not_applicable");
    expect(constants.KNOWN_QUEUE_HOLD_REASONS.OTHER_HOST).toBe("other_host");
    const errors: Record<string, string> = {
      PROJECT_RECORDS_UNAVAILABLE: "project.records_unavailable",
      CHAT_SESSION_UNAVAILABLE: "chat.session_unavailable",
    };
    for (const [name, code] of Object.entries(errors)) {
      expect((KNOWN_ISSUE_CODES as Record<string, string>)[name]).toBe(code);
      expect((ERROR_CODES as Record<string, string>)[name]).toBe(code);
      expect((HTTP_STATUS_BY_ERROR_CODE as Record<string, number>)[code]).toBe(409);
    }
    const info: Record<string, string> = {
      PROJECT_NETWORK_FS: "project.network_fs",
      PROJECT_GITIGNORE_OUTDATED: "project.gitignore_outdated",
      RUN_OTHER_HOST: "run.other_host",
    };
    for (const [name, code] of Object.entries(info)) {
      expect((KNOWN_ISSUE_CODES as Record<string, string>)[name]).toBe(code);
      expect((ERROR_CODES as Record<string, string>)[name]).toBeUndefined();
    }
  });
});
