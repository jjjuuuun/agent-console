import { describe, expect, it } from "vitest";
import { LINK_PART_IDS } from "../modules";
import { DEFAULT_CONFIG_WIDGETS } from "./configWidgets";
import { DEFAULT_LINK_PARTS } from "./linkParts";

describe("위키 연결 등록 데이터", () => {
  it("실행 상세 칩은 역할 wiki:runs 하나만 요구하고 없으면 숨는다", () => {
    expect(DEFAULT_LINK_PARTS.find((p) => p.id === LINK_PART_IDS.runsWikiChanges)).toMatchObject({ requires: ["wiki:runs"], onMissing: "hide" });
  });

  it("스키마 위젯 이름 wiki-ref가 등록 표에 있다(이름은 서버 스키마 데이터)", () => {
    expect(Object.keys(DEFAULT_CONFIG_WIDGETS)).toContain("wiki-ref");
  });
});
