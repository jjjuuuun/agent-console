/**
 * 전체 REST 클라이언트: 기능 클라이언트(`clients/*`)를 한 객체로 합친 편의 조립.
 * 기능 하나만 쓰려면 하위 경로(`@agent-console/api-client/chat` 등)와 `createRestIo`를 쓴다.
 * 기능 클라이언트끼리는 서로 import하지 않는다(dependency-cruiser로 강제).
 */
import { createArchitectureClient, type ArchitectureClient } from "./clients/architecture";
import { createAgentsClient, type AgentsClient } from "./clients/agents";
import { createCatalogClient, type CatalogClient } from "./clients/catalog";
import { createChatClient, type ChatClient } from "./clients/chat";
import { createCoreClient, type CoreClient } from "./clients/core";
import { createExportsClient, type ExportsClient } from "./clients/exports";
import { createGraphsClient, type GraphsClient } from "./clients/graphs";
import { createImportsClient, type ImportsClient } from "./clients/imports";
import { createInteractionsClient, type InteractionsClient } from "./clients/interactions";
import { createLoginClient, type LoginClient } from "./clients/login";
import { createLogsClient, type LogsClient } from "./clients/logs";
import { createMemoryClient, type MemoryClient } from "./clients/memory";
import { createResourcesClient, type ResourcesClient } from "./clients/resources";
import { createRunsClient, type RunsClient } from "./clients/runs";
import { createSettingsClient, type SettingsClient } from "./clients/settings";
import { createUsageClient, type UsageClient } from "./clients/usage";
import { createVersionsClient, type VersionsClient } from "./clients/versions";
import { createProjectsClient, type ProjectsClient } from "./clients/projects";
import { withSpace } from "./io";
import { createRestIo, type RestClientOptions } from "./transport";

export type { FetchLike, RestClientOptions } from "./transport";
export type { Versioned } from "./io";
export type { ListGraphsParams } from "./clients/graphs";
export type { HandoffParams, ListRunEventsParams, ListRunsParams } from "./clients/runs";
export type { ListConversationsParams, ListTurnsParams, PostMessageResult } from "./clients/chat";
export type { ListInteractionsParams } from "./clients/interactions";
export type { LogArchiveFormat, LogArchiveParams, LogQueryParams } from "./clients/logs";
export type { ListResourcesParams } from "./clients/resources";
export type { ListMemoryEntriesParams, LogIndexPurgeRequest, LogIndexPurgeResult } from "./clients/memory";

/** `/api/v1` REST 호출을 계약 타입으로 감싼 클라이언트(모든 기능). 실패는 모두 `ApiError`. */
export interface RestClient
  extends CoreClient,
    CatalogClient,
    AgentsClient,
    GraphsClient,
    RunsClient,
    ChatClient,
    InteractionsClient,
    UsageClient,
    ResourcesClient,
    ImportsClient,
    SettingsClient,
    ExportsClient,
    VersionsClient,
    LoginClient,
    LogsClient,
    ArchitectureClient,
    MemoryClient,
    ProjectsClient {}

/**
 * REST 클라이언트를 만든다.
 * @param options 서버 주소·토큰·fetch 주입
 */
export function createRestClient(options: RestClientOptions): RestClient {
  const io = createRestIo(options);
  return {
    ...createCoreClient(io),
    ...createCatalogClient(io),
    ...createAgentsClient(io),
    ...createGraphsClient(io),
    ...createRunsClient(io),
    ...createChatClient(io),
    ...createInteractionsClient(io),
    ...createUsageClient(io),
    ...createResourcesClient(io),
    ...createImportsClient(io),
    ...createSettingsClient(io),
    ...createExportsClient(io),
    ...createVersionsClient(io),
    ...createLoginClient(io),
    ...createLogsClient(io),
    ...createArchitectureClient(io),
    ...createMemoryClient(io),
    ...createProjectsClient(io),
  };
}

/**
 * 한 공간(라이브러리 또는 프로젝트 폴더의 사본 저장소)을 보는 정의·메모리 클라이언트. 모든 요청에 `?project=<id>`가 붙는다.
 * `project`가 null·undefined면 공간 인자 없이 `createRestClient`와 같은 주소로 요청한다(라이브러리).
 * 프로젝트 모듈이 없는 서버에는 `project`를 주지 않는다.
 */
export interface SpaceRestClient extends AgentsClient, GraphsClient, ResourcesClient, VersionsClient, MemoryClient {}

/**
 * 공간 하나의 정의·메모리 클라이언트를 만든다.
 * @param options 서버 주소·토큰·fetch 주입
 * @param project 프로젝트 id(`SpaceRef.project_id`). null = 라이브러리
 */
export function createSpaceRestClient(options: RestClientOptions, project: string | null | undefined): SpaceRestClient {
  const io = withSpace(createRestIo(options), project);
  return {
    ...createAgentsClient(io),
    ...createGraphsClient(io),
    ...createResourcesClient(io),
    ...createVersionsClient(io),
    ...createMemoryClient(io),
  };
}
