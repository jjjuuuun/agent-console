import { useProjectsText } from "./projectsText";
import type { ReactNode } from "react";
import { useSpace } from "./SpaceScope";

export interface NewScope {
  /** 정의 본문에 펼칠 조각. 새 정의의 저장 위치는 화면(공간)이 정하므로 항상 빈 객체다(본문에 `project`를 찍지 않는다) */
  patch: { project?: string };
  /** 만들기 대화상자의 `extra`에 끼울 읽기 전용 한 줄 "저장 위치: 프로젝트 {이름}"(프로젝트 사본 화면에서만, 공용이면 null) */
  field: ReactNode;
}


/**
 * 새 정의의 저장 위치 표시(screen-projects §5.3). 범위를 고르는 입력은 없다: 공용 구성 화면에서 만들면 공용,
 * 프로젝트 사본(`?prj=`) 화면에서 만들면 그 프로젝트에 저장된다. 호출자가 대화상자를 열 때마다 새로 마운트한다.
 */
export function useNewScope(): NewScope {
  const spaceText = useProjectsText();
  const space = useSpace();
  return {
    patch: {},
    field:
      space === null ? null : (
        <p className="lib-field-note app-muted" data-testid="save-location">
          {spaceText({ key: "space.save_location", params: { name: space.project.name } })}
        </p>
      ),
  };
}
