import { describe, expect, test } from "vitest";

import { createProjectsText } from "../src";

describe("공용에서 가져오기 안내 문장", () => {
  const text = createProjectsText();
  test("프로젝트 이름이 '폴더'로 끝나도 '폴더 폴더'로 읽히지 않는다", () => {
    for (const key of ["copy.import.intro", "copy.import.intro_unknown"] as const) {
      const out = text({ key, params: { name: "작업 폴더", dir: ".agent-console" } });
      expect(out).toContain("‘작업 폴더’ 프로젝트의 구성 폴더");
      expect(out).not.toContain("폴더 폴더");
    }
  });
});
