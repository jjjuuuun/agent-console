import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { findHangulLiterals } from "./hangulLiterals";

/** `i18nPending.json`의 모양. */
export interface I18nPendingData {
  description?: string;
  /** 영구 허용(예시·테스트 데이터·언어 데이터). */
  exempt: { path: string; reason: string }[];
  /** 아직 옮기지 않은 곳(작업 묶음 이름 → 경로 목록). I.12가 하나씩 지운다. */
  pending: Record<string, string[]>;
}

/** 저장소 기준 경로(`/` 구분)가 항목(끝이 `/`면 폴더, 아니면 파일)에 드는가. */
export function matchesEntry(repoPath: string, entry: string): boolean {
  return entry.endsWith("/") ? repoPath.startsWith(entry) : repoPath === entry;
}

const SKIP_DIRS = new Set(["node_modules", "dist"]);

/** 폴더 아래 화면 소스(.ts·.tsx, 테스트·`.d.ts` 제외)의 저장소 기준 경로 목록. */
export function listScreenSources(root: string, repoRoot: string): string[] {
  const out: string[] = [];
  const visit = (dir: string): void => {
    for (const name of readdirSync(dir)) {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) {
        if (!SKIP_DIRS.has(name)) visit(path);
      } else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) && !/\.d\.ts$/.test(name)) {
        out.push(relative(repoRoot, path).replaceAll("\\", "/"));
      }
    }
  };
  visit(root);
  return out.sort();
}

/** 파일별 한글 문자열 조각(허용 목록에 안 든 것만 `unexpected`, 든 것은 `allowed`로 센다). */
export interface HangulReport {
  /** 허용되지 않은 곳의 한글: 경로 → 조각들. */
  unexpected: Record<string, string[]>;
  /** 허용 항목별 한글 문자열 수(항목 경로 → 수). 0이면 낡은 항목이다. */
  allowedCounts: Record<string, number>;
}

/**
 * 파일들을 읽어 한글 문자열을 허용 목록(exempt + pending)과 대조한다.
 * @param files 저장소 기준 경로 목록
 * @param repoRoot 저장소 폴더
 * @param data 허용 목록 데이터
 */
export function scanHangul(files: readonly string[], repoRoot: string, data: I18nPendingData): HangulReport {
  const entries = [...data.exempt.map((e) => e.path), ...Object.values(data.pending).flat()];
  const allowedCounts: Record<string, number> = Object.fromEntries(entries.map((e) => [e, 0]));
  const unexpected: Record<string, string[]> = {};
  for (const file of files) {
    const hits = findHangulLiterals(file, readFileSync(join(repoRoot, file), "utf8"));
    if (hits.length === 0) continue;
    const owners = entries.filter((e) => matchesEntry(file, e));
    if (owners.length === 0) unexpected[file] = hits;
    else allowedCounts[owners[0]!] = (allowedCounts[owners[0]!] ?? 0) + hits.length; // 허용(exempt)이 앞서 있어 먼저 맞는 항목이 가진다
  }
  return { unexpected, allowedCounts };
}

/** 묶음 이름별 남은 한글 문자열 수(I.12 분량 보고용). */
export function pendingTotals(data: I18nPendingData, allowedCounts: Record<string, number>): Record<string, number> {
  return Object.fromEntries(Object.entries(data.pending).map(([group, paths]) => [group, paths.reduce((sum, p) => sum + (allowedCounts[p] ?? 0), 0)]));
}
