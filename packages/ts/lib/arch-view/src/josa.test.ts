import { describe, expect, it } from "vitest";
import { edgeAriaLabel } from "./model";
import { defaultMessages, formatMessage } from "./messages";
import { hasBatchim, josa, withJosa } from "./josa";

describe("받침 판단·조사 고르기", () => {
  it("한글 받침", () => {
    expect(hasBatchim("서버")).toBe(false);
    expect(hasBatchim("훅")).toBe(true);
    expect(hasBatchim("도구 호출")).toBe(true);
    expect(hasBatchim("")).toBe(false);
  });
  it("영문·숫자·약어·끝 기호", () => {
    expect(hasBatchim("Hook")).toBe(true);
    expect(hasBatchim("Context builder")).toBe(false);
    expect(hasBatchim("SDK / CLI")).toBe(false);
    expect(hasBatchim("MCP")).toBe(false);
    expect(hasBatchim("API")).toBe(false);
    expect(hasBatchim("DB")).toBe(false);
    expect(hasBatchim("SQL")).toBe(true);
    expect(hasBatchim("단계 3")).toBe(true);
    expect(hasBatchim("단계 2")).toBe(false);
    expect(hasBatchim("Hook (훅)")).toBe(true);
  });
  it("으로/로: ㄹ 받침은 로", () => {
    expect(withJosa("Hook", "으로/로")).toBe("Hook으로");
    expect(withJosa("서버", "으로/로")).toBe("서버로");
    expect(withJosa("서울", "으로/로")).toBe("서울로");
    expect(withJosa("SQL", "으로/로")).toBe("SQL로");
    expect(withJosa("파일", "으로/로")).toBe("파일로");
  });
  it("그 밖의 쌍과 잘못된 쌍", () => {
    expect(josa("훅", "은/는")).toBe("은");
    expect(josa("서버", "이/가")).toBe("가");
    expect(josa("서버", "없음")).toBe("없음");
  });
  it("formatMessage 틀에서 {이름|쌍}을 풀고 기존 {이름}은 그대로 쓴다", () => {
    expect(formatMessage("{a|을/를} 본다", { a: "훅" })).toBe("훅을 본다");
    expect(formatMessage("{a}로", { a: "훅" })).toBe("훅로");
    expect(formatMessage("{x|은/는}", {})).toBe("{x|은/는}");
  });
  it("연결 접근 이름: 라벨은 그대로, 받침에 맞는 조사, messages로 덮어쓰기 가능", () => {
    const edge = { id: "e", label: "호출", from: "a", to: "b", kind: "structural", status: "observed", metrics: {} } as never;
    const labels = { a: "Dispatcher", b: "Hook" };
    expect(edgeAriaLabel(edge, labels, defaultMessages)).toBe("호출, Dispatcher에서 Hook으로, 구조 연결");
    expect(edgeAriaLabel(edge, { a: "A", b: "서버" }, defaultMessages)).toBe("호출, A에서 서버로, 구조 연결");
    expect(edgeAriaLabel(edge, labels, { ...defaultMessages, ariaEdgeFlow: "{from} → {to}" })).toBe("호출, Dispatcher → Hook, 구조 연결");
  });
});
