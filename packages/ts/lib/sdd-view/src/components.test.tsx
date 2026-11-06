import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { DocumentEditor } from "./DocumentEditor";
import { DocumentNav } from "./DocumentNav";
import { GateNotice } from "./GateNotice";
import { PlanBundles } from "./PlanBundles";
import { PlanGraph } from "./PlanGraph";
import { RulesSourceBadge } from "./RulesSourceBadge";
import { SpecList } from "./SpecList";
import { TaskTable } from "./TaskTable";
import { TaskStatusMenu } from "./TaskStatusMenu";
import { TraceMatrix } from "./TraceMatrix";
import { DocumentStateChip } from "./ToneChip";
import { manyTasks, samplePlan, sampleDocuments, sampleSpecs, sampleStatuses, sampleTasks, sampleTrace } from "./testing";

afterEach(cleanup);

beforeAll(() => {
  // React Flow가 요구하는 브라우저 API(레이아웃 없는 DOM 에뮬레이터용)
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  if (!("DOMMatrixReadOnly" in globalThis)) {
    (globalThis as unknown as Record<string, unknown>).DOMMatrixReadOnly = class {
      m22 = 1;
      constructor(public transform?: string) {}
    };
  }
});

describe("SpecList", () => {
  it("빈 상태: 안내와 앱이 준 버튼을 보인다", () => {
    render(<SpecList specs={[]} emptyActions={<button type="button">새 스펙</button>} />);
    expect(screen.getByText("스펙이 없습니다")).toBeTruthy();
    expect(screen.getByRole("button", { name: "새 스펙" })).toBeTruthy();
  });
  it("불러오는 중에는 빈 안내 대신 로딩", () => {
    render(<SpecList specs={[]} loading />);
    expect(screen.getByText("불러오는 중…")).toBeTruthy();
    expect(screen.queryByText("스펙이 없습니다")).toBeNull();
  });
  it("스펙 줄: 이름 없으면 id, 진행, 문서 상태 라벨은 데이터, 누르면 열기", () => {
    const onOpen = vi.fn();
    render(<SpecList specs={sampleSpecs()} selectedId="sp1" onOpen={onOpen} />);
    expect(screen.getByText("결제")).toBeTruthy();
    expect(screen.getByText("sp2")).toBeTruthy();
    expect(screen.getByRole("progressbar", { name: "작업 1/5" })).toBeTruthy();
    expect(screen.getByText("초안")).toBeTruthy();
    expect(screen.getByText("지금 단계: 1단계")).toBeTruthy();
    fireEvent.click(screen.getByText("sp2"));
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: "sp2" }));
    expect(screen.getByText("결제").closest("button")?.getAttribute("aria-current")).toBe("true");
  });
});

describe("DocumentNav·DocumentStateChip", () => {
  it("빈 상태", () => {
    render(<DocumentNav documents={[]} />);
    expect(screen.getByText("문서가 없습니다")).toBeTruthy();
  });
  it("문서와 상태 칩, 선택, 상태 없는 문서는 칩 없음", () => {
    const onSelect = vi.fn();
    render(<DocumentNav documents={sampleDocuments()} selectedId="d-req" onSelect={onSelect} />);
    expect(screen.getByRole("button", { name: "요구, 상태: 초안" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("button", { name: "메모" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "메모" }));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: "d-note" }));
  });
  it("상태 정의가 없으면 id 원문", () => {
    const { container } = render(<DocumentStateChip state="mystery" />);
    expect(container.textContent).toBe("mystery");
    expect(container.querySelector("[data-tone]")?.getAttribute("data-tone")).toBe("neutral");
    expect(render(<DocumentStateChip state={null} />).container.textContent).toBe("");
  });
});

