import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CopyApplyRequest, CopyApplyResult, CopyPlan, CopyPlanRequest } from "@agent-console/contracts/projects";
import { createProjectsText } from "@agent-console/projects";
import { CopyPlanDialog, type CopyPlanDialogProps } from "./CopyPlanDialog";
import type { SpaceItem } from "./useSpaceItems";

afterEach(cleanup);

const text = createProjectsText();
const item = (kind: string, id: string, name = id): SpaceItem => ({ kind, kindTitle: `종류 ${kind}`, id, name, description: `${name} 설명` });
const CANDIDATES = [item("k1", "review-team", "리뷰 팀"), item("k1", "docs-team", "문서 팀"), item("k2", "pl", "기획")];

function planItem(over: Partial<NonNullable<CopyPlan["items"]>[number]> & { kind: string; id: string }): NonNullable<CopyPlan["items"]>[number] {
  return { reason: "requested", source_version: "s1", target_state: "absent", default_action: "copy", name: over.id, ...over };
}

function setup(over: Partial<CopyPlanDialogProps> = {}, plan: CopyPlan = { items: [planItem({ kind: "k1", id: "review-team" })] }, apply?: (r: CopyApplyRequest) => Promise<CopyApplyResult>) {
  // 서버처럼: include_references:false면 요청한 항목만 돌려준다
  const planCopy = vi.fn(async (r: CopyPlanRequest): Promise<CopyPlan> => (r.include_references === false ? { ...plan, items: (plan.items ?? []).filter((i) => r.items.some((x) => x.kind === i.kind && x.id === i.id)) } : plan));
  const applyCopy = vi.fn(apply ?? (async (r: CopyApplyRequest) => ({ items: r.items.map((i) => ({ kind: i.kind, id: i.id, status: i.action === "skip" ? "skipped" : i.action === "reuse" ? "reused" : "copied" })) })));
  const onClose = vi.fn();
  const onApplied = vi.fn();
  render(
    <CopyPlanDialog
      direction="import"
      projectName="결제"
      projectDir=".cfg"
      source={{ project_id: null }}
      target={{ project_id: "pay" }}
      initialStep="pick"
      candidates={CANDIDATES}
      targetItems={[{ kind: "k1", id: "docs-team" }]}
      planCopy={planCopy}
      applyCopy={applyCopy}
      text={text}
      onClose={onClose}
      onApplied={onApplied}
      {...over}
    />,
  );
  return { planCopy, applyCopy, onClose, onApplied };
}

describe("CopyPlanDialog: 고르기", () => {
  it("목록은 종류 이름 → 이름 순이고 대상에 같은 id가 있으면 칩이 붙으며, 0개 선택이면 [다음]은 aria-disabled", () => {
    setup();
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    const docs = rows.find((r) => within(r).queryByText("문서 팀") !== null) as HTMLElement;
    expect(within(docs).getByText("이 프로젝트에 같은 이름이 있음")).toBeTruthy();
    expect(within(rows[0] as HTMLElement).queryByText("이 프로젝트에 같은 이름이 있음")).toBeNull();
    expect(within(rows[2] as HTMLElement).getByText("기획")).toBeTruthy();
    expect(screen.getByRole("button", { name: "다음" }).getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByText("0개 선택")).toBeTruthy();
  });

  it("종류 드롭다운은 목록에 실제로 있는 종류에서 만들고, 검색 결과가 없으면 안내", () => {
    setup();
    const kinds = Array.from((screen.getByLabelText("종류") as HTMLSelectElement).options).map((o) => o.textContent);
    expect(kinds).toEqual(["전체", "종류 k1", "종류 k2"]);
    fireEvent.change(screen.getByRole("searchbox", { name: "검색" }), { target: { value: "zzz" } });
    expect(screen.getByText("‘zzz’와 맞는 구성이 없습니다")).toBeTruthy();
  });

  it("원본이 비면 안내와 emptyAction 링크 자리", () => {
    setup({ candidates: [], emptyAction: <a href="#x">공용 구성 화면으로</a> });
    expect(screen.getByText("공용 구성이 없습니다. 구성 화면에서 먼저 만드세요.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "공용 구성 화면으로" })).toBeTruthy();
  });

  it("체크하고 [다음] → 계획 요청에 원본·대상·항목과 include_references가 실린다", async () => {
    const { planCopy } = setup();
    fireEvent.click(screen.getByRole("checkbox", { name: "리뷰 팀" }));
    expect(screen.getByText("1개 선택")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "다음" }));
    await waitFor(() => expect(planCopy).toHaveBeenCalled());
    expect(planCopy.mock.calls[0]?.[0]).toEqual({ source: { project_id: null }, target: { project_id: "pay" }, items: [{ kind: "k1", id: "review-team" }], include_references: true });
    expect(await screen.findByText("요청한 항목 1개 · 함께 가져올 항목 0개")).toBeTruthy();
  });
});

