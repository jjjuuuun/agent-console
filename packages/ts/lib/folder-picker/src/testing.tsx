import type { FolderCheckData, FolderCheckOutcome, FolderEntryData, FolderListingData } from "./types";

/** 테스트용 확인 결과 만들기. */
export function sampleCheck(over: Partial<FolderCheckData> = {}): FolderCheckData {
  const path = over.path === undefined ? (over.input ?? "/srv/app") : over.path;
  return { input: path ?? "", path, exists: true, is_dir: true, readable: true, writable: true, can_create: false, nearest_existing: path, ...over };
}
export const checked = (over: Partial<FolderCheckData> = {}): FolderCheckOutcome => ({ kind: "checked", check: sampleCheck(over) });

/** 테스트용 폴더 항목 n개. */
export function sampleEntries(n: number, base = "/srv"): FolderEntryData[] {
  return Array.from({ length: n }, (_, i) => ({ name: `dir-${String(i).padStart(4, "0")}`, path: `${base}/dir-${String(i).padStart(4, "0")}` }));
}
export function sampleListing(path: string, entries: FolderEntryData[], over: Partial<FolderListingData> = {}): FolderListingData {
  const idx = path.lastIndexOf("/");
  return { path, parent: path === "/" ? null : idx <= 0 ? "/" : path.slice(0, idx), entries, ...over };
}
