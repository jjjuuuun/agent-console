/**
 * 공간(어느 저장소인가) 표시와 질의 인자. 공간 = `SpaceRef{project_id}`: null = 공용(라이브러리), 값 = 그 프로젝트 폴더의 사본.
 * 정의·메모리 REST는 `?project=<id>`(없으면 공용)로 고른다(design §PI.10).
 */
import type { MessageRef } from "./messages";

/** 공간을 가리키는 값. null·undefined·빈 문자열 = 공용. */
export type SpaceId = string | null | undefined;

export type SpaceKind = "library" | "project";

/** 공용이면 null, 프로젝트면 그 id. */
export function normalizeSpace(space: SpaceId): string | null {
  if (space === undefined || space === null) return null;
  const s = space.trim();
  return s === "" ? null : s;
}

/** REST 질의 `project`의 값. 공용이면 undefined(인자를 보내지 않아 지금 요청과 같은 주소). */
export function spaceParam(space: SpaceId): string | undefined {
  return normalizeSpace(space) ?? undefined;
}

/** `{project: id}` 질의 조각. 공용이면 빈 객체(펼쳐서 질의 객체에 합친다). */
export function spaceQuery(space: SpaceId): { project?: string } {
  const id = normalizeSpace(space);
  return id === null ? {} : { project: id };
}

/** 계약 `SpaceRef`로. */
export function toSpaceRef(space: SpaceId): { project_id: string | null } {
  return { project_id: normalizeSpace(space) };
}

export interface SpaceLabel {
  kind: SpaceKind;
  /** 칩 글자. 프로젝트는 이름을 `{name}`에 채운다. */
  label: MessageRef;
  /** 팝오버·한 줄 안내 문구. 공용 = 라이브러리 설명, 프로젝트 = "이 프로젝트의 사본입니다…". */
  note: MessageRef;
  /** 칩에 표시할 이름(프로젝트 이름, 없으면 id). 공용은 빈 문자열. */
  name: string;
}

/**
 * 공간 칩의 데이터. 이름 표는 주면 쓰고(`names`), 없으면 id를 이름으로 쓴다.
 * 문구는 키만 돌려준다(`createProjectsText`로 바꾼다).
 */
export function spaceLabel(space: SpaceId, names?: ReadonlyMap<string, string> | Readonly<Record<string, string>>): SpaceLabel {
  const id = normalizeSpace(space);
  if (id === null) return { kind: "library", label: { key: "space.library" }, note: { key: "space.library_tip" }, name: "" };
  const found = names === undefined ? undefined : names instanceof Map ? names.get(id) : (names as Readonly<Record<string, string>>)[id];
  const name = found !== undefined && found !== "" ? found : id;
  return { kind: "project", label: { key: "space.project", params: { name } }, note: { key: "space.project_note" }, name };
}

/** 두 공간이 같은가(공용끼리, 같은 프로젝트끼리). */
export function sameSpace(a: SpaceId, b: SpaceId): boolean {
  return normalizeSpace(a) === normalizeSpace(b);
}
