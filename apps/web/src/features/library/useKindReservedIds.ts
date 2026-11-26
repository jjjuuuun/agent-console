import { useQuery } from "@tanstack/react-query";
import { reservedIdsByKind } from "@agent-console/projects";
import { useApi } from "../../app/ApiContext";
import { PROJECT_REQUIRES } from "../../app/requirements";
import { useRequires } from "../../modules";

const NONE: readonly string[] = [];

/**
 * 정의 종류 하나의 예약어(id로 쓸 수 없는 말). 서버가 종류 메타데이터로 주는 값(`CopyKindInfo.reserved_ids`)만 쓰고 웹에는 목록이 없다.
 * 이 목록을 주는 기능(프로젝트)이 꺼져 있거나 종류를 모르거나 옛 서버면 빈 목록이다(그때는 서버 거절 문구만 보인다).
 * 질의 키는 복사 대화상자의 종류 목록과 같아 캐시를 함께 쓴다.
 */
export function useKindReservedIds(kind: string | undefined): readonly string[] {
  const { rest } = useApi();
  const on = useRequires(PROJECT_REQUIRES).phase === "met" && kind !== undefined;
  const query = useQuery({
    queryKey: ["list", "copy-kinds", ""] as const,
    queryFn: async () => (await rest.listCopyKinds(null)) ?? [],
    enabled: on,
    retry: false,
    staleTime: 60_000,
    meta: { silentBackgroundError: true },
  });
  if (!on || kind === undefined) return NONE;
  return reservedIdsByKind(query.data ?? [])[kind] ?? NONE;
}
