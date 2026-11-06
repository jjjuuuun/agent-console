import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import { getContractSchema } from "@agent-console/contracts";
import type { ModuleInfo } from "@agent-console/contracts";
import type { WikiRulesView } from "@agent-console/contracts/wiki";
import { LONG, INFO, project, projectView, setup } from "./wikiTestSetup";
import { collectEnumUi, propertyTitles, xuiVariables } from "./rulesSchema";
import { ruleFileLinks } from "./WikiRulesEditor";

afterEach(cleanup);

const mod = (roles: string[]): ModuleInfo => ({ id: "m-any", kind: "k", version: "0.0.1", status: "active", web_roles: roles });
const RULE = { kind: "k-rules", id: "ra", name: "규칙 가", description: "", write_rules: [{ id: "w-1", action: "reject", message: "막음", deny_patterns: ["x+"], applies_to: ["a/**"] }], lint_rules: [], page_templates: [{ id: "t-1", title: "결정", file: "templates/t.md", path: "d/{slug}" }], instructions: { file: "instr.md" } };
const view = (over: Partial<WikiRulesView> = {}): WikiRulesView => ({ rules: RULE as never, version_hash: "rv1", used_by: [], issues: [], ...over });
const LIST = [{ id: "ra", name: "규칙 가", counts: { write: 1, lint: 0, templates: 1 }, has_instructions: true }];
const apiError = (status: number, code: string) => new ApiError(status, { code, message: "서버 문장", details: {} });

function rulesSetup(path: string, wiki: Record<string, unknown> = {}, extra: Record<string, unknown> = {}) {
  return setup(path, {
    modules: [mod(["wiki:rules", "projects", "settings"])],
    ...extra,
    wiki: {
      getWikiInfo: vi.fn(async () => INFO),
      listWikiRules: vi.fn(async () => LIST),
      getWikiRules: vi.fn(async () => ({ value: view(), version_hash: "rv1" })),
      listWikiRulesFiles: vi.fn(async () => [{ path: "instr.md", size: 3 }]),
      readWikiRulesFile: vi.fn(async () => ({ text: "지침 글", contentType: "text/markdown", size: 3, version_hash: "rv1" })),
      checkWikiRules: vi.fn(async () => ({ issues: [] })),
      ...wiki,
    },
  });
}

