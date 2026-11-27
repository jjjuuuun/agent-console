import { useMemo, useState } from "react";
import { projectAbilities } from "@agent-console/projects";
import { useProjectsText } from "./projectsText";
import { useApi } from "../../app/ApiContext";
import { ProjectProblemBanner } from "./ProjectProblemBanner";
import { problemBanners, type BannerAction, type BannerSpec } from "./projectHomeLib";
import { useFolderHomeMessages } from "./folderHomeMessages";
import { useProjects } from "./ProjectsContext";

/** 목록 화면에서 처리하는 동작. 나머지(경로 복사·등록 해제 등)는 프로젝트 홈에서 한다. */
const LIST_ACTIONS: ReadonlySet<BannerAction> = new Set<BannerAction>(["recheck", "repath", "setFolder"]);

export interface ProjectRecordsState {
  /** 현재 프로젝트의 폴더·기록 문제 배너(프로젝트 홈과 같은 문구). 없으면 빈 배열 */
  banners: readonly BannerSpec[];
  /** 기록을 읽을 수 없는 상태(폴더 없음·기록 DB 사용 불가). 목록 오류 대신 이 안내를 보인다 */
  blocking: boolean;
}

/**
 * 현재 프로젝트의 기록 상태를 목록 화면용으로 풀어 준다(채팅·실행 기록 목록이 공유).
 * 문구·버튼은 프로젝트 홈의 `problemBanners`를 그대로 쓰고, 목록에서 처리할 수 있는 동작만 남긴다.
 */
export function useProjectRecordsState(): ProjectRecordsState {
  const { currentView } = useProjects();
  const m = useFolderHomeMessages();
  return useMemo(() => {
    if (currentView === undefined || currentView.project.archived === true) return { banners: [], blocking: false };
    const banners = problemBanners(currentView, m)
      .filter((b) => b.kind === "folder" || b.kind === "records" || b.kind === "readonly")
      .map((b) => ({ ...b, actions: b.actions.filter((a) => LIST_ACTIONS.has(a)) }));
    return { banners, blocking: banners.some((b) => b.kind === "folder") || currentView.records_state === "unavailable" };
  }, [currentView, m]);
}

/** 채팅·실행 목록 위에 붙는 폴더·기록 상태 띠(표현은 `ProjectProblemBanner`). 문제가 없으면 아무것도 그리지 않는다. */
export function ProjectRecordsNotice({ banners }: { banners: readonly BannerSpec[] }) {
  const m = useFolderHomeMessages();
  const { rest } = useApi();
  const p = useProjects();
  const id = p.current;
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  if (banners.length === 0 || id === null) return null;
  const onAction = (action: BannerAction, banner: BannerSpec) => {
    if (action === "repath" || action === "setFolder") {
      p.requestRepath(id);
      return;
    }
    if (action !== "recheck") return;
    setBusy(banner.id);
    void rest
      .getProject(id)
      .then(() => p.refresh())
      .then(() => setNote(new Date().toTimeString().slice(0, 5)))
      .finally(() => setBusy(null));
  };
  return (
    <div className="prj-records-notice">
      <ProjectProblemBanner banners={banners} onAction={onAction} busy={busy} note={note === null ? null : m.problem.stillOpen(note)} />
    </div>
  );
}


/**
 * 현재 프로젝트에서 새 대화·실행을 시작할 수 없는 이유 문구(막혀 있지 않으면 null).
 * 프로젝트 홈·시작 대화상자와 같은 능력표(`projectAbilities`)의 첫 이유를 쓴다. 목록 화면의 [새 대화] 같은 단추가 aria-disabled + 이유로 쓴다.
 */
export function useStartBlockReason(action: "start_chat" | "start_run" | "copy_in"): string | null {
  const projectText = useProjectsText();
  const { currentView } = useProjects();
  if (currentView === undefined) return null;
  const a = projectAbilities(currentView, { recordsWritable: currentView.records_writable !== false })[action];
  return a.allowed || a.reason === null ? null : projectText(a.reason);
}
