import { describe, expect, it } from "vitest";
import { parseIssuesHeader } from "./io";

// 4R.19 QA: X-Console-Issues 파싱 경계
describe("parseIssuesHeader 경계", () => {
  const w = { severity: "warning", code: "c", message: "m", path: "/p" };
  it("없음·빈 문자열·빈 배열·깨진 JSON·배열 아님은 undefined", () => {
    for (const v of [null, undefined, "", "[]", "{깨짐", "{}", "null", "5", '"s"']) expect(parseIssuesHeader(v)).toBeUndefined();
  });
  it("ASCII 이스케이프된 한글(서버 형식)과 원문 한글 모두 복원한다", () => {
    const esc = JSON.stringify([{ ...w, message: "예약 이름" }]).replace(/[^ -~]/g, (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
    expect(/^[ -~]*$/.test(esc)).toBe(true);
    expect(parseIssuesHeader(esc)?.[0]?.message).toBe("예약 이름");
    expect(parseIssuesHeader(JSON.stringify([{ ...w, message: "예약 이름" }]))?.[0]?.message).toBe("예약 이름");
  });
  it("message 없는 항목은 걸러내고 나머지는 남긴다", () => {
    expect(parseIssuesHeader(JSON.stringify([{ code: "x" }, null, 3, w]))).toEqual([w]);
    expect(parseIssuesHeader(JSON.stringify([{ code: "x" }]))).toBeUndefined();
  });
  it("큰 헤더(수천 항목)도 던지지 않고 읽는다", () => {
    const big = JSON.stringify(Array.from({ length: 5000 }, (_, i) => ({ ...w, message: `m${i}` })));
    expect(parseIssuesHeader(big)?.length).toBe(5000);
  });
});
