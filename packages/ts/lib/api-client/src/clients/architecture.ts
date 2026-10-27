/** 관측 구조도 프로필 REST(`mod-architecture`). 프로필·칸 이름을 모른다(모두 서버가 주는 데이터). */
import type { ArchitectureProfileList } from "@agent-console/contracts";
import type { RestIo } from "../io";

export interface ArchitectureClient {
  /** 병합된 프로필 목록(기본 → 플러그인 → 사용자 순, 끈 프로필은 `disabled`). 프로필이 없어도 200과 빈 목록이다. */
  listArchitectureProfiles(): Promise<ArchitectureProfileList>;
}

export function createArchitectureClient(io: RestIo): ArchitectureClient {
  return {
    listArchitectureProfiles: () => io.request("GET", "/architecture/profiles"),
  };
}
