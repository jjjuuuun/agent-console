import type { FolderCheck, FolderPickResult } from "@agent-console/contracts/projects";
import { describe, expect, test } from "vitest";

import { folderCapabilities, folderCheckData, folderCheckOutcome, folderErrorOutcome, folderPickOutcome, logFilterFor } from "@agent-console/projects";

const ok: FolderCheck = {
  input: "~/work/app",
  path: "/home/me/work/app",
  exists: true,
  is_dir: true,
  readable: true,
  writable: true,
  can_create: false,
  status: "ok",
};
const names = { projectName: (id: string) => ({ p1: "결제" })[id as "p1"] };

describe("폴더 확인 → picker", () => {
  test("정상: status·conflict를 빼고 필드 그대로", () => {
    expect(folderCheckOutcome(ok)).toEqual({
      kind: "checked",
      check: { input: "~/work/app", path: "/home/me/work/app", exists: true, is_dir: true, readable: true, writable: true, can_create: false },
    });
  });

  test("빠진 필드는 안전한 기본값, 선택 필드는 있을 때만", () => {
    expect(folderCheckData({ input: "x", status: "invalid", problem: "relative" })).toEqual({
      input: "x", path: null, exists: false, is_dir: false, readable: false, writable: false, can_create: false, problem: "relative",
    });
    const d = folderCheckData({ ...ok, nearest_existing: "/home", link: true, hidden: false });
    expect(d).toMatchObject({ nearest_existing: "/home", link: true, hidden: false });
  });

  test("같은 폴더 = taken (이름 표 → 이름, 없으면 id), 보관 표시", () => {
    const base = { ...ok, status: "taken", conflict: { project_id: "p1", relation: "same" } };
    expect(folderCheckOutcome(base, names)).toMatchObject({ kind: "taken", projectId: "p1", name: "결제" });
    expect(folderCheckOutcome(base)).toMatchObject({ name: "p1" });
    const archivedByStatus = folderCheckOutcome({ ...base, status: "taken_archived" }, names);
    expect(archivedByStatus).toMatchObject({ kind: "taken", archived: true });
    const archivedByField = folderCheckOutcome({ ...base, conflict: { project_id: "p1", relation: "same", archived: true } });
    expect(archivedByField).toMatchObject({ archived: true });
    expect((folderCheckOutcome(base) as { archived?: boolean }).archived).toBeUndefined();
  });

  test.each(["parent", "child"] as const)("겹침 %s = overlap + 겹치는 폴더", (relation) => {
    const out = folderCheckOutcome({ ...ok, status: `overlap_${relation}`, conflict: { project_id: "p1", relation, folder: "/srv" } }, names);
    expect(out).toMatchObject({ kind: "overlap", relation, projectId: "p1", name: "결제", path: "/srv" });
  });

  test("모르는 관계는 일반 확인으로", () => {
    expect(folderCheckOutcome({ ...ok, conflict: { project_id: "p1", relation: "weird" } }).kind).toBe("checked");
  });
});

describe("거절 오류 → picker", () => {
  test("원격 접속 차단", () => {
    expect(folderErrorOutcome({ code: "folders.remote_disabled" })).toEqual({ kind: "remote_disabled" });
  });
  test("등록 409: taken / overlaps", () => {
    expect(folderErrorOutcome({ code: "project.folder_taken", details: { project_id: "p1", archived: true } }, names)).toEqual({
      kind: "taken", projectId: "p1", name: "결제", archived: true,
    });
    expect(folderErrorOutcome({ code: "project.folder_overlaps", details: { project_id: "p1", relation: "child", folder: "/a/b" } })).toEqual({
      kind: "overlap", relation: "child", projectId: "p1", name: "p1", path: "/a/b",
    });
  });
  test("그 밖의 오류는 바꾸지 않는다", () => {
    expect(folderErrorOutcome({ code: "network_error" })).toBeNull();
    expect(folderErrorOutcome({ code: "project.folder_taken" })).toBeNull();
  });
});

describe("선택 창 응답 → picker", () => {
  test("picked: check와 outcome을 채워 다시 요청하지 않게", () => {
    const r: FolderPickResult = { status: "picked", path: "/home/me/work/app", check: ok, provider: "zenity" };
    const out = folderPickOutcome(r);
    expect(out.status).toBe("picked");
    expect(out.path).toBe("/home/me/work/app");
    expect(out.check?.path).toBe("/home/me/work/app");
    expect(out.outcome?.kind).toBe("checked");
  });
  test("picked + 이미 등록 = outcome이 taken", () => {
    const out = folderPickOutcome({ status: "picked", path: "/x", check: { ...ok, status: "taken", conflict: { project_id: "p1", relation: "same" } } }, names);
    expect(out.outcome).toMatchObject({ kind: "taken", name: "결제" });
  });
  test.each(["cancelled", "unavailable", "busy", "timeout", "failed"])("%s는 그대로", (status) => {
    expect(folderPickOutcome({ status })).toEqual({ status });
  });
  test("모르는 상태는 failed", () => {
    expect(folderPickOutcome({ status: "exploded" }).status).toBe("failed");
  });
  test("picked인데 check가 없으면 경로만(picker가 확인 요청)", () => {
    expect(folderPickOutcome({ status: "picked", path: "/p" })).toEqual({ status: "picked", path: "/p" });
  });
  test("고르기 방법", () => {
    expect(folderCapabilities({ native_dialog: true, browse: true })).toEqual({ browse: true, native_dialog: true });
    expect(folderCapabilities({ reason: "remote" })).toEqual({ browse: true, native_dialog: false, reason: "remote" });
    expect(folderCapabilities({ browse: false, native_dialog: false, reason: null })).toEqual({ browse: false, native_dialog: false, reason: null });
  });
});

describe("로그 필터", () => {
  test("LogSessionSummary.project_id 기준: 필터는 project=<id>", () => {
    expect(logFilterFor("p1").filter).toEqual({ project: "p1" });
  });
});