describe("공용 구성 › 위키 규칙", () => {
  it("규칙이 없으면 빈 목록 안내가 나오고 예시 규칙을 만들어 두지 않는다", async () => {
    rulesSetup("/wiki-rules", { listWikiRules: vi.fn(async () => []) });
    expect(await screen.findByTestId("wiki-rules-empty", {}, LONG)).toBeTruthy();
    expect(screen.getByText("위키 규칙이 없습니다")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "새 위키 규칙" })).toHaveLength(1);
  });

  it("위키 모듈 없이 규칙 역할만 켜져 있어도(정의 모듈 꺼짐) 목록과 편집기가 열린다", async () => {
    rulesSetup("/wiki-rules/ra");
    expect(await screen.findByTestId("wiki-rule-editor", {}, LONG)).toBeTruthy();
    expect(screen.getAllByText("규칙 가").length).toBeGreaterThan(0);
    expect(screen.getByText("쓰기 1 · 점검 0 · 틀 1")).toBeTruthy();
  });

  it("목록 행을 누르면 /wiki-rules/:id 로 가고 ?prj= 는 이어진다", async () => {
    const { router } = rulesSetup("/wiki-rules?prj=p1");
    fireEvent.click(await screen.findByRole("button", { name: /규칙 가/ }, LONG));
    await waitFor(() => expect(router.state.location.pathname).toBe("/wiki-rules/ra"), LONG);
    expect(router.state.location.search).toContain("prj=p1");
  });

  it("새 위키 규칙: 이름만으로 만들고 만든 규칙의 편집기로 간다", async () => {
    const created = view({ rules: { ...RULE, id: "rn", name: "새 규칙" } as never });
    const createWikiRules = vi.fn(async () => ({ value: created, version_hash: "rv0" }));
    const { router } = rulesSetup("/wiki-rules", { createWikiRules });
    fireEvent.click(await screen.findByRole("button", { name: "새 위키 규칙" }, LONG));
    const dialog = await screen.findByRole("dialog", {}, LONG);
    fireEvent.click(within(dialog).getByRole("button", { name: "만들기" }));
    expect(await within(dialog).findByText("이름을 적으세요")).toBeTruthy();
    fireEvent.change(within(dialog).getByLabelText(/^이름/), { target: { value: "새 규칙" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "만들기" }));
    await waitFor(() => expect(createWikiRules).toHaveBeenCalledWith({ name: "새 규칙" }), LONG);
    await waitFor(() => expect(router.state.location.pathname).toBe("/wiki-rules/rn"), LONG);
  });

  it("규칙 탭의 스키마 폼에서 고치면 저장 안 됨이 되고 저장은 If-Match(정의 버전)로 PUT 한다", async () => {
    const putWikiRules = vi.fn(async () => ({ value: view(), version_hash: "rv2" }));
    const { wiki } = rulesSetup("/wiki-rules/ra", { putWikiRules });
    const name = await screen.findByLabelText("이름", { selector: "input" }, LONG);
    fireEvent.change(name, { target: { value: "고친 이름" } });
    expect(await screen.findByText("저장 안 됨")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(wiki.putWikiRules).toHaveBeenCalledTimes(1), LONG);
    const call = putWikiRules.mock.calls[0] as unknown as [string, { name: string }, string];
    expect(call[0]).toBe("ra");
    expect(call[1].name).toBe("고친 이름");
    expect(call[2]).toBe("rv1");
  });

  it("초안이 바뀌고 600ms 뒤 서버 검사가 자동으로 돌고 서버 메시지가 그대로 보인다(저장은 막지 않는다)", async () => {
    const checkWikiRules = vi.fn(async () => ({ issues: [{ severity: "error", code: "x", message: "서버가 말한 오류", path: "/write_rules/0/id" }] }));
    rulesSetup("/wiki-rules/ra", { checkWikiRules });
    const name = await screen.findByLabelText("이름", { selector: "input" }, LONG);
    fireEvent.change(name, { target: { value: "다른 이름" } });
    expect(checkWikiRules).not.toHaveBeenCalled();
    await waitFor(() => expect(checkWikiRules).toHaveBeenCalledTimes(1), LONG);
    expect(await screen.findByTestId("wiki-rule-check", {}, LONG)).toBeTruthy();
    expect(screen.getByText("경고 0 · 오류 1")).toBeTruthy();
    expect(screen.getByRole("button", { name: "저장" }).getAttribute("aria-disabled")).toBeNull();
  });

  it("[검사]는 바로 검사하고 문제가 없으면 그렇게 보인다", async () => {
    const { wiki } = rulesSetup("/wiki-rules/ra");
    fireEvent.click(await screen.findByRole("button", { name: "검사" }, LONG));
    await waitFor(() => expect(wiki.checkWikiRules).toHaveBeenCalledWith({ rules: expect.objectContaining({ id: "ra" }), files: ["instr.md"] }), LONG);
    expect(await screen.findByText("문제가 없습니다", {}, LONG)).toBeTruthy();
  });

  it("충돌(412)이면 충돌 배너가 나온다", async () => {
    const putWikiRules = vi.fn(async () => { throw apiError(412, "version_conflict"); });
    rulesSetup("/wiki-rules/ra", { putWikiRules });
    fireEvent.change(await screen.findByLabelText("이름", { selector: "input" }, LONG), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    expect(await screen.findByTestId("wiki-rule-conflict", {}, LONG)).toBeTruthy();
  });

  it("본문 파일 탭: 규칙이 가리키는데 없는 파일은 파일 없음 + [만들기]이고 연결 안 된 파일은 알린다", async () => {
    rulesSetup("/wiki-rules/ra?tab=files", { listWikiRulesFiles: vi.fn(async () => [{ path: "stray.md", size: 1 }]), readWikiRulesFile: vi.fn(async () => ({ text: "x", contentType: "text/markdown", size: 1, version_hash: "rv1" })) });
    expect((await screen.findAllByText("파일 없음", {}, LONG)).length).toBe(2);
    expect(screen.getByRole("button", { name: "instr.md 파일 만들기" })).toBeTruthy();
    expect(screen.getByTestId("wiki-rule-unlinked").textContent).toContain("stray.md");
    expect(screen.getByTestId("wiki-rule-instructions-note")).toBeTruthy();
  });

  it("쓰는 위키가 있으면 머리 아래에 이름이 나오고 지우기 확인에 경고가 붙는다", async () => {
    const getWikiRules = vi.fn(async () => ({ value: view({ used_by: [{ id: "w1", name: "노트" }, { id: "w2" }] }), version_hash: "rv1" }));
    rulesSetup("/wiki-rules/ra?prj=p1", { getWikiRules, deleteWikiRules: vi.fn(async () => undefined) });
    expect((await screen.findByTestId("wiki-rule-usedby", {}, LONG)).textContent).toContain("이 규칙을 쓰는 위키: 노트, w2");
    fireEvent.click(screen.getByRole("button", { name: "더보기" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "지우기" }, LONG));
    expect((await screen.findByTestId("wiki-rule-delete-usedby", {}, LONG)).textContent).toContain("2개에서 규칙이 빠진 것으로 표시됩니다");
  });

  it("읽기 전용 폴더에서는 [새 위키 규칙]과 저장이 aria-disabled이다", async () => {
    rulesSetup("/wiki-rules/ra?prj=p1", {}, { projects: [projectView(project("p1"), { config_writable: false })] });
    expect((await screen.findByRole("button", { name: "새 위키 규칙" }, LONG)).getAttribute("aria-disabled")).toBe("true");
    expect((await screen.findByRole("button", { name: "저장" }, LONG)).getAttribute("aria-disabled")).toBe("true");
    expect(await screen.findByTestId("wiki-rule-readonly", {}, LONG)).toBeTruthy();
  });

  it("스키마 x-ui 위젯: 걸 페이지는 글롭 칸(mono + 도움말), 경로 틀에는 스키마가 준 변수 칩이 붙는다", async () => {
    rulesSetup("/wiki-rules/ra?section=write_rules");
    expect(await screen.findAllByText("확장자 없는 페이지 경로 기준", {}, LONG)).toBeTruthy();
    cleanup();
    rulesSetup("/wiki-rules/ra?section=page_templates");
    expect(await screen.findByRole("button", { name: "{slug} 넣기" }, LONG)).toBeTruthy();
  });
});

