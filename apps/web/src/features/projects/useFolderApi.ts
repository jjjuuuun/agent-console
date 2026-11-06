import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "@agent-console/api-client";
import type { FolderCheck } from "@agent-console/contracts/projects";
import type {
  FolderCapabilitiesData,
  FolderCheckFn,
  FolderCreateFn,
  FolderListFn,
  FolderPickFn,
  FolderRootData,
} from "@agent-console/folder-picker";
import { folderCapabilities, folderCheckOutcome, folderErrorOutcome, folderPickOutcome } from "@agent-console/projects";
import { useApi } from "../../app/ApiContext";

/** 폴더 고르기에 필요한 서버 호출 묶음(folder-picker props 모양). 대화상자 동안 유지한다. */
export interface FolderApi {
  check: FolderCheckFn;
  list: FolderListFn;
  createFolder: FolderCreateFn;
  /** OS 선택 창. 능력 조회 결과가 `native_dialog: false`면 undefined(찾아보기 패널만 쓴다). */
  pickNative: FolderPickFn | undefined;
  capabilities: FolderCapabilitiesData | null;
  roots: readonly FolderRootData[];
  /** 가장 최근에 받은 확인 응답(입력·정규화 경로로 찾는다). 이름·id·구성 폴더 이름 같은 부가 값을 읽는다. */
  lastCheckFor(path: string | null): FolderCheck | undefined;
  /** 마지막으로 받은 `config_dir`(선택 전에도 "{dir} 폴더를 만듭니다" 줄을 채운다). */
  configDir: string | undefined;
}

/**
 * 프로젝트 폴더 REST(`rest`)를 folder-picker 콜백으로 바꾼다. 프로젝트 이름은 `projectName`으로 찾는다.
 * 예상한 거절(409 겹침·같은 폴더, 403 원격 차단)은 던지지 않고 결과 종류로 돌려준다.
 */
export function useFolderApi(projectName: (id: string) => string | undefined, options: { excludeProjectId?: string } = {}): FolderApi {
  const { rest } = useApi();
  const [capabilities, setCapabilities] = useState<FolderCapabilitiesData | null>(null);
  const [roots, setRoots] = useState<readonly FolderRootData[]>([]);
  const [configDir, setConfigDir] = useState<string | undefined>(undefined);
  const checks = useRef(new Map<string, FolderCheck>());
  const nameRef = useRef(projectName);
  useEffect(() => {
    nameRef.current = projectName;
  });

  useEffect(() => {
    let alive = true;
    rest.getFolderCapabilities().then((c) => alive && c != null && setCapabilities(folderCapabilities(c)), () => undefined);
    rest.listFolders().then((l) => alive && l != null && setRoots((l.roots ?? []).map((r) => ({ kind: r.kind, path: r.path, label: r.label ?? r.path }))), () => undefined);
    return () => {
      alive = false;
    };
  }, [rest]);

  return useMemo<FolderApi>(() => {
    const remember = (c: FolderCheck) => {
      checks.current.set(c.input, c);
      if (c.path != null) checks.current.set(c.path, c);
      if (c.config_dir != null && c.config_dir !== "") setConfigDir(c.config_dir);
    };
    const names = { projectName: (id: string) => nameRef.current(id) };
    const check: FolderCheckFn = async (request, signal) => {
      try {
        const result = await rest.checkFolder({
          path: request.path,
          ...(request.create === true ? { create: true } : {}),
          ...((request.excludeProjectId ?? options.excludeProjectId) ? { exclude_project_id: request.excludeProjectId ?? options.excludeProjectId ?? null } : {}),
        });
        if (signal.aborted) throw new DOMException("aborted", "AbortError");
        remember(result);
        return folderCheckOutcome(result, names);
      } catch (e) {
        if (e instanceof ApiError) {
          const outcome = folderErrorOutcome(e, names);
          if (outcome !== null) return outcome;
        }
        throw e;
      }
    };
    const list: FolderListFn = async (request) => {
      const l = await rest.listFolders({ path: request.path, hidden: request.hidden });
      return {
        path: l.path,
        parent: l.parent ?? null,
        entries: (l.entries ?? []).map((e) => ({
          name: e.name,
          path: e.path,
          ...(e.hidden === undefined ? {} : { hidden: e.hidden }),
          ...(e.link === undefined ? {} : { link: e.link }),
          ...(e.locked === undefined ? {} : { locked: e.locked }),
          project_id: e.project_id ?? null,
          project_name: e.project_id == null ? null : (nameRef.current(e.project_id) ?? e.project_id),
        })),
        ...(l.truncated === undefined ? {} : { truncated: l.truncated }),
        ...(l.timed_out === undefined ? {} : { timed_out: l.timed_out }),
        ...(l.hidden_count === undefined ? {} : { hidden_count: l.hidden_count }),
      };
    };
    const createFolder: FolderCreateFn = async (request) => {
      const sep = request.parent.includes("\\") && !request.parent.includes("/") ? "\\" : "/";
      const path = `${request.parent.replace(/[\\/]+$/, "")}${sep}${request.name}`;
      try {
        const r = await rest.createFolder(path);
        return { ok: true, path: r.path ?? path };
      } catch (e) {
        if (e instanceof ApiError) return { ok: false, code: e.code.replace(/^folders\./, ""), message: e.message };
        throw e;
      }
    };
    const pickNative: FolderPickFn | undefined = async (initial, signal) => {
      const r = await rest.pickFolder(initial === undefined ? {} : { initial }, { signal });
      if (r.check) remember(r.check);
      return folderPickOutcome(r, names);
    };
    return {
      check,
      list,
      createFolder,
      pickNative: capabilities?.native_dialog === false ? undefined : pickNative,
      capabilities,
      roots,
      lastCheckFor: (path) => (path === null ? undefined : checks.current.get(path)),
      configDir,
    };
  }, [rest, capabilities, roots, configDir, options.excludeProjectId]);
}
