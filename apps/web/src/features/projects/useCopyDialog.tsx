import { useCallback, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useToast } from "@agent-console/ui";
import { createProjectsText, toSpaceRef } from "@agent-console/projects";
import type { DefinitionKey } from "@agent-console/contracts";
import { useApi } from "../../app/ApiContext";
import { DEFAULT_ROUTES } from "../../shell/routeConfig";
import { CopyPlanDialog, type CopyDirection, type CopyOutcome } from "./CopyPlanDialog";
import { useProjects } from "./ProjectsContext";
import { useSpaceItems, type SpaceItem } from "./useSpaceItems";

const text = createProjectsText();

/** 복사 대화상자를 여는 요청. 공용이 아닌 쪽 공간은 항상 프로젝트 하나(`project`)다. */
export interface CopyRequest {
  /** import = 공용 → 프로젝트, save = 프로젝트 → 공용, move = 옛 프로젝트 전용 구성 정리(공용 → 프로젝트, 원본 지우기 기본 켜짐) */
  direction: CopyDirection;
  /** 프로젝트 등록 id */
  project: string;
  /** 고르기부터(`pick`) 또는 고른 항목으로 계획부터(`plan`) */
  start: "pick" | "plan";
  items?: readonly DefinitionKey[];
  /** 고르기 목록을 이 종류들로 좁힌다(호출 화면이 한 종류만 가져올 때, 예: 새 스펙의 문서 틀). 생략하면 서버가 준 복사 종류 전부 */
  onlyKinds?: readonly string[];
  /** [가져오고 실행] 진입의 제출 문구 */
  submitStyle?: "default" | "run";
  /** 옛 방식으로 만든 이 프로젝트 전용 정의를 옮기는 계획(`planLegacyCopy`)을 쓴다. `direction: "move"`와 함께 쓴다 */
  legacy?: boolean;
  /** 적용 응답마다(구성 표 새로 읽기·자동 선택·가져오고 실행의 재시도 등) */
  onApplied?: (outcome: CopyOutcome) => void;
}

export interface CopyDialogApi {
  open: (request: CopyRequest) => void;
  /** 화면 어디든 한 번 그린다(열려 있을 때만 마운트되어 열 때마다 새로 시작한다) */
  dialog: ReactNode;
}

/** 공용 구성 화면으로 가는 링크 주소: 구성 종류를 맡은 라우트 중 첫 번째(라우트 데이터). */
function libraryHome(): string | undefined {
  return DEFAULT_ROUTES.find((r) => r.serves !== undefined && r.serves.startsWith("definition:"))?.path;
}

/**
 * 복사 계획 대화상자를 여는 훅(컨테이너 쪽 조립). 복사 호출·목록 읽기·토스트·캐시 갱신을 맡고,
 * 대화상자 자체(`CopyPlanDialog`)는 props만 받는다. 프로젝트 기능이 꺼져 있으면 `open`은 아무것도 하지 않는다.
 */
export function useCopyDialog(): CopyDialogApi {
  const [request, setRequest] = useState<CopyRequest | null>(null);
  const open = useCallback((r: CopyRequest) => setRequest(r), []);
  const close = useCallback(() => setRequest(null), []);
  return useMemo(() => ({ open, dialog: request === null ? null : <CopyDialogHost request={request} onClose={close} /> }), [open, request, close]);
}

function CopyDialogHost({ request, onClose }: { request: CopyRequest; onClose: () => void }) {
  const { rest } = useApi();
  const p = useProjects();
  const toast = useToast();
  const queryClient = useQueryClient();
  const view = p.views.find((v) => v.project.id === request.project);
  const toProject = request.direction !== "save";
  // 공용 → 프로젝트는 `portable`, 프로젝트 → 공용은 `library`인 종류만(서버 종류 메타데이터, 종류 이름 표 없음)
  const flag = toProject ? "portable" : "library";
  const source = useSpaceItems(toProject ? null : request.project, flag, true);
  const target = useSpaceItems(toProject ? request.project : null, flag, true);
  const only = request.onlyKinds;
  const narrow = (items: readonly SpaceItem[]) => (only === undefined ? [...items] : items.filter((i) => only.includes(i.kind)));
  const homeHref = libraryHome();
  if (view === undefined) return null;
  const name = view.project.name;
  const dir = view.config_dir ?? text("projects.dir_fallback");

  const applied = (o: CopyOutcome) => {
    void queryClient.invalidateQueries({ queryKey: ["list"] });
    if (o.allOk) {
      const total = o.summary.ok;
      const first = o.first === null ? undefined : o.summary.rows.find((r) => r.kind === o.first?.kind && (r.newId ?? r.id) === o.first.id);
      const label = first === undefined ? name : (first.newId ?? first.id);
      toast({
        tone: "success",
        text: total > 1 ? text({ key: "copy.result.toast_many", params: { name: label, n: total - 1 } }) : text({ key: "copy.result.toast_one", params: { name: label } }),
        durationMs: 8000,
        ...(request.direction === "save" ? {} : { action: { label: text("copy.result.open"), onClick: () => p.openHome(request.project) } }),
      });
    }
    request.onApplied?.(o);
  };

  return (
    <CopyPlanDialog
      direction={request.direction}
      {...(request.submitStyle === undefined ? {} : { submitStyle: request.submitStyle })}
      projectName={name}
      projectDir={dir}
      source={toSpaceRef(toProject ? null : request.project)}
      target={toSpaceRef(toProject ? request.project : null)}
      initialStep={request.start}
      {...(request.items === undefined ? {} : { initialItems: request.items })}
      candidates={narrow(source.items)}
      candidatesLoading={source.loading}
      candidatesFailed={source.failed}
      onCandidatesRetry={source.retry}
      targetItems={narrow(target.items)}
      emptyAction={homeHref === undefined || request.direction === "save" ? undefined : <Link className="ac-btn" data-variant="secondary" data-size="sm" to={homeHref} onClick={onClose}>{text("copy.pick.to_library")}</Link>}
      {...(request.direction === "move" ? { removeSourceDefault: true } : {})}
      planCopy={(r) => (request.legacy === true ? rest.planLegacyCopy(request.project) : rest.planCopy(r))}
      applyCopy={(r) => rest.applyCopy(r)}
      text={text}
      onApplied={applied}
      onClose={onClose}
    />
  );
}
