// 템플릿 렌더링(순수 함수). `{{a.b}}` 자리표시자를 값으로 바꾸고 `.tmpl` 확장자를 뗀다.
// 파일 시스템을 모른다. 읽기·쓰기는 호출자가 한다.

/**
 * 문자열 안의 `{{키}}`를 값으로 바꾼다. 점(`.`)으로 중첩 키를 읽는다.
 * @param {string} text 템플릿 문자열
 * @param {Record<string, unknown>} vars 값
 * @returns {string}
 * @throws {Error} 값이 없는 키
 */
export function renderString(text, vars) {
  return text.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_m, key) => {
    let cur = vars;
    for (const part of key.split(".")) {
      if (cur === null || typeof cur !== "object" || !(part in cur)) throw new Error(`템플릿 값이 없다: ${key}`);
      cur = cur[part];
    }
    return String(cur);
  });
}

/**
 * 템플릿 파일 묶음을 렌더링한다. 경로의 `.tmpl` 접미사는 제거한다.
 * @param {Record<string, string>} files 상대 경로 -> 템플릿 내용
 * @param {Record<string, unknown>} vars
 * @returns {Record<string, string>} 상대 경로 -> 내용
 */
export function renderTree(files, vars) {
  const out = {};
  for (const [rel, content] of Object.entries(files)) {
    out[rel.replace(/\.tmpl$/, "")] = renderString(content, vars);
  }
  return out;
}

const isPlainObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

/**
 * JSON 객체를 깊게 합친다. 배열·원시값은 patch가 이긴다. patch 값이 null이면 키를 지운다.
 * @param {Record<string, unknown>} base
 * @param {Record<string, unknown>} patch
 * @returns {Record<string, unknown>}
 */
export function mergeJson(base, patch) {
  const out = { ...base };
  for (const [key, value] of Object.entries(patch)) {
    if (value === null) delete out[key];
    else if (isPlainObject(value) && isPlainObject(out[key])) out[key] = mergeJson(out[key], value);
    else out[key] = value;
  }
  return out;
}

/**
 * 기본 템플릿 위에 덮어쓰기(overlay) 파일을 얹는다.
 * `package.patch.json`은 `package.json`에 깊게 합치고, 그 밖의 파일은 같은 경로를 덮어쓴다.
 * @param {Record<string, string>} base 렌더링된 기본 파일
 * @param {Record<string, string>} overlay 렌더링된 덮어쓰기 파일
 * @returns {Record<string, string>}
 */
export function applyOverlay(base, overlay) {
  const out = { ...base };
  for (const [rel, content] of Object.entries(overlay)) {
    if (rel === "package.patch.json") {
      const merged = mergeJson(JSON.parse(out["package.json"] ?? "{}"), JSON.parse(content));
      out["package.json"] = `${JSON.stringify(merged, null, 2)}\n`;
    } else {
      out[rel] = content;
    }
  }
  return out;
}