describe("CopyPlanDialog: 계획", () => {
  const referenced = planItem({ kind: "k2", id: "pl", reason: "referenced", referenced_by: [{ kind: "k1", id: "review-team", name: "review-team" }] });

  it("기본 동작은 서버 default_action이고 같은 내용은 그대로 쓰기, 요약 줄과 제출 개수가 맞는다", async () => {
    setup(
      { initialStep: "plan", initialItems: [{ kind: "k1", id: "review-team" }] },
      { items: [planItem({ kind: "k1", id: "review-team" }), { ...referenced, target_state: "identical", default_action: "reuse" }] },
    );
    expect(await screen.findByRole("button", { name: "가져오기 (1)" })).toBeTruthy();
    expect(screen.getByText("복사 1 · 그대로 쓰기 1 · 덮어쓰기 0 · 새 이름 0 · 건너뜀 0")).toBeTruthy();
    expect(screen.getByText("‘review-team’이(가) 사용")).toBeTruthy();
  });

  it("내용이 다른 항목은 고르기 전에 [가져오기]가 aria-disabled + 이유, 덮어쓰기를 고르면 danger 줄이 뜨고 풀린다", async () => {
    const { applyCopy } = setup(
      { initialStep: "plan", initialItems: [{ kind: "k1", id: "review-team" }] },
      { items: [planItem({ kind: "k1", id: "review-team", target_state: "different", default_action: null })] },
    );
    const submit = await screen.findByRole("button", { name: "가져오기 (0)" });
    expect(submit.getAttribute("aria-disabled")).toBe("true");
    expect(screen.getAllByText("내용이 다른 항목 1개의 처리 방법을 고르세요.").length).toBeGreaterThan(0);
    const select = screen.getByLabelText(/review-team: 처리/) as HTMLSelectElement;
    expect(select.getAttribute("aria-invalid")).toBe("true");
    fireEvent.change(select, { target: { value: "overwrite" } });
    expect(screen.getByText("이 프로젝트에서 바꾼 내용이 사라집니다. 편집기의 버전 기록에서 되돌릴 수 있습니다.")).toBeTruthy();
    const ready = screen.getByRole("button", { name: "가져오기 (1)" });
    expect(ready.getAttribute("aria-disabled")).toBeNull();
    fireEvent.click(ready);
    await waitFor(() => expect(applyCopy).toHaveBeenCalled());
    expect(applyCopy.mock.calls[0]?.[0]).toMatchObject({ source: { project_id: null }, target: { project_id: "pay" }, remove_source: false, items: [{ kind: "k1", id: "review-team", action: "overwrite", source_version: "s1" }] });
  });

  it("새 이름 입력은 기본 {id}-2, 대상에 있는 id와 겹치면 오류 + 제출 막힘", async () => {
    setup(
      { initialStep: "plan", initialItems: [{ kind: "k1", id: "docs" }] },
      { items: [planItem({ kind: "k1", id: "docs", target_state: "identical", default_action: "reuse" })] },
      undefined,
    );
    const select = (await screen.findByLabelText(/docs: 처리/)) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "rename" } });
    const input = screen.getByLabelText("새 이름(id)") as HTMLInputElement;
    expect(input.value).toBe("docs-2");
    fireEvent.change(input, { target: { value: "docs-team" } });
    expect(screen.getByText("이미 있는 이름입니다.")).toBeTruthy();
    expect(screen.getByRole("button", { name: /가져오기/ }).getAttribute("aria-disabled")).toBe("true");
    fireEvent.change(input, { target: { value: "docs-b" } });
    expect(screen.getByRole("button", { name: "가져오기 (1)" }).getAttribute("aria-disabled")).toBeNull();
  });

  it("연결된 항목을 가져오지 않기로 하면 경고, 요청 항목을 건너뛰면 경고 없음", async () => {
    setup({ initialStep: "plan", initialItems: [{ kind: "k1", id: "review-team" }] }, { items: [planItem({ kind: "k1", id: "review-team" }), referenced] });
    await screen.findByText("요청한 항목 1개 · 함께 가져올 항목 1개");
    fireEvent.click(screen.getByRole("checkbox", { name: "pl 가져오기" }));
    expect(screen.getByText("‘review-team’은(는) pl가 없어 실행 전에 막힙니다")).toBeTruthy();
    fireEvent.click(screen.getByRole("checkbox", { name: "review-team 가져오기" }));
    expect(screen.getAllByText(/없어 실행 전에 막힙니다/)).toHaveLength(1);
  });

  it("함께 가져올 항목 체크를 끄면 include_references:false로 다시 계획하고 안내가 뜬다", async () => {
    const { planCopy } = setup({ initialStep: "plan", initialItems: [{ kind: "k1", id: "review-team" }] }, { items: [planItem({ kind: "k1", id: "review-team" }), referenced] });
    await screen.findByText("요청한 항목 1개 · 함께 가져올 항목 1개");
    fireEvent.click(screen.getByRole("checkbox", { name: "함께 가져올 항목도 포함" }));
    await waitFor(() => expect(planCopy).toHaveBeenCalledTimes(2));
    expect(planCopy.mock.calls[1]?.[0]).toMatchObject({ include_references: false, items: [{ kind: "k1", id: "review-team" }] });
    expect(screen.getByText("연결된 항목을 빼면 이 구성은 실행 전에 막힐 수 있습니다.")).toBeTruthy();
  });

  it("서버 warnings는 배너로, 계획 실패는 danger 줄 + [다시 시도]", async () => {
    setup({ initialStep: "plan", initialItems: [{ kind: "k1", id: "a" }] }, { items: [planItem({ kind: "k1", id: "a" })], warnings: [{ severity: "warning", code: "project.references_unavailable", message: "참조를 고칠 수 없습니다" }] });
    expect(await screen.findByText("참조를 고칠 수 없습니다")).toBeTruthy();
    cleanup();
    const failing = setup({ initialStep: "plan", initialItems: [{ kind: "k1", id: "a" }], planCopy: vi.fn(async () => { throw new Error("서버 오류"); }) });
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText(/복사 계획을 만들지 못했습니다/)).toBeTruthy();
    expect(failing.applyCopy).not.toHaveBeenCalled();
  });

  it("옛 전용 구성 옮기기: remove_source 체크가 기본 켜짐이고 요청에 실린다", async () => {
    const { applyCopy } = setup({ direction: "move", removeSourceDefault: true, initialStep: "plan", initialItems: [{ kind: "k1", id: "a" }] }, { items: [planItem({ kind: "k1", id: "a" })] });
    const box = (await screen.findByRole("checkbox", { name: "복사한 뒤 공용에서 지우기" })) as HTMLInputElement;
    expect(box.checked).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "옮기기 (1)" }));
    await waitFor(() => expect(applyCopy).toHaveBeenCalled());
    expect(applyCopy.mock.calls[0]?.[0]?.remove_source).toBe(true);
  });
});

