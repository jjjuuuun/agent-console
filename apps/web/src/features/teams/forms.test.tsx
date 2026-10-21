import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import type { NodeTypeDescriptor } from "@agent-console/contracts";
import { EdgeConfigForm, NodeConfigForm, splitConfigSchema, starterSection } from "./forms";
import { REVIEW_DECISIONS_FIELD, ReviewDecisionsField, nextDecisionId } from "./widgets/ReviewDecisionsField";
import { parseVariables } from "./widgets/TemplateField";

afterEach(cleanup);

// 도메인과 무관한 임의 스키마
const descriptor = {
  id: "t-any",
  title: "아무 노드",
  config_schema: {
    type: "object",
    properties: {
      plain: { type: "string", title: "단순 값", default: "x" },
      panel: { anyOf: [{ $ref: "#/$defs/Panel" }, { type: "null" }], default: null, title: "패널" },
    },
    $defs: {
      Panel: {
        type: "object",
        title: "패널 설정",
        description: "패널 설명",
        properties: {
          decisions: { type: "array", minItems: 1, items: { $ref: "#/$defs/Item" }, title: "항목들" },
          output_template: { anyOf: [{ type: "string" }, { type: "null" }], default: null, title: "형식", description: "안전 치환. 변수 alpha·beta·gamma. 비우면 그대로." },
        },
        required: ["decisions"],
      },
      Item: { type: "object", properties: { id: { type: "string", pattern: "^[a-z]+$" }, label: { type: "string", default: "" } }, required: ["id"] },
    },
  },
} as unknown as NodeTypeDescriptor;

describe("config 스키마로 폼 나누기", () => {
  it("단순 값과 객체 섹션을 속성 이름이 아니라 모양으로 가른다", () => {
    const { scalars, sections } = splitConfigSchema(descriptor);
    expect(scalars).toEqual(["plain"]);
    expect(sections.map((s) => [s.key, s.title, s.description])).toEqual([["panel", "패널", "패널 설명"]]);
  });

  it("섹션을 켤 때의 시작 값: 최소 1개인 필수 목록에 항목 하나(필수 문자열은 빈 값, id는 새 id)", () => {
    const { sections } = splitConfigSchema(descriptor);
    expect(starterSection(sections[0]!.schema)).toEqual({ decisions: [{ id: "d1" }] });
    expect(nextDecisionId([{ id: "d1" }, { id: "d2" }])).toBe("d3");
  });

  it("설명 문장에서 변수 이름을 읽는다", () => {
    expect(parseVariables("안전 치환. 변수 alpha·beta·gamma. 비우면 그대로.")).toEqual(["alpha", "beta", "gamma"]);
    expect(parseVariables("변수가 없음")).toEqual([]);
    expect(parseVariables(undefined)).toEqual([]);
  });
});

function Host({ initial = {} }: { initial?: Record<string, unknown> }) {
  const [config, setConfig] = useState<Record<string, unknown>>(initial);
  return (
    <>
      <NodeConfigForm descriptor={descriptor} config={config} onChange={setConfig} />
      <output data-testid="out">{JSON.stringify(config)}</output>
    </>
  );
}

describe("NodeConfigForm", () => {
  it("섹션은 꺼져 있다가 켜면 시작 값이 들어가고, 끄면 키가 지워진다", () => {
    render(<Host />);
    expect(screen.getByText("패널 설명")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "검토 사용" }));
    expect(screen.getByTestId("out").textContent).toBe('{"panel":{"decisions":[{"id":"d1"}]}}');
    fireEvent.click(screen.getByRole("button", { name: "검토 끄기" }));
    expect(screen.getByTestId("out").textContent).toBe("{}");
  });

  it("변수 칩을 누르면 커서 위치에 {변수}가 들어간다(기본값은 저장 값에 쌓이지 않는다)", () => {
    render(<Host initial={{ panel: { decisions: [{ id: "d1" }] } }} />);
    const area = screen.getByLabelText("형식") as HTMLTextAreaElement;
    fireEvent.change(area, { target: { value: "앞 뒤" } });
    fireEvent.click(screen.getByRole("button", { name: "{alpha} 넣기" }));
    expect(JSON.parse(screen.getByTestId("out").textContent ?? "{}").panel.output_template).toContain("{alpha}");
    expect(JSON.parse(screen.getByTestId("out").textContent ?? "{}")).not.toHaveProperty("plain");
  });
});

