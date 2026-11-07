import { describe, expect, it } from "vitest";
import { ApiError } from "@agent-console/api-client";
import { startErrorView } from "./startErrors";

const err = (code: string, details: Record<string, unknown> = {}, status = 409) => new ApiError(status, { code, message: "서버 메시지", details });

describe("startErrorView: 시작 오류 → 배너·해결 버튼 표 (screen-projects §5.4)", () => {
  it.each([
    ["project.required", {}, "warning", "pickProject"],
    ["project.not_imported", { in_library: true, id: "g1" }, "warning", "importAndRun"],
    ["project.not_imported", { in_library: false, id: "g1" }, "danger", "toLibrary"],
    ["project.folder_missing", {}, "danger", "repath"],
    ["project.manifest_invalid", {}, "danger", "checkInHome"],
    ["project.records_unavailable", { reason: "readonly" }, "warning", "repath"],
    ["project.records_unavailable", { reason: "folder_missing" }, "warning", "repath"],
    ["project.records_unavailable", { reason: "newer" }, "warning", "none"],
    ["project.records_unavailable", { reason: "corrupt" }, "danger", "checkInHome"],
    ["project.records_unavailable", { reason: "migration_failed" }, "danger", "checkInHome"],
    ["project.records_unavailable", { reason: "link_disabled" }, "info", "checkInHome"],
    ["project.records_unavailable", { reason: "busy" }, "warning", "retry"],
    ["project.config_readonly", {}, "warning", "repath"],
    ["project.outside_folder", { paths: [{ value: "/etc/x", resolved: "/etc/x", pointer: "/p", layer: "사용자", node_id: "n" }] }, "danger", "openSettings"],
  ])("%s %j → %s / %s", (code, details, tone, fix) => {
    const v = startErrorView(err(code, details));
    expect(v).toMatchObject({ tone, fix });
    expect(v?.message).not.toBe("");
  });

  it("not_imported는 대상 종류·id·in_library를 돌려주고 이름은 호출자가 찾는다", () => {
    const v = startErrorView(err("project.not_imported", { project_id: "a", kind: "k", id: "g1", in_library: true }), (_k, id) => `이름-${id}`);
    expect(v?.message).toContain("이름-g1");
    expect(v?.notImported).toEqual({ projectId: "a", kind: "k", id: "g1", inLibrary: true });
  });

  it("outside_folder 문구에 경로와 출처 층을 넣고, 모르는 records 이유는 danger", () => {
    expect(startErrorView(err("project.outside_folder", { paths: [{ value: "/etc/x", resolved: "/etc/x", pointer: "/p", layer: "사용자", node_id: "n" }] }))?.message).toBe("‘/etc/x’는 프로젝트 폴더 밖입니다 (출처: 사용자)");
    expect(startErrorView(err("project.records_unavailable", { reason: "weird" }))?.tone).toBe("danger");
  });

  it("outside_folder의 중첩 팀 경로 node_id는 첫 조각을 head로, 나머지를 rest로 풀고 문구에 경로를 보인다", () => {
    const v = startErrorView(err("project.outside_folder", { paths: [{ value: "/etc/x", resolved: "/etc/x", pointer: "/p", layer: "사용자", node_id: "T/T/a" }] }));
    expect(v?.node).toEqual({ id: "T/T/a", head: "T", rest: "T/a" });
    expect(v?.message).toContain("T/T/a");
  });

  it("알려지지 않은 오류와 ApiError가 아닌 값은 null(호출자가 서버 메시지를 그대로 보인다)", () => {
    expect(startErrorView(err("something_else"))).toBeNull();
    expect(startErrorView(new Error("x"))).toBeNull();
  });
});
