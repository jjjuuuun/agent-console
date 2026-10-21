/**
 * 여러 파일 리소스(`content.multi_file`)의 로컬 초안 로직. 순수 함수만 둔다(서버·React를 모른다).
 * 종류 이름을 모른다 — 어떤 종류든 파일 경로와 내용만 본다.
 */

/** 파일 한 개의 초안. `text`가 null이면 텍스트로 편집할 수 없는 파일이다. */
export interface FileEntry {
  /** `/`로 구분한 상대 경로 */
  path: string;
  /** UTF-8로 읽은 내용. 텍스트가 아니면 null */
  text: string | null;
  /** 서버가 알려 준 바이트 수(편집하면 `text`/`bytes`로 다시 계산) */
  size: number;
  mediaType?: string;
  /** 올려서 바꾼 텍스트 아닌 파일의 내용(저장 때 그대로 보낸다) */
  bytes?: Uint8Array;
}

/** 경로 검사 실패 사유. 문구는 화면이 messages에서 고른다. */
export type PathProblem = "empty" | "absolute" | "dotdot" | "duplicate" | "forbidden" | "reserved" | "trailing" | "folderConflict";

/** Windows가 파일 이름으로 허용하지 않는 장치 이름(OS 규칙이지 도메인 목록이 아니다). */
const RESERVED = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i;
const FORBIDDEN_CHARS = new Set('<>:"\\|?*');
const forbidden = (part: string): boolean => [...part].some((c) => FORBIDDEN_CHARS.has(c) || c.charCodeAt(0) < 32);

/** 확장자 -> 편집기 언어(앱 데이터. 코드 분기 없음). 모르면 text. */
export const EXTENSION_LANGUAGE: Readonly<Record<string, string>> = { md: "markdown", markdown: "markdown", html: "html", htm: "html", json: "json" };
/** 미디어 타입 -> 편집기 언어. */
export const MEDIA_TYPE_LANGUAGE: Readonly<Record<string, string>> = { "text/markdown": "markdown", "text/html": "html", "application/json": "json" };

/** 편집기 언어: 미디어 타입 -> 확장자 -> text. */
export function languageForFile(path: string, mediaType?: string): string {
  const byMedia = mediaType === undefined ? undefined : MEDIA_TYPE_LANGUAGE[mediaType.split(";")[0]!.trim().toLowerCase()];
  if (byMedia !== undefined) return byMedia;
  const name = path.split("/").pop() ?? path;
  const dot = name.lastIndexOf(".");
  return dot > 0 ? (EXTENSION_LANGUAGE[name.slice(dot + 1).toLowerCase()] ?? "text") : "text";
}

/** 경로를 검사한다. 문제가 없으면 null. `ignore`는 이름을 바꾸는 중인 자기 자신(중복 검사에서 뺀다). */
export function checkPath(path: string, existing: readonly string[], ignore?: string): PathProblem | null {
  if (path.trim() === "") return "empty";
  if (path.startsWith("/") || /^[a-zA-Z]:/.test(path)) return "absolute";
  const parts = path.split("/");
  if (parts.some((p) => p === "")) return path.endsWith("/") ? "empty" : "absolute";
  if (parts.some((p) => p === ".." || p === ".")) return "dotdot";
  if (parts.some(forbidden)) return "forbidden";
  if (parts.some((p) => RESERVED.test(p.split(".")[0] ?? p))) return "reserved";
  if (parts.some((p) => p.endsWith(".") || p.endsWith(" "))) return "trailing";
  const others = existing.filter((e) => e !== ignore);
  if (others.includes(path)) return "duplicate";
  if (others.some((e) => e.startsWith(`${path}/`) || path.startsWith(`${e}/`))) return "folderConflict";
  return null;
}

/** 파일 하나의 바이트 수. */
export function entrySize(entry: FileEntry): number {
  if (entry.bytes !== undefined) return entry.bytes.length;
  return entry.text === null ? entry.size : new TextEncoder().encode(entry.text).length;
}

/** 모든 파일의 합계 바이트. */
export function totalSize(files: readonly FileEntry[]): number {
  return files.reduce((sum, f) => sum + entrySize(f), 0);
}

/** 이름 바꾸기. `from`이 파일이면 그 파일만, 폴더(접두 경로)이면 아래 전부. 바뀐 파일 수를 함께 돌려준다. */
export function renameEntries(files: readonly FileEntry[], from: string, to: string): { files: FileEntry[]; moved: number } {
  let moved = 0;
  const next = files.map((f) => {
    if (f.path === from) {
      moved += 1;
      return { ...f, path: to };
    }
    if (f.path.startsWith(`${from}/`)) {
      moved += 1;
      return { ...f, path: `${to}${f.path.slice(from.length)}` };
    }
    return f;
  });
  return { files: next, moved };
}

/** 삭제. 폴더이면 아래 전부. */
export function removeEntries(files: readonly FileEntry[], path: string): { files: FileEntry[]; removed: number } {
  const next = files.filter((f) => f.path !== path && !f.path.startsWith(`${path}/`));
  return { files: next, removed: files.length - next.length };
}

/** 파일을 넣는다(같은 경로가 있으면 바꾼다). */
export function upsertEntry(files: readonly FileEntry[], entry: FileEntry): FileEntry[] {
  return files.some((f) => f.path === entry.path) ? files.map((f) => (f.path === entry.path ? entry : f)) : [...files, entry];
}

/** 경로 순(서버가 주는 순서와 같게). */
export function sortEntries(files: readonly FileEntry[]): FileEntry[] {
  return [...files].sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
}

/** 서버 상태 대비 초안의 파일 변경 계획. 올리기(put)가 모두 끝난 뒤에만 삭제한다(이름 바꾸기에서 내용을 잃지 않게). */
export interface FilePlan {
  puts: FileEntry[];
  deletes: string[];
}

/** 파일이 서버 것과 다른가. */
export function entryChanged(origin: FileEntry | undefined, draft: FileEntry): boolean {
  return origin === undefined || draft.bytes !== undefined || draft.text !== origin.text;
}

export function planFileChanges(origin: readonly FileEntry[], draft: readonly FileEntry[]): FilePlan {
  const byPath = new Map(origin.map((f) => [f.path, f]));
  const draftPaths = new Set(draft.map((f) => f.path));
  return {
    puts: draft.filter((f) => entryChanged(byPath.get(f.path), f)),
    deletes: origin.filter((f) => !draftPaths.has(f.path)).map((f) => f.path),
  };
}

/** 바이트 -> 텍스트(UTF-8로 해석되지 않으면 null). */
export function decodeUtf8(bytes: Uint8Array): string | null {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return null;
  }
}

/** 경로의 폴더 부분(`a/b.md` -> `a/`, 폴더 없음 -> ""). */
export function dirOf(path: string): string {
  const i = path.lastIndexOf("/");
  return i < 0 ? "" : path.slice(0, i + 1);
}