describe("검토 결정 목록 편집", () => {
  function Decisions({ initial }: { initial: unknown[] }) {
    const [value, setValue] = useState<unknown>(initial);
    return (
      <>
        <ReviewDecisionsField id="d" value={value} onChange={setValue} onBlur={() => {}} label="결정" required={false} disabled={false} readonly={false} schema={{}} options={{ idPattern: "^[a-z0-9]+$" }} errors={[]} />
        <output data-testid="v">{JSON.stringify(value)}</output>
      </>
    );
  }

  it("결정 추가·순서·삭제, id 중복·형식 오류 즉시 표시", () => {
    render(<Decisions initial={[{ id: "ok", label: "승인" }]} />);
    fireEvent.click(screen.getByRole("button", { name: "+ 결정 추가" }));
    expect(screen.getByTestId("v").textContent).toBe('[{"id":"ok","label":"승인"},{"id":"d1","label":""}]');
    const ids = screen.getAllByLabelText("id(포트 이름)");
    fireEvent.change(ids[1]!, { target: { value: "ok" } });
    expect(screen.getAllByText("id가 겹칩니다").length).toBeGreaterThan(0);
    fireEvent.change(ids[1]!, { target: { value: "Bad Id" } });
    expect(screen.getByText("포트 이름 규칙에 맞지 않습니다")).toBeTruthy();
    fireEvent.change(ids[1]!, { target: { value: "no" } });
    fireEvent.click(screen.getByRole("button", { name: "위로: no" }));
    expect(JSON.parse(screen.getByTestId("v").textContent ?? "[]").map((d: { id: string }) => d.id)).toEqual(["no", "ok"]);
    fireEvent.click(screen.getByRole("button", { name: "삭제: 승인" }));
    expect(JSON.parse(screen.getByTestId("v").textContent ?? "[]")).toHaveLength(1);
  });

  it("모양: 색은 토큰 이름 목록에서만 고르고(자유 입력 없음) 기본으로 되돌리면 힌트가 사라진다", () => {
    render(<Decisions initial={[{ id: "ok", label: "승인" }]} />);
    const color = screen.getByLabelText("색") as HTMLSelectElement;
    const options = within(color).getAllByRole("option").map((o) => o.getAttribute("value"));
    expect(options[0]).toBe("");
    expect(options.slice(1)).toEqual(["accent", "success", "danger", "warning", "info", "neutral"]);
    fireEvent.change(color, { target: { value: "danger" } });
    expect(screen.getByTestId("v").textContent).toBe('[{"id":"ok","label":"승인","ui_hints":{"color":"danger"}}]');
    fireEvent.click(screen.getByLabelText("점선"));
    expect(screen.getByTestId("v").textContent).toContain('"dashed":true');
    fireEvent.change(color, { target: { value: "" } });
    fireEvent.click(screen.getByLabelText("점선"));
    expect(screen.getByTestId("v").textContent).toBe('[{"id":"ok","label":"승인"}]');
    expect(REVIEW_DECISIONS_FIELD).toBe("review-decisions");
  });
});

describe("EdgeConfigForm", () => {
  it("연결 종류가 말하는 선택지(허용 종류)를 체크 상자로 보이고 비우면 null", () => {
    const kind = {
      id: "k-any",
      title: "아무 연결",
      interaction: { kinds: ["i-a", "i-b"] },
      config_schema: { type: "object", properties: { kinds: { anyOf: [{ type: "array", items: { type: "string" } }, { type: "null" }], default: null, title: "허용 종류" } } },
    } as never;
    function H() {
      const [c, setC] = useState<Record<string, unknown>>({});
      return (
        <>
          <EdgeConfigForm kind={kind} config={c} onChange={setC} interactionKinds={[{ id: "i-a", title: "가 종류" } as never]} />
          <output data-testid="e">{JSON.stringify(c)}</output>
        </>
      );
    }
    render(<H />);
    fireEvent.click(screen.getByRole("checkbox", { name: "가 종류" }));
    expect(screen.getByTestId("e").textContent).toBe('{"kinds":["i-a"]}');
    expect(screen.getByRole("checkbox", { name: "i-b" })).toBeTruthy();
    fireEvent.click(screen.getByRole("checkbox", { name: "가 종류" }));
    expect(screen.getByTestId("e").textContent).toBe("{}");
  });
});
