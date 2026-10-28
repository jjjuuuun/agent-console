import { describe, expect, test } from "vitest";

import {
  ABILITY_TABLE,
  DEFAULT_PROJECT_MESSAGES,
  PROJECT_ACTIONS,
  RETIRED_TERMS,
  configDirLabel,
  createProjectsText,
  projectAbilities,
  sameSpace,
  spaceLabel,
  spaceParam,
  spaceQuery,
  statusInfo,
  toSpaceRef,
  type ProjectStateInput,
} from "@agent-console/projects";

const view = (status: string, extra: Partial<ProjectStateInput> = {}): ProjectStateInput => ({ status, ...extra });

describe("상태 표현", () => {
  test.each([
    ["ready", "projects.status.ready", "ok", true],
    ["folder_missing", "projects.status.folder_missing", "danger", false],
    ["not_a_directory", "projects.status.not_a_directory", "danger", false],
    ["no_access", "projects.status.no_access", "danger", false],
    ["folder_unset", "projects.status.folder_unset", "warning", false],
    ["folder_conflict", "projects.status.folder_conflict", "warning", false],
    ["manifest_invalid", "projects.status.manifest_invalid", "danger", false],
  ])("%s", (status, key, tone, plain) => {
    const info = statusInfo(view(status));
    expect(info.label).toEqual({ key });
    expect(info.tone).toBe(tone);
    expect(info.plain).toBe(plain);
  });

  test("모르는 상태는 원문과 일반 경고", () => {
    const info = statusInfo(view("brand_new"));
    expect(info.label).toEqual({ key: "projects.status.unknown", params: { status: "brand_new" } });
    expect(info.tone).toBe("warning");
    expect(createProjectsText()(info.label)).toBe("프로젝트 상태: brand_new");
  });

  test("config_writable이 없으면 쓸 수 있는 것으로 본다. false면 읽기 전용 칩", () => {
    expect(statusInfo(view("ready")).plain).toBe(true);
    expect(statusInfo(view("ready", { config_writable: true })).plain).toBe(true);
    expect(statusInfo(view("ready", { config_writable: false })).label).toEqual({ key: "projects.status.readonly" });
  });

  test("보관은 다른 상태보다 앞선다", () => {
    expect(statusInfo(view("folder_missing", { project: { archived: true } })).label).toEqual({ key: "projects.status.archived" });
  });
});

describe("능력 표 (§6.0)", () => {
  const allowed = (v: ProjectStateInput) =>
    Object.fromEntries(PROJECT_ACTIONS.map((a) => [a, projectAbilities(v)[a].allowed])) as Record<string, boolean>;

  test("ready + 쓰기 가능 = 전부", () => {
    expect(Object.values(allowed(view("ready"))).every(Boolean)).toBe(true);
  });

  test("읽기 전용: 시작·가져오기·편집이 막히고 이유 문구가 붙는다", () => {
    const a = projectAbilities(view("ready", { config_writable: false }));
    expect(a.start_chat).toEqual({ allowed: false, reason: { key: "projects.blocked.records_readonly" } });
    expect(a.copy_in.reason).toEqual({ key: "projects.blocked.copy_in" });
    expect(a.edit.reason).toEqual({ key: "projects.blocked.edit" });
    expect(a.save_to_library.allowed).toBe(true);
    expect(a.view_records.allowed).toBe(true);
  });

  test("폴더를 읽을 수 없으면 기록 보기·경로 다시 지정·등록 해제만", () => {
    for (const s of ["folder_missing", "not_a_directory", "no_access", "folder_unset", "folder_conflict"]) {
      const on = PROJECT_ACTIONS.filter((x) => projectAbilities(view(s))[x].allowed);
      expect(on).toEqual(["view_records", "repath", "unregister"]);
    }
  });

  test("설정 파일 오류는 읽을 수 있는 것만, 이유는 설정 파일 문구", () => {
    const a = projectAbilities(view("manifest_invalid"));
    expect(a.start_run).toEqual({ allowed: false, reason: { key: "projects.blocked.manifest" } });
    expect(a.save_to_library.allowed && a.collect_logs.allowed).toBe(true);
  });

  test("보관은 기록 보기만", () => {
    const a = projectAbilities(view("ready", { project: { archived: true } }));
    expect(PROJECT_ACTIONS.filter((x) => a[x].allowed)).toEqual(["view_records"]);
    expect(a.start_chat.reason).toEqual({ key: "projects.blocked.archived" });
  });

  test("기록 쓰기 불가는 상태와 별개로 쓰기를 막는다", () => {
    const a = projectAbilities(view("ready"), { recordsWritable: false });
    expect(a.start_chat.allowed).toBe(false);
    expect(a.view_records.allowed).toBe(true);
    expect(a.collect_logs.allowed).toBe(true);
  });

  test("모르는 상태는 보수적으로 막고 상태 원문을 이유에 넣는다", () => {
    const a = projectAbilities(view("brand_new"));
    expect(a.start_chat.reason).toEqual({ key: "projects.status.blocked_reason", params: { status: "brand_new" } });
    expect(a.view_records.allowed).toBe(true);
  });

  test("표(데이터)를 바꾸면 결과가 바뀐다 — 코드에 상태별 분기가 없다", () => {
    const table = { ...ABILITY_TABLE, ready: new Set(["view_records" as const]) };
    expect(projectAbilities(view("ready"), { table }).start_chat.allowed).toBe(false);
  });

  test("구성 폴더 이름: 값이 없으면 대체 문구", () => {
    expect(configDirLabel(".x", "구성 폴더")).toBe(".x");
    expect(configDirLabel(undefined, "구성 폴더")).toBe("구성 폴더");
    expect(configDirLabel("  ", "구성 폴더")).toBe("구성 폴더");
  });
});

describe("공간", () => {
  test("공용은 인자를 보내지 않는다 (회귀: 지금 요청과 같은 주소)", () => {
    for (const none of [null, undefined, "", "  "]) {
      expect(spaceParam(none)).toBeUndefined();
      expect(spaceQuery(none)).toEqual({});
      expect(toSpaceRef(none)).toEqual({ project_id: null });
    }
    expect(spaceQuery("p1")).toEqual({ project: "p1" });
    expect(toSpaceRef(" p1 ")).toEqual({ project_id: "p1" });
    expect(sameSpace(null, "")).toBe(true);
    expect(sameSpace("a", "b")).toBe(false);
  });

  test("칩 데이터: 이름 표가 있으면 이름, 없으면 id", () => {
    expect(spaceLabel(null)).toMatchObject({ kind: "library", label: { key: "space.library" } });
    expect(spaceLabel("p1", new Map([["p1", "결제"]])).label).toEqual({ key: "space.project", params: { name: "결제" } });
    expect(spaceLabel("p1", {}).name).toBe("p1");
    const text = createProjectsText();
    expect(text(spaceLabel("p1", { p1: "결제" }).label)).toBe("프로젝트: 결제");
  });
});

describe("메시지 표", () => {
  test("기본 문구에 폐기어(U-16)가 없다", () => {
    for (const [key, value] of Object.entries(DEFAULT_PROJECT_MESSAGES)) {
      for (const term of RETIRED_TERMS) expect(value, `${key}: ${term}`).not.toContain(term);
    }
  });
  test("덮어쓰기와 모르는 키", () => {
    const text = createProjectsText({ "space.library": "라이브러리" });
    expect(text("space.library")).toBe("라이브러리");
    expect(text("nope.key")).toBe("nope.key");
    expect(text("copy.status.renamed", { id: "x-2" })).toBe("새 이름으로 추가함 → x-2");
  });
});
