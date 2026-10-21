/** 사용량 REST. */
import type { UsageReport, UsageSourceInfo } from "@agent-console/contracts";
import { query, type RestIo } from "../io";

export interface UsageClient {
  /**
   * 사용량 보고. `parts`로 필요한 부분만 요청한다(예: `["windows"]`: 실행 기록을 읽지 않는 가벼운 응답). 생략하면 서버가 전부 계산한다.
   * 알 수 없는 부분 이름은 서버가 무시한다.
   */
  getUsage(parts?: readonly string[]): Promise<UsageReport>;
  listUsageSources(): Promise<UsageSourceInfo[]>;
}

export function createUsageClient(io: RestIo): UsageClient {
  return {
    getUsage: (parts) => io.request("GET", `/usage${query(parts === undefined ? undefined : { parts: parts.join(",") })}`),
    listUsageSources: () => io.request("GET", "/usage/sources"),
  };
}
