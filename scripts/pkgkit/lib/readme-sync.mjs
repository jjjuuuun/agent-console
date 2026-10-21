// README의 ```ts readme 블록과 test/readme.test.ts의 표시 구간이 같은지 검사한다(순수 함수, E-9).
// README 쪽: 펜스 정보 문자열이 `ts readme`인 코드 블록.
// 테스트 쪽: `// readme:start` 와 `// readme:end` 사이. 블록·구간은 등장 순서대로 짝을 맞춘다.

export const README_FENCE_INFO = "ts readme";
export const REGION_START = "// readme:start";
export const REGION_END = "// readme:end";

/**
 * 비교용으로 코드를 다듬는다: 줄바꿈 통일, 줄 끝 공백 제거, 공통 들여쓰기 제거, 앞뒤 빈 줄 제거.
 * @param {string} text
 * @returns {string}
 */
export function normalizeCode(text) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n").map((l) => l.replace(/\s+$/, ""));
  while (lines.length && lines[0] === "") lines.shift();
  while (lines.length && lines[lines.length - 1] === "") lines.pop();
  const indents = lines.filter((l) => l !== "").map((l) => /^ */.exec(l)[0].length);
  const cut = indents.length ? Math.min(...indents) : 0;
  return lines.map((l) => l.slice(cut)).join("\n");
}

/**
 * README에서 `ts readme` 코드 블록을 뽑는다.
 * @param {string} markdown
 * @returns {string[]} 정규화된 블록 내용
 */
export function extractReadmeBlocks(markdown) {
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  for (let i = 0; i < lines.length; i += 1) {
    const open = /^(`{3,})\s*(.*?)\s*$/.exec(lines[i]);
    if (!open || open[2] !== README_FENCE_INFO) continue;
    const fence = open[1];
    const body = [];
    i += 1;
    while (i < lines.length && !new RegExp(`^${fence}\`*\\s*$`).test(lines[i])) {
      body.push(lines[i]);
      i += 1;
    }
    blocks.push(normalizeCode(body.join("\n")));
  }
  return blocks;
}

/**
 * 테스트 소스에서 표시 구간을 뽑는다.
 * @param {string} source
 * @returns {{regions: string[], problems: string[]}} 구간 내용과 표시 오류(짝이 안 맞음 등)
 */
export function extractTestRegions(source) {
  const regions = [];
  const problems = [];
  let current = null;
  for (const raw of source.replace(/\r\n?/g, "\n").split("\n")) {
    const line = raw.trim();
    if (line === REGION_START) {
      if (current) problems.push(`${REGION_START}가 닫히기 전에 다시 나왔다`);
      current = [];
    } else if (line === REGION_END) {
      if (!current) problems.push(`${REGION_END}에 짝이 되는 ${REGION_START}가 없다`);
      else regions.push(normalizeCode(current.join("\n")));
      current = null;
    } else if (current) {
      current.push(raw);
    }
  }
  if (current) problems.push(`${REGION_START}에 짝이 되는 ${REGION_END}가 없다`);
  return { regions, problems };
}

/**
 * README 블록과 테스트 구간이 일치하는지 본다.
 * @param {string | null} readme README 내용(없으면 null)
 * @param {string | null} testSource test/readme.test.ts 내용(없으면 null)
 * @returns {string[]} 문제 설명 목록(비어 있으면 일치)
 */
export function checkReadmeSync(readme, testSource) {
  if (readme === null) return ["README.md가 없다"];
  if (testSource === null) return ["test/readme.test.ts가 없다"];
  const blocks = extractReadmeBlocks(readme);
  const { regions, problems } = extractTestRegions(testSource);
  const out = [...problems];
  if (blocks.length === 0) out.push(`README에 \`\`\`${README_FENCE_INFO} 블록이 없다`);
  if (regions.length === 0) out.push(`test/readme.test.ts에 ${REGION_START} ~ ${REGION_END} 구간이 없다`);
  if (blocks.length !== regions.length) {
    out.push(`README 블록 ${blocks.length}개, 테스트 구간 ${regions.length}개로 개수가 다르다`);
    return out;
  }
  blocks.forEach((block, i) => {
    if (block !== regions[i]) out.push(`README 블록 ${i + 1}번이 테스트 구간과 다르다`);
  });
  return out;
}