describe("DocumentEditor", () => {
  const doc = { id: "d1", title: "요구 문서", file: "req.md" };
  it("빈 상태: 문서를 고르라는 안내", () => {
    render(<DocumentEditor document={null} value="" />);
    expect(screen.getByText("문서를 고르세요")).toBeTruthy();
  });
  it("편집기와 마크다운 미리보기를 나란히 그린다", () => {
    const { container } = render(<DocumentEditor document={doc} value={"# 제목\n\n본문"} />);
    expect(container.querySelector(".cm-content")).toBeTruthy();
    const preview = screen.getByRole("region", { name: "미리보기" });
    expect(within(preview).getByRole("heading", { name: "제목" })).toBeTruthy();
  });
  it("보기 방식 전환: 편집만 → 미리보기만", () => {
    const { container } = render(<DocumentEditor document={doc} value="x" />);
    fireEvent.click(screen.getByRole("button", { name: "편집" }));
    expect(screen.queryByRole("region", { name: "미리보기" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "미리보기" }));
    expect(container.querySelector(".cm-content")).toBeNull();
    expect(screen.getByRole("region", { name: "미리보기" })).toBeTruthy();
  });
  it("미리보기는 원시 HTML을 실행하지 않는다", () => {
    const { container } = render(<DocumentEditor document={doc} value={"<img src=x onerror=alert(1)>\n\n<script>1</script>"} defaultMode="preview" />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });
  it("읽기 전용: 이유를 보이고 저장을 막는다", () => {
    const onSave = vi.fn();
    const { container } = render(<DocumentEditor document={doc} value="x" readOnly readOnlyReason="폴더에 쓸 수 없습니다" dirty onSave={onSave} />);
    expect(screen.getByText("폴더에 쓸 수 없습니다")).toBeTruthy();
    expect((screen.getByRole("button", { name: "저장" }) as HTMLButtonElement).disabled).toBe(true);
    expect(container.querySelector(".cm-content")?.getAttribute("contenteditable")).toBe("false");
  });
  it("저장: 바뀐 내용이 있을 때만 켜지고 누르면 onSave", () => {
    const onSave = vi.fn();
    const { rerender } = render(<DocumentEditor document={doc} value="x" onSave={onSave} />);
    expect((screen.getByRole("button", { name: "저장" }) as HTMLButtonElement).disabled).toBe(true);
    rerender(<DocumentEditor document={doc} value="x" dirty onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    expect(onSave).toHaveBeenCalledTimes(1);
  });
  it("충돌: 경고와 두 선택지를 주고 저장은 막는다", () => {
    const onReload = vi.fn();
    const onOverwrite = vi.fn();
    const onSave = vi.fn();
    render(<DocumentEditor document={doc} value="x" dirty conflict onReload={onReload} onOverwrite={onOverwrite} onSave={onSave} />);
    expect(screen.getByRole("alert").textContent).toContain("다른 곳에서 문서가 바뀌었습니다");
    expect((screen.getByRole("button", { name: "저장" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "최신 내용 불러오기" }));
    fireEvent.click(screen.getByRole("button", { name: "내 변경으로 덮어쓰기" }));
    expect(onReload).toHaveBeenCalled();
    expect(onOverwrite).toHaveBeenCalled();
    expect(onSave).not.toHaveBeenCalled();
  });
  it("읽기 전용이면 충돌에서도 덮어쓰기가 꺼진다", () => {
    render(<DocumentEditor document={doc} value="x" readOnly conflict onOverwrite={() => undefined} />);
    expect((screen.getByRole("button", { name: "내 변경으로 덮어쓰기" }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("파일 없음: 자동으로 만들지 않고 버튼만 준다", () => {
    const onCreate = vi.fn();
    const { container } = render(<DocumentEditor document={doc} value="" missing onCreateMissing={onCreate} />);
    expect(screen.getByText("req.md 파일이 사라졌습니다. 앱은 파일을 대신 만들지 않습니다.")).toBeTruthy();
    expect(container.querySelector(".cm-content")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "빈 파일로 만들기" }));
    expect(onCreate).toHaveBeenCalled();
  });
  it("점검 결과를 서버 문구 그대로 보인다", () => {
    render(<DocumentEditor document={doc} value="x" issues={[{ severity: "warning", code: "sdd.secret_suspect", message: "비밀 의심", line: 3 }]} />);
    expect(screen.getByText("sdd.secret_suspect")).toBeTruthy();
    expect(screen.getByText(/비밀 의심/)).toBeTruthy();
  });
  it("IME 조합 중에는 저장이 잠기고 안내가 뜬다", () => {
    const { container } = render(<DocumentEditor document={doc} value="x" dirty onSave={() => undefined} />);
    const content = container.querySelector(".cm-content") as HTMLElement;
    act(() => {
      fireEvent.compositionStart(content);
    });
    expect((screen.getByRole("button", { name: "저장" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("입력 중에는 저장을 미룹니다")).toBeTruthy();
    act(() => {
      fireEvent.compositionEnd(content);
    });
    expect((screen.getByRole("button", { name: "저장" }) as HTMLButtonElement).disabled).toBe(false);
  });
  it("마크다운이 아닌 언어는 미리보기 없이 편집만", () => {
    render(<DocumentEditor document={doc} value="{}" language="json" />);
    expect(screen.queryByRole("region", { name: "미리보기" })).toBeNull();
    expect(screen.queryByRole("group", { name: "보기 방식" })).toBeNull();
  });
});

describe("TaskTable", () => {
  const statuses = sampleStatuses();
  it("빈 상태", () => {
    render(<TaskTable tasks={[]} statuses={statuses} />);
    expect(screen.getByText("작업이 없습니다")).toBeTruthy();
  });
  it("문법 없음: 표 대신 안내와 규칙 열기", () => {
    const onOpenRules = vi.fn();
    render(<TaskTable tasks={sampleTasks()} statuses={statuses} syntaxEmpty onOpenRules={onOpenRules} />);
    expect(screen.getByText("작업 문법이 없습니다")).toBeTruthy();
    expect(screen.queryByRole("list", { name: "작업 표" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "규칙 열기" }));
    expect(onOpenRules).toHaveBeenCalled();
  });
  it("단계 묶음과 상태 라벨(데이터)을 그린다", () => {
    render(<TaskTable tasks={sampleTasks()} statuses={statuses} />);
    expect(screen.getByRole("button", { name: /1단계 단계 접기·펼치기, 1\/2/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "작업 T1의 상태 바꾸기: 끝" })).toBeTruthy();
    expect(screen.getByText("단계 없음")).toBeTruthy();
  });
  it("단계 접기", () => {
    render(<TaskTable tasks={sampleTasks()} statuses={statuses} />);
    fireEvent.click(screen.getByRole("button", { name: /^1단계 단계 접기·펼치기/ }));
    expect(screen.queryByText("작업 T1")).toBeNull();
    expect(screen.getByText("작업 T3")).toBeTruthy();
  });
  it("상태 메뉴: 고르면 onStatusChange(낙관적으로 바꾸지 않음)", () => {
    const onStatusChange = vi.fn();
    render(<TaskTable tasks={sampleTasks()} statuses={statuses} onStatusChange={onStatusChange} />);
    fireEvent.click(screen.getByRole("button", { name: "작업 T2의 상태 바꾸기: 열림" }));
    fireEvent.click(screen.getByRole("menuitemradio", { name: "진행" }));
    expect(onStatusChange).toHaveBeenCalledWith(expect.objectContaining({ key: "T2", line_hash: "h-T2" }), "s-doing");
    expect(screen.getByRole("button", { name: "작업 T2의 상태 바꾸기: 열림" })).toBeTruthy();
  });
  it("읽기 전용: 상태 칩이 버튼이 아니다", () => {
    render(<TaskTable tasks={sampleTasks()} statuses={statuses} readOnly />);
    expect(screen.queryByRole("button", { name: /상태 바꾸기/ })).toBeNull();
    expect(screen.getAllByText("열림").length).toBeGreaterThan(0);
  });
  it("관문에 막힘: 버튼은 보이되 열리지 않고 이유가 설명으로 붙는다", () => {
    render(<TaskTable tasks={sampleTasks()} statuses={statuses} blockedReason="승인 전에는 바꿀 수 없습니다" />);
    const btn = screen.getAllByRole("button", { name: /상태 바꾸기/ })[0] as HTMLElement;
    expect(btn.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(btn);
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.getElementById(btn.getAttribute("aria-describedby") ?? "")?.textContent).toBe("승인 전에는 바꿀 수 없습니다");
  });
  it("줄 충돌: 최신 줄을 보이고 닫을 수 있다", () => {
    const onDismiss = vi.fn();
    render(<TaskTable tasks={sampleTasks()} statuses={statuses} conflicts={{ T2: { task_key: "T2", text: "- [ ] 최신 줄" } }} onDismissConflict={onDismiss} />);
    expect(screen.getByRole("alert").textContent).toContain("줄이 바뀌었습니다");
    expect(screen.getByRole("alert").textContent).toContain("- [ ] 최신 줄");
    fireEvent.click(within(screen.getByRole("alert")).getByRole("button", { name: "닫기" }));
    expect(onDismiss).toHaveBeenCalledWith("T2");
  });
  it("행 펼침은 하나만, 상세에 문서·요구·의존", () => {
    const onOpenDocument = vi.fn();
    render(<TaskTable tasks={sampleTasks()} statuses={statuses} documentTitles={{ "d-tasks": "작업 문서" }} onOpenDocument={onOpenDocument} />);
    fireEvent.click(screen.getByRole("button", { name: /^작업 T2, 상태 열림/ }));
    expect(screen.getByText("R1")).toBeTruthy();
    expect(screen.getByText(/작업 문서 · 3번째 줄/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /^작업 T4, 상태 진행/ }));
    expect(screen.queryByText("R1")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "문서에서 열기" }));
    expect(onOpenDocument).toHaveBeenCalledWith(expect.objectContaining({ key: "T4" }));
  });
  it("실행 칩: 열 수 있는 종류만 버튼, showLinks=false면 연결 열이 없다", () => {
    const onOpenLink = vi.fn();
    const { rerender } = render(<TaskTable tasks={sampleTasks()} statuses={statuses} openableKinds={["k-run"]} onOpenLink={onOpenLink} />);
    fireEvent.click(screen.getByRole("button", { name: "run-1 열기" }));
    expect(onOpenLink).toHaveBeenCalledWith(expect.objectContaining({ ref: "run-1" }));
    rerender(<TaskTable tasks={sampleTasks()} statuses={statuses} showLinks={false} />);
    expect(screen.queryByText(/run-1/)).toBeNull();
    rerender(<TaskTable tasks={sampleTasks()} statuses={statuses} />);
    expect(screen.getByText("run-1, ok")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "run-1 열기" })).toBeNull();
  });
  it("동작 자리(renderActions)를 행마다 그린다", () => {
    render(<TaskTable tasks={sampleTasks().slice(0, 2)} statuses={statuses} renderActions={(t) => <button type="button">동작 {t.key}</button>} />);
    expect(screen.getByRole("button", { name: "동작 T2" })).toBeTruthy();
  });
  it("가상 목록: 3000개여도 일부만 DOM에 둔다", () => {
    render(<TaskTable tasks={manyTasks(3000)} statuses={statuses} />);
    const rows = screen.getByRole("list", { name: "작업 표" }).children.length;
    expect(rows).toBeGreaterThan(0);
    expect(rows).toBeLessThan(100);
  });
  it("화살표 키로 이웃 줄에 포커스", () => {
    render(<TaskTable tasks={sampleTasks()} statuses={statuses} />);
    const first = screen.getByRole("button", { name: /^작업 T1, 상태 끝/ });
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowDown" });
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /^작업 T2, 상태 열림/ }));
  });
});

describe("TaskStatusMenu 키보드", () => {
  it("열면 현재 값에 포커스, 화살표로 이동, Esc로 닫고 버튼으로 복귀", () => {
    render(<TaskStatusMenu status="s-open" statuses={sampleStatuses()} taskTitle="X" onSelect={() => undefined} />);
    const btn = screen.getByRole("button", { name: "X의 상태 바꾸기: 열림" });
    fireEvent.click(btn);
    const items = screen.getAllByRole("menuitemradio");
    expect(document.activeElement).toBe(items[0]);
    fireEvent.keyDown(items[0] as HTMLElement, { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[1]);
    fireEvent.keyDown(items[1] as HTMLElement, { key: "ArrowUp" });
    fireEvent.keyDown(items[0] as HTMLElement, { key: "ArrowUp" });
    expect(document.activeElement).toBe(items[3]);
    fireEvent.keyDown(items[3] as HTMLElement, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(btn);
  });
});

describe("PlanGraph·PlanBundles", () => {
  it("계획할 작업이 없으면 빈 상태", () => {
    render(<PlanGraph plan={{}} tasks={[]} />);
    expect(screen.getByText("계획할 작업이 없습니다")).toBeTruthy();
  });
  it("노드마다 접근성 이름(제목·묶음·표시)을 갖고, 배치 엔진 결과를 쓴다", async () => {
    const engine = vi.fn(async () => ({ T1: { x: 0, y: 0 } }));
    const { container } = render(<PlanGraph plan={samplePlan()} tasks={sampleTasks()} statuses={sampleStatuses()} engine={engine} height={400} />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(engine).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("group", { name: "작업 계획 그래프" })).toBeTruthy();
    const names = Array.from(container.querySelectorAll(".react-flow__node")).map((n) => n.getAttribute("aria-label"));
    expect(names).toContain("작업 T2, 2번째 묶음, 병목, 준비됨");
    expect(container.querySelector(".ac-sdd-plan-node[data-critical]")).toBeTruthy();
  });
  it("배치 엔진이 실패하면 층별 배치로 남고 안내한다", async () => {
    render(<PlanGraph plan={samplePlan()} tasks={sampleTasks()} engine={async () => { throw new Error("x"); }} />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("자동 배치를 쓸 수 없어 층별로 놓았습니다")).toBeTruthy();
  });
  it("노드를 누르면 onSelect", async () => {
    const onSelect = vi.fn();
    const { container } = render(<PlanGraph plan={samplePlan()} tasks={sampleTasks()} engine={async () => ({})} onSelect={onSelect} />);
    await act(async () => {
      await Promise.resolve();
    });
    const node = container.querySelector(".react-flow__node[data-id='T2']") as HTMLElement;
    fireEvent.click(node);
    expect(onSelect).toHaveBeenCalledWith("T2");
  });
  it("묶음 글: 병렬 묶음·병목 표시, 순환 경고, 빈 상태", () => {
    const onSelect = vi.fn();
    const { rerender } = render(<PlanBundles plan={{ ...samplePlan(), cycles: [["T3", "T4"]] }} tasks={sampleTasks()} onSelect={onSelect} />);
    expect(screen.getByText("묶음 2")).toBeTruthy();
    expect(screen.getAllByText("2개 작업을 동시에 할 수 있습니다")).toHaveLength(2);
    expect(screen.getAllByText(/병목/).length).toBeGreaterThan(0);
    expect(screen.getByRole("alert").textContent).toContain("T3 → T4");
    fireEvent.click(screen.getByRole("button", { name: "작업 T2" }));
    expect(onSelect).toHaveBeenCalledWith("T2");
    rerender(<PlanBundles plan={{}} tasks={[]} />);
    expect(screen.getByText("묶음이 없습니다")).toBeTruthy();
  });
});

describe("TraceMatrix", () => {
  it("빈 상태", () => {
    render(<TraceMatrix matrix={{ rows: [] }} />);
    expect(screen.getByText("추적할 요구가 없습니다")).toBeTruthy();
  });
  it("빈 곳 코드는 표 → 문구 → 원문, 검증 결과는 표에 따른 라벨", () => {
    render(
      <TraceMatrix
        matrix={sampleTrace()}
        gapDisplay={{ "g-none": { tone: "danger", label: "작업 없음" } }}
        verificationDisplay={{ "v-pass": { tone: "success", label: "통과" } }}
        messages={{ "gap.g-unknown-code": "문구 표 라벨" }}
      />,
    );
    expect(screen.getByText("작업 없음")).toBeTruthy();
    expect(screen.getByText("문구 표 라벨")).toBeTruthy();
    expect(screen.getByText("통과")).toBeTruthy();
    expect(screen.getByText("검증 없음")).toBeTruthy();
    expect(screen.getByText("요구 없는 작업 1")).toBeTruthy();
  });
  it("빈 곳만 보기 거르기", () => {
    render(<TraceMatrix matrix={sampleTrace()} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    fireEvent.click(screen.getByRole("checkbox", { name: "빈 곳만 보기" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByText("R2")).toBeTruthy();
  });
  it("요구·작업·실행으로 이동하는 콜백, 연동이 꺼진 열은 숨김", () => {
    const onOpenTask = vi.fn();
    const onOpenRequirement = vi.fn();
    const onOpenLink = vi.fn();
    const { rerender } = render(<TraceMatrix matrix={sampleTrace()} onOpenTask={onOpenTask} onOpenRequirement={onOpenRequirement} onOpenLink={onOpenLink} openableKinds={["k-run"]} />);
    fireEvent.click(screen.getByRole("button", { name: "T2 작업 열기" }));
    fireEvent.click(screen.getByRole("button", { name: "R1 요구 열기" }));
    fireEvent.click(screen.getByRole("button", { name: "run-1" }));
    expect(onOpenTask).toHaveBeenCalledWith("T2", expect.objectContaining({ id: "R1" }));
    expect(onOpenRequirement).toHaveBeenCalledWith(expect.objectContaining({ id: "R1" }));
    expect(onOpenLink).toHaveBeenCalled();
    rerender(<TraceMatrix matrix={sampleTrace()} showRuns={false} showVerification={false} />);
    expect(screen.queryByText("run-1")).toBeNull();
    expect(screen.queryByText("검증 없음")).toBeNull();
  });
  it("가상 목록: 1000개 요구도 일부만 DOM에", () => {
    const rows = Array.from({ length: 1000 }, (_, i) => ({ id: `Q${i}`, document: "d", line: i, tasks: [], gaps: [] }));
    render(<TraceMatrix matrix={{ rows }} />);
    expect(screen.getAllByRole("listitem").length).toBeLessThan(100);
  });
});

describe("GateNotice·RulesSourceBadge", () => {
  it("관문 안내: 서버 문구, 확인할 문서 열기, 닫기, 동작 자리", () => {
    const onOpenDocument = vi.fn();
    const onDismiss = vi.fn();
    render(
      <GateNotice
        details={{ gate_id: "gate-x", message: "승인된 요구 문서가 필요합니다", document_ids: ["d-req"] }}
        documentTitles={{ "d-req": "요구" }}
        onOpenDocument={onOpenDocument}
        onDismiss={onDismiss}
        actions={<button type="button">가져와서 실행</button>}
      />,
    );
    expect(screen.getByRole("alert").textContent).toContain("승인된 요구 문서가 필요합니다");
    fireEvent.click(screen.getByRole("button", { name: "요구 열기" }));
    expect(onOpenDocument).toHaveBeenCalledWith("d-req");
    fireEvent.click(screen.getByRole("button", { name: "알림 닫기" }));
    expect(onDismiss).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "가져와서 실행" })).toBeTruthy();
  });
  it("문구가 없으면 SpecGate 문구 → 관문 id 안내 순", () => {
    const { rerender } = render(<GateNotice details={{ gate_id: "g1" }} message="규칙 문구" />);
    expect(screen.getByText("규칙 문구")).toBeTruthy();
    rerender(<GateNotice details={{ gate_id: "g1" }} />);
    expect(screen.getByText("g1 관문 조건을 만족하지 않습니다.")).toBeTruthy();
    expect(screen.queryByText("확인할 문서")).toBeNull();
  });
  it("출처 배지: 문구 표에 없으면 원문", () => {
    const { rerender } = render(<RulesSourceBadge source="spec" messages={{ "source.spec": "스펙" }} />);
    expect(screen.getByText("출처: 스펙")).toBeTruthy();
    rerender(<RulesSourceBadge source="made-up" />);
    expect(screen.getByText("출처: made-up")).toBeTruthy();
  });
});
