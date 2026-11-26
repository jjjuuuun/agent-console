import ko from "./locales/ko.json";
import retired from "./locales/retired.json";

/** 문구 나무(JSON 모양). 값은 문자열이거나 하위 나무다. */
export interface MessageTree {
  readonly [key: string]: string | MessageTree;
}

/** 나무의 경로 문자열 합집합: `{ a: { b: "x", _: "y" } }` → `"a.b" | "a"`. */
type TreePaths<T, P extends string = ""> = T extends string
  ? P
  : { [K in keyof T & string]: TreePaths<T[K], K extends "_" ? P : P extends "" ? K : `${P}.${K}`> }[keyof T & string];

/** 문구 나무를 점 표기 키 표로 편다. 이름이 `_`인 값은 부모 키가 된다. */
export function flattenMessageTree(tree: MessageTree, prefix = ""): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(tree)) {
    const path = key === "_" ? prefix : prefix === "" ? key : `${prefix}.${key}`;
    if (typeof value === "string") out[path] = value;
    else Object.assign(out, flattenMessageTree(value, path));
  }
  return out;
}

export type ProjectMessageKey = TreePaths<typeof ko>;

/**
 * 프로젝트 2 문구 표(한국어 원본, screen-projects §12.2). 화면 문구는 키로만 다루고 이 표는 기본값이다.
 * 앱이 같은 키로 덮어쓸 수 있다(`createProjectsText`). 문구에 모듈·기능·구성 종류 이름을 고정하지 않는다:
 * 종류 이름은 `{kind}` 같은 자리표시로, 구성 폴더 이름은 `{dir}`로 받는다.
 * 폐기어(U-16: 작업 폴더·사용 중·빼기·가져온 구성 …)는 쓰지 않는다 — `RETIRED_TERMS`가 그 목록(데이터)이다.
 * 한국어 기본 문구 표는 `locales/ko.json`을 편 것이다(점 표기 키를 나무로 편 모양, 한 키가 다른 키의 앞부분이면 값을 `_`에 둔다).
 */
export const DEFAULT_PROJECT_MESSAGES = flattenMessageTree(ko) as Readonly<Record<ProjectMessageKey, string>>;

/** 문구 표. 기본 키는 모두 있고 앱이 더한 키도 허용한다. */
export type ProjectMessages = { [K in ProjectMessageKey]: string } & Readonly<Record<string, string>>;

/** 화면 문구에 쓰지 않는 말(U-16, 한국어). 5.7R.35 정적 검사(이 패키지 테스트·앱 메시지 표 검사)가 읽는 데이터다(`locales/retired.json`). */
export const RETIRED_TERMS: readonly string[] = retired.ko.terms;

/**
 * `RETIRED_TERMS` 가운데 프로젝트 문구에서만 폐기어인 말. 다른 기능에서는 일반 뜻(켜짐·목록에서 제거)으로 쓰이므로,
 * 앱 전체 메시지 표를 보는 정적 검사는 이 말을 프로젝트 기능 문구에만 적용한다. 데이터라 바꿀 수 있다.
 */
export const PROJECT_CONTEXT_RETIRED_TERMS: readonly string[] = retired.ko.projectContext;

/** 영어 화면 문구에 쓰지 않는 말(용어집 §3 "쓰지 않을 말"의 프로젝트 관련 줄). 영어 묶음 검사가 읽는 데이터다. */
export const RETIRED_TERMS_EN: readonly string[] = retired.en.terms;

/** `RETIRED_TERMS_EN` 가운데 프로젝트 문구에서만 폐기어인 말(`PROJECT_CONTEXT_RETIRED_TERMS`의 영어 짝). */
export const PROJECT_CONTEXT_RETIRED_TERMS_EN: readonly string[] = retired.en.projectContext;

export type MessageParams = Readonly<Record<string, string | number>>;

/** `{이름}` 자리를 채운다. 없는 값은 자리표시를 그대로 둔다. */
export function formatMessage(template: string, params: MessageParams = {}): string {
  return template.replace(/\{(\w+)\}/g, (whole, name: string) => (name in params ? String(params[name]) : whole));
}

/** 키 + 자리 값 한 쌍. 판단 함수가 문구 대신 돌려주고, 화면이 `text(ref)`로 바꾼다. */
export interface MessageRef {
  key: string;
  params?: MessageParams;
}

export type ProjectsText = (ref: MessageRef | string, params?: MessageParams) => string;

/**
 * 문구 변환 함수를 만든다. `overrides`가 기본 표를 덮어쓰고, 모르는 키는 키 문자열 그대로 돌려준다
 * (누락이 화면에서 보이게).
 */
export function createProjectsText(overrides: Readonly<Record<string, string>> = {}): ProjectsText {
  const table: Readonly<Record<string, string>> = { ...DEFAULT_PROJECT_MESSAGES, ...overrides };
  return (ref, params) => {
    const r: MessageRef = typeof ref === "string" ? { key: ref, ...(params === undefined ? {} : { params }) } : ref;
    const template = table[r.key];
    return template === undefined ? r.key : formatMessage(template, { ...r.params, ...params });
  };
}
