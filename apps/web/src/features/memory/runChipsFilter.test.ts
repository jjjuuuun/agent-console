import { describe, expect, it } from "vitest";
import { joinTypePrefixes, matchesTypePrefix } from "../../lib/typePrefix";
import { RUN_CHIPS } from "./memoryConfig";

describe("메모리 읽기 칩: 세는 것과 여는 필터가 같다(5.7R.31)", () => {
  it("칩이 세는 read.types 이벤트는 모두 여는 필터에 들고 쓰기 이벤트는 들지 않는다", () => {
    const filter = joinTypePrefixes(RUN_CHIPS.read.openPrefixes);
    for (const n of RUN_CHIPS.read.types) expect(matchesTypePrefix(`${RUN_CHIPS.typePrefix}${n}`, filter)).toBe(true);
    for (const n of RUN_CHIPS.write.types) expect(matchesTypePrefix(`${RUN_CHIPS.typePrefix}${n}`, filter)).toBe(false);
  });
});
