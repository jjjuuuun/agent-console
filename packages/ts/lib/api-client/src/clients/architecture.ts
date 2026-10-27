/** 관측 구조도 프로필 REST(`mod-architecture`). 프로필·칸 이름을 모른다(모두 서버가 주는 데이터). */
import type { ArchitectureProfileCheckRequest, ArchitectureProfileCheckResult, ArchitectureProfileDetail, ArchitectureProfileList } from "@agent-console/contracts";
import type { RestIo } from "../io";

export interface ArchitectureClient {
  /** 병합된 프로필 목록(기본 → 플러그인 → 사용자 순, 끈 프로필은 `disabled`). 프로필이 없어도 200과 빈 목록이다. */
  listArchitectureProfiles(): Promise<ArchitectureProfileList>;
  /** 프로필 하나(본문 + 검사 결과). 끈 프로필도 받는다. 없으면 404 `architecture.profile_not_found`. */
  getArchitectureProfile(id: string): Promise<ArchitectureProfileDetail>;
  /** 편집 중인 프로필 본문을 검사한다. 형식 오류도 문제 목록으로 돌려준다(저장 여부는 호출자가 정한다). */
  checkArchitectureProfile(body: ArchitectureProfileCheckRequest): Promise<ArchitectureProfileCheckResult>;
}

export function createArchitectureClient(io: RestIo): ArchitectureClient {
  return {
    listArchitectureProfiles: () => io.request("GET", "/architecture/profiles"),
    getArchitectureProfile: (id) => io.request("GET", `/architecture/profiles/${encodeURIComponent(id)}`),
    checkArchitectureProfile: (body) => io.request("POST", "/architecture/profiles/check", { body }),
  };
}
