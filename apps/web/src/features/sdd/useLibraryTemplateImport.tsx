/**
 * 새 스펙 대화상자의 [공용에서 가져오기…](screen-sdd §4.1, 6R.20c): 공용 문서 틀을 이 프로젝트로 복사하는 복사 계획 대화상자를 연다.
 * 종류 목록·항목은 서버가 준다(복사 종류 메타데이터). 문서 틀 종류 이름은 공용 틀 하나의 `kind`에서 읽는다(코드에 이름이 없다).
 * 복사가 끝나면 스펙 질의를 다시 읽게 해 열려 있는 새 스펙 대화상자의 틀 목록이 갱신된다.
 */
import { useMemo, type ReactNode } from "react";
import { useCopyDialog } from "../projects";
import { useApi } from "../../app/ApiContext";
import { useInvalidateSdd } from "./useSddApi";
import { useSddContext } from "./useSddContext";
import { useTemplateKind } from "./useTemplateApi";

export interface LibraryTemplateImport {
  /** 이 조립에서 쓸 수 있는가(프로젝트가 있고 정의 모듈이 있어 공용 틀이 있을 때) */
  available: boolean;
  open: () => void;
  /** 화면 어디든 한 번 그린다 */
  dialog: ReactNode;
}

/** @param enabled false면 문서 틀 종류를 읽지 않는다(새 스펙 대화상자가 닫혀 있을 때) */
export function useLibraryTemplateImport(enabled = true): LibraryTemplateImport {
  const ctx = useSddContext();
  const copy = useCopyDialog();
  const invalidate = useInvalidateSdd();
  const { sdd } = useApi();
  const library = useMemo(() => sdd(null), [sdd]);
  const project = ctx.projectId;
  const kind = useTemplateKind(library, "", undefined, enabled && project !== null && ctx.capabilities.templates);
  const available = project !== null && kind !== undefined && ctx.capabilities.templates;
  return {
    available,
    open: () => {
      if (project === null || kind === undefined) return;
      copy.open({ direction: "import", project, start: "pick", onlyKinds: [kind], onApplied: () => void invalidate() });
    },
    dialog: copy.dialog,
  };
}
