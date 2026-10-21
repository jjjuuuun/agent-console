import { useCallback, type ReactNode } from "react";
import { Link } from "react-router";
import { LINK_PART_IDS, useLinkPart } from "../../modules";
import { LINK_ROLES, pathForRole } from "./routeLinks";
import { logsMessages as t } from "./messages";

/**
 * 이벤트 상세의 링크 슬롯: 실행(`run_id`) 링크는 연동 부분(`logs.run-link`)이 켜져 있을 때만 링크가 되고(꺼지면 텍스트),
 * 세션 링크는 이 화면의 세션 상세로 간다. 반환값이 undefined면 `LogEventDetail`이 텍스트로 그린다.
 */
export function useLogLinks(): (kind: "run" | "session", id: string) => ReactNode | undefined {
  const runPart = useLinkPart(LINK_PART_IDS.logsRunLink);
  return useCallback(
    (kind, id) => {
      if (kind === "session") return <Link to={`/logs/sessions/${encodeURIComponent(id)}`} title={id}>{id}</Link>;
      if (!runPart.visible) return undefined;
      return (
        <Link to={`${pathForRole(LINK_ROLES.runs)}/${encodeURIComponent(id)}`}>
          {t.detail.openRun}
        </Link>
      );
    },
    [runPart.visible],
  );
}