describe("규칙 스키마 읽기(순수)", () => {
  const schema = getContractSchema("WikiRulesDefinition");
  it("x-ui.enum_labels·enum_tones를 스키마 어디서든 모은다(필드 이름을 모른 채)", () => {
    const { labels, tones } = collectEnumUi(schema);
    expect(tones["reject"]).toBe("danger");
    expect(labels["warn"]).toEqual(expect.any(String));
  });
  it("x-ui를 바꾸면 코드 수정 없이 라벨·톤이 바뀐다", () => {
    const patched = { a: { "x-ui": { enum_labels: { zz: "새 라벨" }, enum_tones: { zz: "success" } } } };
    expect(collectEnumUi(patched)).toEqual({ labels: { zz: "새 라벨" }, tones: { zz: "success" } });
    expect(collectEnumUi({})).toEqual({ labels: {}, tones: {} });
  });
  it("최상위 속성 제목과 x-ui.variables 읽기", () => {
    expect(propertyTitles({ properties: { a: { title: "에이" }, b: {} } })).toEqual({ a: "에이" });
    expect(xuiVariables({ "x-ui": { variables: [{ name: "n", description: "d" }, { nope: 1 }] } })).toEqual([{ name: "n", description: "d" }]);
    expect(xuiVariables({})).toEqual([]);
  });
  it("본문 파일 연결은 데이터(fileFields)가 가리키는 속성에서 읽는다", () => {
    const fields = { single: ["one"], list: ["many"], fileKey: "f", labelKeys: ["n"] };
    expect(ruleFileLinks({ one: { f: "a.md" }, many: [{ f: "b.md", n: "비" }, { n: "파일 없음" }] }, fields)).toEqual([
      { file: "a.md", kind: "instructions" },
      { file: "b.md", kind: "template", label: "비" },
    ]);
  });
});