describe("CopyPlanDialog: 결과", () => {
  it("전부 성공이면 onApplied(allOk, first)를 부르고 대화상자를 닫는다", async () => {
    const { onApplied, onClose } = setup({ initialStep: "plan", initialItems: [{ kind: "k1", id: "review-team" }] }, { items: [planItem({ kind: "k1", id: "review-team" })] });
    fireEvent.click(await screen.findByRole("button", { name: "가져오기 (1)" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(onApplied.mock.calls[0]?.[0]).toMatchObject({ allOk: true, first: { kind: "k1", id: "review-team" } });
  });

  it("conflict가 있으면 닫지 않고 부분 성공 줄 + [다시 계획]이 나오며, 그 행만 새 계획을 받아 계획 표로 돌아간다", async () => {
    const apply = vi.fn(async (r: CopyApplyRequest): Promise<CopyApplyResult> => ({
      items: r.items.map((i) => (i.id === "b" ? { kind: i.kind, id: i.id, status: "conflict" } : { kind: i.kind, id: i.id, status: "copied" })),
    }));
    const { planCopy, onClose } = setup(
      { initialStep: "plan", initialItems: [{ kind: "k1", id: "a" }, { kind: "k1", id: "b" }] },
      { items: [planItem({ kind: "k1", id: "a" }), planItem({ kind: "k1", id: "b" })] },
      apply,
    );
    fireEvent.click(await screen.findByRole("button", { name: "가져오기 (2)" }));
    expect(await screen.findByText("2개 중 1개를 가져왔습니다")).toBeTruthy();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByText(/계획 뒤에 바뀌어 적용하지 않았습니다/)).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "다시 계획" })[0] as HTMLElement);
    await waitFor(() => expect(planCopy).toHaveBeenCalledTimes(2));
    expect(planCopy.mock.calls[1]?.[0]).toMatchObject({ items: [{ kind: "k1", id: "b" }], include_references: false });
    expect(await screen.findByRole("button", { name: "가져오기 (1)" })).toBeTruthy();
  });

  it("서버 이슈가 있는 행은 메시지를 그대로 보인다", async () => {
    setup(
      { initialStep: "plan", initialItems: [{ kind: "k1", id: "a" }] },
      { items: [planItem({ kind: "k1", id: "a" })] },
      async (r) => ({ items: r.items.map((i) => ({ kind: i.kind, id: i.id, status: "failed", issue: { severity: "error", code: "x", message: "비밀 값은 저장할 수 없습니다 (/env/KEY)" } })) }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "가져오기 (1)" }));
    expect(await screen.findByText(/비밀 값은 저장할 수 없습니다 \(\/env\/KEY\)/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "닫기" })).toBeTruthy();
  });
});

describe("CopyPlanDialog: 막힌 항목", () => {
  it("blocked 항목은 선택·처리가 비활성이고 이유(issue message)를 보이며 복사로 바꿀 수 없다", async () => {
    const blockedItem = planItem({
      kind: "k1",
      id: "review-team",
      default_action: "skip",
      blocked: true,
      issues: [{ severity: "error", code: "secret.plain_found", path: "/env/KEY", message: "평문 비밀이 들어 있습니다" }],
    });
    setup({ initialStep: "plan", initialItems: [{ kind: "k1", id: "review-team" }] }, { items: [blockedItem] });
    expect(await screen.findByText("평문 비밀이 들어 있습니다")).toBeTruthy();
    expect(screen.getByText("가져올 수 없어 건너뜁니다.")).toBeTruthy();
    const box = screen.getByRole("checkbox", { name: /review-team/ }) as HTMLInputElement;
    expect(box.disabled).toBe(true);
    expect(box.checked).toBe(false);
    const sel = screen.getByRole("combobox", { name: /review-team/ }) as HTMLSelectElement;
    expect(sel.disabled).toBe(true);
    expect([...sel.options].map((o) => o.value)).toEqual(["skip"]);
  });
});
