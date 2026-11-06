import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NoProjectState } from "./NoProjectState";
import { PROJECT_START_STEPS, buildProjectStartSteps } from "./projectStartSteps";

afterEach(cleanup);

describe("NoProjectState", () => {
  it("제목·본문·[폴더 추가]가 있고 링크 버튼은 주소가 있을 때만 그린다", () => {
    const onAddFolder = vi.fn();
    const { rerender } = render(<MemoryRouter><NoProjectState onAddFolder={onAddFolder} /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "프로젝트 폴더를 먼저 추가하세요" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "공용 구성 화면으로" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "폴더 추가" }));
    expect(onAddFolder).toHaveBeenCalled();
    rerender(<MemoryRouter><NoProjectState onAddFolder={onAddFolder} libraryHref="/teams" /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "공용 구성 화면으로" }).getAttribute("href")).toBe("/teams");
  });
  it("문구는 덮어쓸 수 있다", () => {
    render(<MemoryRouter><NoProjectState onAddFolder={() => {}} messages={{ title: "다른 제목" }} /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "다른 제목" })).toBeTruthy();
  });
});

describe("시작하기 4단계(데이터)", () => {
  const counts = { projects: 0, libraryTeams: 0, projectTeams: 0, projectConversations: 0 };
  const actions = { folder: { onAction: () => {} }, library: { to: "/teams" }, import: { to: "/projects/a" }, chat: { to: "/chat" } };
  it("순서는 폴더 → 공용 구성 → 가져오기 → 대화이고 전제가 안 된 단계는 버튼 없이 이유를 보인다", () => {
    const steps = buildProjectStartSteps({ counts, actions });
    expect(steps.map((s) => s.id)).toEqual(PROJECT_START_STEPS.map((d) => d.id));
    expect(steps[0]?.onAction).toBeTypeOf("function");
    expect(steps[2]?.to).toBeUndefined();
    expect(steps[2]?.hint).toBe("먼저 폴더를 추가하세요");
    expect(steps[3]?.hint).toBe("먼저 폴더를 추가하세요");
  });
  it("폴더가 있으면 가져오기가 열리고, 공용 구성이 이미 있으면 건너뜀 표시", () => {
    const steps = buildProjectStartSteps({ counts: { ...counts, projects: 1, libraryTeams: 2 }, actions });
    expect(steps.map((s) => s.done)).toEqual([true, true, false, false]);
    expect(steps[1]?.hint).toBe("공용 구성이 있습니다");
    expect(steps[2]?.to).toBe("/projects/a");
    expect(steps[3]?.hint).toBe("먼저 공용 구성을 만들거나 이 프로젝트에서 새로 만드세요");
  });
  it("꺼진 화면(actions에 없는 단계)은 빠진다", () => {
    const steps = buildProjectStartSteps({ counts, actions: { folder: actions.folder, chat: actions.chat } });
    expect(steps.map((s) => s.id)).toEqual(["folder", "chat"]);
  });
  it("개수를 모르면 완료로 치지 않는다", () => {
    const steps = buildProjectStartSteps({ counts: { projects: undefined, libraryTeams: undefined, projectTeams: undefined, projectConversations: undefined }, actions });
    expect(steps.every((s) => !s.done)).toBe(true);
  });
});
