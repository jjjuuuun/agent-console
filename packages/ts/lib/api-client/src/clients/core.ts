/** 핵심 조회: 부트스트랩·서버 정보·모듈 목록. 모듈과 무관하게 서버에 항상 있다. */
import type { BootstrapResponse, ModuleInfo, ModuleOptionsView, ServerInfo } from "@agent-console/contracts";
import type { RestIo } from "../io";

export interface CoreClient {
  getBootstrap(): Promise<BootstrapResponse>;
  /** 서버 버전·계약 버전·플러그인(읽기 전용, 비밀 제외). */
  getServerInfo(): Promise<ServerInfo>;
  /** 이 서버의 기능 모듈과 상태(토큰 없이 읽을 수 있다). 웹이 화면을 조립하는 근거. */
  listModules(): Promise<ModuleInfo[]>;
  /** 모듈 옵션의 읽기 전용 보기(스키마·가린 값·YAML 조각). 모르는 id는 404. */
  getModuleOptions(id: string): Promise<ModuleOptionsView>;
}

export function createCoreClient(io: RestIo): CoreClient {
  return {
    getBootstrap: () => io.request("GET", "/bootstrap"),
    getServerInfo: () => io.request("GET", "/server-info"),
    listModules: () => io.request("GET", "/modules"),
    getModuleOptions: (id) => io.request("GET", `/modules/${encodeURIComponent(id)}/options`),
  };
}
