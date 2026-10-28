import { describe, expect, it } from "vitest";
import { makeDescriptor, makeInteraction } from "../fixtures";
import { answerCardIds, answerViaOf, resolveAnswerSurface, type ResolveAnswerSurfaceInput } from "./answerSurface";

const free = makeDescriptor({ id: "any-kind", free_text_path: "/response", ui_hints: { renderer: "whatever" }, response_schema: { type: "object", properties: { response: { type: "string" } } } });
const ask = makeInteraction({ id: "i1", kind: "any-kind", payload: { questions: [{ question: "?", options: [] }] } });

function resolve(over: Partial<ResolveAnswerSurfaceInput> = {}) {
  return resolveAnswerSurface({ pending: [ask], descriptors: new Map([["any-kind", free]]), answerWithComposer: true, context: "chat", ...over });
}

describe("resolveAnswerSurface (screen-chat §10.2)", () => {
  it("AC1 자유 답 하나 + 기본 설정이면 입력창", () => {
    expect(resolve()).toEqual({ surface: "composer", interactionId: "i1" });
  });
  it("payload·response_schema가 없어도(질문 배열 없음) 입력창", () => {
    expect(resolve({ pending: [makeInteraction({ id: "i1", kind: "any-kind", payload: { text: "?" } })] }).surface).toBe("composer");
    expect(resolve({ pending: [makeInteraction({ id: "i1", kind: "any-kind" })], descriptors: { "any-kind": makeDescriptor({ free_text_path: "/response" }) } }).surface).toBe("composer");
  });
  it("AC2 선택지가 있거나 질문이 둘 이상이면 카드", () => {
    expect(resolve({ pending: [makeInteraction({ id: "i1", kind: "any-kind", payload: { questions: [{ question: "?", options: [{ label: "a" }] }] } })] }).surface).toBe("card");
    expect(resolve({ pending: [makeInteraction({ id: "i1", kind: "any-kind", payload: { questions: [{ question: "a" }, { question: "b" }] } })] }).surface).toBe("card");
  });
  it("AC3 대기 0개·2개 이상이면 카드", () => {
    expect(resolve({ pending: [] }).surface).toBe("card");
    expect(resolve({ pending: [ask, makeInteraction({ id: "i2", kind: "any-kind" })] }).surface).toBe("card");
  });
  it("AC4 free_text_path가 없으면 카드. 종류 이름·렌더러 이름은 결과에 영향이 없다", () => {
    for (const name of ["question", "tool_permission", "zz-임의", "constructor"]) {
      const d = makeDescriptor({ id: name, free_text_path: "/response", ui_hints: { renderer: `r-${name}` } });
      const i = makeInteraction({ id: "i1", kind: name, payload: { questions: [{ question: "?" }] } });
      expect(resolve({ pending: [i], descriptors: { [name]: d } }).surface).toBe("composer");
      expect(resolve({ pending: [i], descriptors: { [name]: { ...d, free_text_path: null } } }).surface).toBe("card");
    }
    expect(resolve({ descriptors: new Map() }).surface).toBe("card");
  });
  it("필수 응답 항목이 free_text_path 밖에 있으면 카드", () => {
    const d = { ...free, response_schema: { required: ["decision"] } };
    expect(resolve({ descriptors: new Map([["any-kind", d]]) }).surface).toBe("card");
    expect(resolve({ descriptors: new Map([["any-kind", { ...free, response_schema: { required: ["response"] } }]]) }).surface).toBe("composer");
    expect(resolve({ descriptors: new Map([["any-kind", { ...free, response_schema: { required: [] } }]]) }).surface).toBe("composer");
  });
  it("요청별 response_schema가 디스크립터보다 우선한다", () => {
    expect(resolve({ pending: [{ ...ask, response_schema: { required: ["pick"] } }] }).surface).toBe("card");
  });
  it("AC5 answer_surface=card는 카드, 모르는 값은 auto", () => {
    const d = (v: unknown) => new Map([["any-kind", { ...free, ui_hints: { renderer: "x", answer_surface: v } }]]);
    expect(resolve({ descriptors: d("card") }).surface).toBe("card");
    expect(resolve({ descriptors: d("auto") }).surface).toBe("composer");
    expect(resolve({ descriptors: d("composer") }).surface).toBe("composer");
    expect(resolve({ descriptors: d("???") }).surface).toBe("composer");
  });
  it("AC6 설정이 꺼졌으면 카드", () => {
    expect(resolve({ answerWithComposer: false }).surface).toBe("card");
  });
  it("AC7 run-detail이면 항상 카드", () => {
    expect(resolve({ context: "run-detail" }).surface).toBe("card");
  });
  it("answerViaOf: 주인 요청만 external, 입력창 id 헬퍼는 요청마다 다르다", () => {
    const s = resolve();
    expect(answerViaOf(s, "i1")).toBe("external");
    expect(answerViaOf(s, "i2")).toBe("inline");
    expect(answerViaOf({ surface: "card" }, "i1")).toBe("inline");
    expect(answerCardIds("a").body).not.toBe(answerCardIds("b").body);
  });
});
