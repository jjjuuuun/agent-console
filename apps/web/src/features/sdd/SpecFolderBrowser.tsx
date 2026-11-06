/**
 * 프로젝트 폴더 안 하위 폴더 고르기(screen-sdd §4.2·§4.4). `@agent-console/folder-picker`의 `FolderBrowser`를 `rootPath=""`(프로젝트 폴더 기준 상대 경로)로 쓰고,
 * 가져오기 목록 응답(`dirs`)을 그 목록 모양으로 바꿔 준다. 서버 호출은 `load` props이고, 한 단계만 열며 폴더 밖 이동은 막힌다.
 */
import "@agent-console/folder-picker/styles.css";
import { useCallback } from "react";
import { FolderBrowser, createTranslate, type FolderListFn, type FolderListingData } from "@agent-console/folder-picker";
import type { ImportFileListing } from "@agent-console/contracts/sdd";

export interface SpecFolderBrowserProps {
  id: string;
  /** 폴더 하나의 목록(프로젝트 폴더 기준 상대 경로, 빈 값 = 루트). */
  load: (path: string) => Promise<ImportFileListing>;
  /** 처음 열 폴더(빈 값 = 루트). 값이 바뀌어도 다시 열지 않는다 — 다시 열려면 `key`를 바꾼다 */
  startPath?: string;
  /** 첫 조각 이름(프로젝트 폴더). */
  rootLabel: string;
  /** 폴더 목록이 도착했다(가져오기는 이 응답의 파일 목록도 쓴다). */
  onListing?: (path: string, listing: ImportFileListing) => void;
  /** 목록 읽기 실패(오류 문구는 호출자가 보인다). */
  onError?: (error: unknown) => void;
  /** 폴더로 들어갔다. */
  onNavigate?: (path: string) => void;
  /** [이 폴더 선택]. */
  onSelect?: (path: string) => void;
}

const translate = createTranslate();
const joinPath = (folder: string, name: string) => (folder === "" ? name : `${folder.replace(/\/+$/, "")}/${name}`);
const parentOf = (path: string) => (path === "" ? null : path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "");

export function SpecFolderBrowser({ id, load, startPath = "", rootLabel, onListing, onError, onNavigate, onSelect }: SpecFolderBrowserProps) {
  const list: FolderListFn = useCallback(
    async ({ path }, signal) => {
      try {
        const listing = await load(path);
        if (!signal.aborted) onListing?.(listing.path ?? path, listing);
        const base = listing.path ?? path;
        return {
          path: base,
          parent: parentOf(base),
          entries: (listing.dirs ?? []).map((d) => ({ name: d.name, path: joinPath(base, d.name) })),
          truncated: listing.truncated === true,
        } satisfies FolderListingData;
      } catch (e) {
        if (!signal.aborted) onError?.(e);
        throw e;
      }
    },
    [load, onListing, onError],
  );
  return (
    <div className="sdd-browse">
      <FolderBrowser
        id={id}
        t={translate}
        roots={[]}
        rootPath=""
        rootLabel={rootLabel}
        startPath={startPath}
        list={list}
        showHiddenToggle={false}
        autoFocus={false}
        {...(onNavigate ? { onNavigate } : {})}
        {...(onSelect ? { onSelect } : {})}
      />
    </div>
  );
}
