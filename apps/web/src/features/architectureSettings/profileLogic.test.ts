import { describe, expect, it } from "vitest";
import type { ArchitectureProfileList } from "@agent-console/contracts";
import { buildRows, deleteProfile, disableProfile, removeKey, setProfile, suggestCloneId } from "./profileLogic";
import { lineOfPath, newProfileSkeleton, parseProfileYaml, profileToYaml } from "./yamlProfile";

// 프로필 id·출처는 이 테스트 안의 임의 값이다.
const info = (id: string, origin: string, extra: object = {}) => ({ id, title: `제목-${id}`, origin, issues: 1, cells: 3, edges: 2, ...extra });
const list = (profiles: ReturnType<typeof info>[]): ArchitectureProfileList => ({ profiles, default_profile: null, include_defaults: true });
const isDefault = { isDefault: (o: string) => o === "default", user: "user" };

describe("buildRows", () => {
  it("서버 목록을 그대로 행으로 만들고 끈 프로필은 따로 모은다", () => {
    const r = buildRows(list([info("a", "default"), info("b", "plugin:x"), info("c", "default", { disabled: true })]), { c: null }, { c: null }, true, isDefault);
    expect(r.rows.map((x) => x.id)).toEqual(["a", "b"]);
    expect(r.disabled.map((x) => x.id)).toEqual(["c"]);
    expect(r.rows[0]).toMatchObject({ origin: "default", issues: 1, cells: 3, dirty: false });
  });
  it("같은 id의 사용자 프로필은 한 행이고 덮어씀 출처를 가진다", () => {
    const body = { title: "내 것" };
    const r = buildRows(list([info("a", "user", { overrides: "default" })]), { a: body }, { a: body }, true, isDefault);
    expect(r.rows).toHaveLength(1);
    expect(r.rows[0]).toMatchObject({ origin: "user", overrides: "default", title: "내 것", dirty: false });
  });
  it("저장 전 변경은 dirty이고 서버 수치를 모른다", () => {
    const r = buildRows(list([]), { n: { title: "새" } }, {}, true, isDefault);
    expect(r.rows[0]).toMatchObject({ id: "n", origin: "user", dirty: true, issues: null, cells: null });
  });
  it("초안에서 기본 프로필 사용을 끄면 기본 출처 행이 빠지고 사용자 행은 남는다", () => {
    const r = buildRows(list([info("a", "default"), info("u", "user")]), { u: { title: "u" } }, { u: { title: "u" } }, false, isDefault);
    expect(r.rows.map((x) => x.id)).toEqual(["u"]);
  });
  it("초안에서 덮어쓰기를 지우면 원래 출처로 돌아간다", () => {
    const r = buildRows(list([info("a", "user", { overrides: "default" })]), {}, { a: { title: "x" } }, true, isDefault);
    expect(r.rows[0]).toMatchObject({ origin: "default", dirty: true });
  });
});

describe("프로필 편집 함수", () => {
  it("끄기는 null, 지우기는 저장된 적 있으면 null·없으면 키 삭제, 되돌리기는 키 삭제", () => {
    expect(disableProfile({ a: { t: 1 } }, "b")).toEqual({ a: { t: 1 }, b: null });
    expect(deleteProfile({ a: { t: 1 } }, "a", { a: { t: 1 } })).toEqual({ a: null });
    expect(deleteProfile({ a: { t: 1 } }, "a", {})).toEqual({});
    expect(removeKey({ a: null, b: 1 }, "a")).toEqual({ b: 1 });
    expect(setProfile({}, "a", { t: 1 })).toEqual({ a: { t: 1 } });
  });
  it("복제 id는 이미 있으면 번호를 붙인다", () => {
    expect(suggestCloneId("a", new Set(["a"]))).toBe("a-custom");
    expect(suggestCloneId("a", new Set(["a-custom", "a-custom-2"]))).toBe("a-custom-3");
  });
});

describe("YAML", () => {
  it("왕복하고 형식 오류는 줄 번호를 준다", () => {
    const text = profileToYaml({ t: "가", n: { k: [1, 2] } });
    expect(parseProfileYaml(text)).toEqual({ ok: true, value: { t: "가", n: { k: [1, 2] } } });
    const bad = parseProfileYaml("a: [1\nb: 2");
    expect(bad.ok).toBe(false);
    expect(parseProfileYaml("- x").ok).toBe(false);
    expect(parseProfileYaml("").ok).toBe(true);
  });
  it("경로로 줄을 찾는다", () => {
    expect(lineOfPath("a: 1\nb:\n  c: 2\n", "b.c")).toBe(3);
    expect(lineOfPath("a: 1\n", "zz")).toBeNull();
  });
});

describe("새 프로필 골격", () => {
  it("계약 스키마의 기본 속성으로 제목·캔버스·칸 하나를 만든다", () => {
    const sk = newProfileSkeleton("내 제목", "c1");
    expect(Object.values(sk)).toContain("내 제목");
    const objs = Object.values(sk).filter((v): v is Record<string, unknown> => typeof v === "object" && v !== null);
    expect(objs.some((o) => Object.keys(o).length === 1 && Object.keys(o)[0] === "c1")).toBe(true);
    expect(objs.some((o) => Object.values(o).every((x) => typeof x === "number"))).toBe(true);
  });
});
