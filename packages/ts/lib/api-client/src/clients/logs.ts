/**
 * 로그 REST(design §4R.10·§4R.11·§4R.12): 출처·수집·세션·타임라인·이벤트·집계·handoff·분류 체계·대시보드 템플릿·보관본.
 * 출처·범주·차원·지표 이름을 모른다(모두 서버가 주는 데이터). 필터는 이름 -> 값(또는 값 목록, 반복 키)이며
 * 어떤 이름이 유효한지는 서버(`GET /logs/schema`의 `filters`)가 정한다.
 */
import type {
  HandoffMatrix,
  LogAggregateRequest,
  LogAggregateRow,
  LogClassifierDescriptor,
  LogDashboard,
  LogEventDetail,
  LogEventPage,
  LogQuerySchema,
  LogScanReport,
  LogSessionSummary,
  LogSourceInfo,
  LogTaxonomy,
  LogTimeline,
  Trace,
} from "@agent-console/contracts";
import { enc, type BlobResponse, type RestIo } from "../io";

/** `LogFilter` 쿼리: 이름 -> 값 하나 또는 여러 개(반복 키). 값이 없거나 빈 문자열이면 보내지 않는다. */
export type LogQueryParams = Readonly<Record<string, string | number | boolean | readonly string[] | null | undefined>>;

/** 보관본 형식. 서버가 모르는 값은 422로 거절한다. */
export type LogArchiveFormat = "html" | "json";

export interface LogArchiveParams {
  /** `LogFilter` 이름(예: 세션 하나만) */
  filter?: LogQueryParams;
  format?: LogArchiveFormat;
  /** HTML 시각 표시 시간대(IANA 이름) */
  tz?: string;
}

/** 필터 객체를 쿼리 문자열로(`?a=1&a=2&b=x`, 없으면 빈 문자열). 반복 키는 다중 값이다. */
export function logQuery(params: LogQueryParams | undefined): string {
  if (params === undefined) return "";
  const parts: string[] = [];
  for (const [name, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    const list = Array.isArray(value) ? (value as readonly string[]) : [String(value)];
    for (const item of list) if (item !== "") parts.push(`${enc(name)}=${enc(item)}`);
  }
  return parts.length === 0 ? "" : `?${parts.join("&")}`;
}

export interface LogsClient {
  /** 출처 목록: 디스크립터(설정 스키마 포함)·켜짐·출처 구분·수집 상태. */
  listLogSources(): Promise<LogSourceInfo[]>;
  listLogClassifiers(): Promise<LogClassifierDescriptor[]>;
  /** 지금 한 번 수집(202). `sourceIds`를 생략하면 켜진 출처 전부. */
  scanLogs(sourceIds?: readonly string[]): Promise<LogScanReport>;
  /** 이벤트 목록(키셋 페이지: 응답 `next_cursor`를 다음 호출의 `cursor` 필터로). */
  listLogEvents(params?: LogQueryParams): Promise<LogEventPage>;
  getLogEvent(uid: string): Promise<LogEventDetail>;
  listLogSessions(params?: LogQueryParams): Promise<LogSessionSummary[]>;
  getLogTimeline(session: string, params?: LogQueryParams): Promise<LogTimeline>;
  /** 세션의 위임 흐름(`logs:trace` 연동이 있을 때만 경로가 있다). */
  getLogSessionTrace(session: string): Promise<Trace>;
  aggregateLogs(request: LogAggregateRequest): Promise<LogAggregateRow[]>;
  getLogHandoffs(params?: LogQueryParams): Promise<HandoffMatrix>;
  getLogTaxonomy(): Promise<LogTaxonomy>;
  listLogDashboardTemplates(): Promise<LogDashboard[]>;
  /** 집계 차원·지표·필터 이름 목록. 이 경로가 없으면(404) 호출하는 쪽이 자유 입력으로 폴백한다. */
  getLogSchema(): Promise<LogQuerySchema>;
  /** 오프라인 보관본(첨부). 파일 이름은 `Content-Disposition`. */
  downloadLogArchive(params?: LogArchiveParams): Promise<BlobResponse>;
  /** 실행에 연결된 세션 로그(`logs:runs` 연동이 있을 때만 경로가 있다). 응답 `total`은 항상 채워진다. */
  listRunLogs(runId: string, params?: LogQueryParams): Promise<LogEventPage>;
}

export function createLogsClient(io: RestIo): LogsClient {
  return {
    listLogSources: () => io.request("GET", "/logs/sources"),
    listLogClassifiers: () => io.request("GET", "/logs/classifiers"),
    scanLogs: (sourceIds) => io.request("POST", "/logs/scan", sourceIds === undefined ? {} : { body: { source_ids: [...sourceIds] } }),
    listLogEvents: (params) => io.request("GET", `/logs/events${logQuery(params)}`),
    getLogEvent: (uid) => io.request("GET", `/logs/events/${enc(uid)}`),
    listLogSessions: (params) => io.request("GET", `/logs/sessions${logQuery(params)}`),
    getLogTimeline: (session, params) => io.request("GET", `/logs/sessions/${enc(session)}/timeline${logQuery(params)}`),
    getLogSessionTrace: (session) => io.request("GET", `/logs/sessions/${enc(session)}/trace`),
    aggregateLogs: (request) => io.request("POST", "/logs/aggregate", { body: request }),
    getLogHandoffs: (params) => io.request("GET", `/logs/handoffs${logQuery(params)}`),
    getLogTaxonomy: () => io.request("GET", "/logs/taxonomy"),
    listLogDashboardTemplates: () => io.request("GET", "/logs/dashboard-templates"),
    getLogSchema: () => io.request("GET", "/logs/schema"),
    downloadLogArchive: (params) =>
      io.requestBlob("GET", `/logs/archive${logQuery({ ...params?.filter, ...(params?.format === undefined ? {} : { format: params.format }), ...(params?.tz === undefined ? {} : { tz: params.tz }) })}`),
    listRunLogs: (runId, params) => io.request("GET", `/runs/${enc(runId)}/logs${logQuery(params)}`),
  };
}
