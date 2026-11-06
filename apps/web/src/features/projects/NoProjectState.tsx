import { Link } from "react-router";
import { Button, Icon } from "@agent-console/ui";
import { folderHomeMessages } from "./folderHomeMessages";

export interface NoProjectStateProps {
  /** [폴더 추가] — 폴더 추가 대화상자를 연다 */
  onAddFolder: () => void;
  /** 공용 구성 화면 주소. 없으면 링크 버튼을 그리지 않는다 */
  libraryHref?: string | undefined;
  /** 문구 덮어쓰기(기본: 프로젝트 문구 표) */
  messages?: Partial<{ title: string; body: string; add: string; goLibrary: string }>;
}

/**
 * 프로젝트가 0개일 때 기능 화면 본문 전체를 대체하는 상태(screen-projects §7.2). 기능 이름을 모르며 모든 화면이 같은 문구를 쓴다.
 * 필터·탭·화면 액션은 이 부품 밖(호출한 화면)이 그리지 않는 것으로 보장한다.
 */
export function NoProjectState({ onAddFolder, libraryHref, messages }: NoProjectStateProps) {
  const t = { ...folderHomeMessages.none, ...messages };
  return (
    <div className="prj-none" role="region" aria-labelledby="prj-none-title" data-testid="no-project-state">
      <span className="prj-none-icon" aria-hidden="true"><Icon name="folder" size={40} /></span>
      <h2 id="prj-none-title" className="prj-none-title">{t.title}</h2>
      <p className="prj-none-body">{t.body}</p>
      <div className="prj-none-actions">
        <Button variant="primary" onClick={onAddFolder}>{t.add}</Button>
        {libraryHref === undefined ? null : (
          <Link className="ac-btn" data-variant="ghost" data-size="md" to={libraryHref}>{t.goLibrary}</Link>
        )}
      </div>
    </div>
  );
}
