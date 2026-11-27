import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * 프로젝트 전용 정의 범위(옛 `project` 필드·범위 배지·공용으로 옮기기)와 함께 지운 이름을 웹이 다시 쓰지 않는다.
 * `@agent-console/projects`가 이 내보내기를 지워도(0.2.0) 웹이 깨지지 않음을 보증한다.
 * 이름을 코드 조각으로 쪼개 두어 이 파일 자신은 검사에 걸리지 않는다.
 */
const RETIRED = [
  // 웹 잔재
  "useProjectScopeFilter", "ProjectTag", "ScopeFilter", "useMoveIssueToShared", "MoveIssueToShared", "useScopedList", "ScopedList", "MoveToProjectDialog", "MoveItem", "useProjectMove", "SCOPE_VIEW_STORAGE_KEY", "createFakeProjects", "projectsOverrides",
  // @agent-console/projects의 지울 내보내기
  "DEFAULT_SCOPE_VIEW_MODE", "SCOPE_GROUP_ORDER", "SCOPE_VIEW_MODES", "defaultScopeFor", "filterByScope", "groupByScope", "groupOf", "isShared", "isVisible", "normalizeScope", "withScope",
  "NewScopePreferences", "ScopeGroup", "ScopeViewMode", "VisibilityOptions", "DEFAULT_BADGE_MESSAGES", "SCOPE_BADGE_KEYS", "badgeLabel", "scopeBadge",
  "MOVE_TO_SHARED_SUGGESTION_ID", "SCOPE_ISSUE_CODES", "isRequiredMove", "mergeMovePlans", "moveKey", "moveTargetOfIssue", "selectMoves",
  "createProjectsClient", "ProjectsClient", "ProjectsIo", "ProjectsVersioned", "configDirLabel",
].map((n) => new RegExp(`\\b${n}\\b`));

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "node_modules" ? [] : sources(path);
    return /\.(ts|tsx)$/.test(name) ? [path] : [];
  });
}

/** 소스 전체를 훑는 테스트의 시간 한도(부하가 있으면 기본 5초를 넘는다). */
const SCAN_TIMEOUT = 60_000;

describe("옛 범위 이름 사용 0", () => {
  it("웹 소스에 지운 이름이 없다", () => {
    const self = resolve(__dirname, "retiredScopeNames.test.ts");
    const hits: string[] = [];
    for (const file of sources(resolve(__dirname, ".."))) {
      if (file === self) continue;
      const text = readFileSync(file, "utf8");
      for (const re of RETIRED) if (re.test(text)) hits.push(`${file}: ${re.source}`);
    }
    expect(hits).toEqual([]);
  }, SCAN_TIMEOUT);

  it("log-view 세션 목록은 summary.project를 읽지 않는다", () => {
    const text = readFileSync(resolve(__dirname, "../../../../packages/ts/lib/log-view/src/SessionList.tsx"), "utf8");
    expect(/\bs\.project\b/.test(text)).toBe(false);
  });
});
