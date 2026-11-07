/** 사용량 REST. */
import type { UsageReport, UsageSourceInfo } from "@agent-console/contracts";
import { query, type RestIo } from "../io";

export interface UsageClient {
  /**
   * 사용량 보고. `parts`로 필요한 부분만 요청한다(예: `["windows"]`: 실행 기록을 읽지 않는 가벼운 응답). 생략하면 서버가 전부 계산한다.
   * `project`를 주면 토큰 합계(rollups)를 그 프로젝트 기록만으로 센다. 창 스냅샷은 계정 값 그대로다. 생략·null이면 전체.
   * 알 수 없는 부분 이름은 서버가 무시한다.
   */
  getUsage(parts?: readonly string[], project?: string | null): Promise<UsageReport>;
  listUsageSources(): Promise<UsageSourceInfo[]>;
}

export function createUsageClient(io: RestIo): UsageClient {
  return {
    getUsage: (parts, project) =>
      io.request("GET", `/usage${query({ parts: parts === undefined ? undefined : parts.join(","), project: project ?? undefined })}`),
    listUsageSources: () => io.request("GET", "/usage/sources"),
  };
}
