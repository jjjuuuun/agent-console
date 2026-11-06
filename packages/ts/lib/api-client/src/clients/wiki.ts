/**
 * 위키 REST(design §7R.7, 계약 `wiki` 1.0.0): 위키 목록·보기·저장·삭제, 페이지 목록·보기·쓰기·미리보기·이름 바꾸기·지우기,
 * 기록(목록·버전 본문·되돌리기), 링크 넣기 글자·페이지 틀, 검색·그래프·점검·최근 변경·유효 문법·다시 읽기, zip 내보내기·가져오기, 위키 규칙.
 * 서버: `mod-wiki`(`/api/v1/wiki…`). 공간 인자(`?project=`)는 `withSpace(io, project)`가 맡는다: `createWikiClient(withSpace(io, "payments"))`.
 * 링크 문법·머리말 키·규칙 id·동작 이름·폴더 이름을 모른다(전부 서버가 주는 데이터).
 *
 * 쓰기 헤더: 있는 페이지를 고칠 때는 `expectedHash`(`If-Match`)가 필수(없으면 428), 새 페이지는 `createOnly`(`If-None-Match: *`).
 * 해시가 틀리면 412 `version_conflict`(+ `ETag`). 규칙 경고 등은 응답 헤더 `X-Console-Issues`가 `Versioned.issues`로 온다.
 */
import type { ResourceFile } from "@agent-console/contracts";
import type {
  EffectiveWikiSyntax,
  WikiChangePage,
  WikiCreateRequest,
  WikiDefinition,
  WikiGraph,
  WikiHistoryPage,
  WikiImportResult,
  WikiInfo,
  WikiLinkText,
  WikiLinkTextRequest,
  WikiLintReport,
  WikiMoveRequest,
  WikiMoveResult,
  WikiPageList,
  WikiPagePreview,
  WikiPageTemplateInfo,
  WikiPageView,
  WikiPageWrite,
  WikiRestoreRequest,
  WikiRulesCheckRequest,
  WikiRulesCheckResult,
  WikiRulesDefinition,
  WikiRulesListItem,
  WikiRulesView,
  WikiScanResult,
  WikiSearchResult,
  WikiSummary,
  WikiTemplateRender,
  WikiTemplateRenderRequest,
  WikiView,
} from "@agent-console/contracts/wiki";
import { enc, encodePath, ifMatch, query, withHeaders, type BlobResponse, type RestIo, type Versioned } from "../io";

/** 최근 변경 질의. `op`는 쉼표로 이어 보낸다(열린 문자열). */
export interface ListWikiChangesParams {
  /** 실행 id 또는 루트 실행 id */
  authorRun?: string;
  /** 동작 거르기(여러 개 = 또는) */
  op?: readonly string[];
  limit?: number;
  cursor?: string;
}

export interface ListWikiPagesParams {
  /** 이 경로 접두어(폴더) 아래만 */
  prefix?: string;
  tag?: string;
}

export interface SearchWikiParams {
  q: string;
  prefix?: string;
  /** 여러 개 = 모두 붙은 페이지 */
  tags?: readonly string[];
  limit?: number;
}

export interface WikiGraphParams {
  /** 없으면 전체 */
  center?: string;
  depth?: number;
  limit?: number;
}

/** 가져오기 겹침 처리. 값 목록은 서버 계약(`skip`·`overwrite`·`rename`)이며 화면 라벨은 앱이 정한다. */
export type WikiImportPolicy = string;

export interface WikiImportOptions {
  policy?: WikiImportPolicy;
  dryRun?: boolean;
}

/** 쓰기 옵션. */
export interface WikiWriteOptions {
  /** `If-Match`: 읽을 때 받은 본문 해시 */
  expectedHash?: string;
  /** `If-None-Match: *`: 이미 있으면 거부 */
  createOnly?: boolean;
}

/** 위키 규칙 본문 파일 읽기 결과. `version_hash` = 규칙 정의 버전(`ETag`, 다음 쓰기의 `If-Match`). 텍스트가 아니면 `text`가 null. */
export interface WikiRulesFileContent {
  text: string | null;
  contentType: string;
  size: number;
  version_hash: string | undefined;
}

export interface WikiClient {
  /** 화면 정보: 페이지 폴더(`pages_root`)·능력(`capabilities`)·한도(`limits`). */
  getWikiInfo(): Promise<WikiInfo>;
  /** 공간의 모든 위키를 가로지르는 최근 변경(실행 상세 "고친 위키 페이지"). */
  listSpaceWikiChanges(params?: ListWikiChangesParams): Promise<WikiChangePage>;

  listWikis(): Promise<WikiSummary[]>;
  /** 만들기(정의만). 201 + `ETag`(정의 버전). 같은 id가 있으면 409. */
  createWiki(body: WikiCreateRequest): Promise<Versioned<WikiView>>;
  getWiki(wiki: string): Promise<Versioned<WikiView>>;
  /** 정의 저장. `If-Match` 필수. */
  putWiki(wiki: string, body: WikiDefinition, versionHash: string): Promise<Versioned<WikiView>>;
  /** 정의만 지운다(페이지 폴더는 남는다). */
  deleteWiki(wiki: string, versionHash?: string): Promise<void>;

  listWikiPages(wiki: string, params?: ListWikiPagesParams): Promise<WikiPageList>;
  /** 페이지 보기. `version_hash` = 본문 해시. 없으면 404 `wiki.page_not_found`(`details.has_history`). */
  getWikiPage(wiki: string, path: string): Promise<Versioned<WikiPageView>>;
  /** 쓰기. 새 페이지면 201. 거부는 422 `wiki.rule_rejected`·`wiki.secret_rejected`·`wiki.too_large`. */
  putWikiPage(wiki: string, path: string, body: WikiPageWrite, options?: WikiWriteOptions): Promise<Versioned<WikiPageView>>;
  /** 지우기(`If-Match` 선택). */
  deleteWikiPage(wiki: string, path: string, expectedHash?: string): Promise<void>;
  /** 저장 전 시험(쓰지 않고 기록·색인·알림을 건드리지 않는다). */
  previewWikiPage(wiki: string, path: string, content: string, signal?: AbortSignal): Promise<WikiPagePreview>;
  /** 이름 바꾸기·옮기기. `dry_run`이면 미리보기. */
  moveWikiPage(wiki: string, path: string, body: WikiMoveRequest, signal?: AbortSignal): Promise<WikiMoveResult>;

  /** 기록 목록(최근 것부터). 기록 저장소가 없으면 409 `wiki.history_unavailable`. */
  getWikiPageHistory(wiki: string, path: string, limit?: number): Promise<WikiHistoryPage>;
  /** 그 버전 본문(글). `version_hash` = 그 버전 해시. 지워진 버전은 404 `wiki.version_not_found`. */
  getWikiPageVersion(wiki: string, path: string, version: number): Promise<Versioned<string>>;
  /** 그 버전 본문으로 새 버전(`restore`). 없는 경로면 만든다. */
  restoreWikiPage(wiki: string, path: string, body: WikiRestoreRequest): Promise<Versioned<WikiPageView>>;

  /** 링크 넣기 글자(문법 데이터의 삽입 틀). 틀이 없으면 422 `wiki.link_insert_unavailable`. */
  getWikiLinkText(wiki: string, body: WikiLinkTextRequest): Promise<WikiLinkText>;
  listWikiTemplates(wiki: string): Promise<WikiPageTemplateInfo[]>;
  /** 페이지 틀 채우기(쓰지 않음). */
  renderWikiTemplate(wiki: string, templateId: string, body: WikiTemplateRenderRequest): Promise<WikiTemplateRender>;

  searchWiki(wiki: string, params: SearchWikiParams, signal?: AbortSignal): Promise<WikiSearchResult>;
  getWikiGraph(wiki: string, params?: WikiGraphParams): Promise<WikiGraph>;
  getWikiLint(wiki: string): Promise<WikiLintReport>;
  listWikiChanges(wiki: string, params?: ListWikiChangesParams): Promise<WikiChangePage>;
  getWikiSyntax(wiki: string): Promise<EffectiveWikiSyntax>;
  /** 외부 변경 다시 읽기(기록에 `external`) + 검색 색인 맞추기. */
  scanWiki(wiki: string): Promise<WikiScanResult>;

  /** 페이지 파일 zip(`filename`은 서버가 준 `<위키 id>.zip`). */
  exportWiki(wiki: string): Promise<BlobResponse>;
  /** zip 가져오기(본문 = zip 바이트). `dryRun`이면 쓰지 않는다. */
  importWiki(wiki: string, zip: Uint8Array, options?: WikiImportOptions): Promise<WikiImportResult>;

  listWikiRules(): Promise<WikiRulesListItem[]>;
  getWikiRules(id: string): Promise<Versioned<WikiRulesView>>;
  createWikiRules(body: Record<string, unknown>): Promise<Versioned<WikiRulesView>>;
  putWikiRules(id: string, body: WikiRulesDefinition, versionHash: string): Promise<Versioned<WikiRulesView>>;
  deleteWikiRules(id: string, versionHash?: string): Promise<void>;
  checkWikiRules(body: WikiRulesCheckRequest): Promise<WikiRulesCheckResult>;
  /** 규칙 본문 폴더의 파일 목록(지침·페이지 틀, 경로 순). */
  listWikiRulesFiles(id: string): Promise<ResourceFile[]>;
  readWikiRulesFile(id: string, path: string): Promise<WikiRulesFileContent>;
  /** 규칙 본문 파일 쓰기. `versionHash` = 규칙 정의 버전(`If-Match`). 응답 `version_hash`가 다음 쓰기의 `If-Match`다. 비밀 의심은 `issues`(`X-Console-Issues`). */
  putWikiRulesFile(id: string, path: string, content: string | Uint8Array, versionHash: string, mediaType?: string): Promise<Versioned<WikiRulesView>>;
  deleteWikiRulesFile(id: string, path: string, versionHash: string): Promise<Versioned<WikiRulesView>>;
}

const ZIP_TYPE = "application/zip";

/** 최근 변경 질의 문자열(`op`는 쉼표 목록). */
function changesQuery(params: ListWikiChangesParams | undefined): string {
  if (params === undefined) return "";
  const op = params.op === undefined || params.op.length === 0 ? undefined : params.op.join(",");
  return query({ author_run: params.authorRun, op, limit: params.limit, cursor: params.cursor });
}

export function createWikiClient(io: RestIo): WikiClient {
  const wikiPath = (wiki: string) => `/wiki/wikis/${enc(wiki)}`;
  const pagePath = (wiki: string, path: string) => `${wikiPath(wiki)}/pages/${encodePath(path)}`;
  return {
    getWikiInfo: () => io.request("GET", "/wiki/info"),
    listSpaceWikiChanges: (params) => io.request("GET", `/wiki/changes${changesQuery(params)}`),

    listWikis: () => io.request("GET", "/wiki/wikis"),
    createWiki: (body) => io.requestVersioned("POST", "/wiki/wikis", { body }),
    getWiki: (wiki) => io.requestVersioned("GET", wikiPath(wiki)),
    putWiki: (wiki, body, hash) => io.requestVersioned("PUT", wikiPath(wiki), { body, ...withHeaders(ifMatch(hash)) }),
    deleteWiki: (wiki, hash) => io.request("DELETE", wikiPath(wiki), withHeaders(ifMatch(hash))),

    listWikiPages: (wiki, params) => io.request("GET", `${wikiPath(wiki)}/pages${query({ prefix: params?.prefix, tag: params?.tag })}`),
    getWikiPage: (wiki, path) => io.requestVersioned("GET", pagePath(wiki, path)),
    putWikiPage: (wiki, path, body, options = {}) =>
      io.requestVersioned("PUT", pagePath(wiki, path), {
        body,
        ...withHeaders(options.createOnly === true ? { "If-None-Match": "*" } : ifMatch(options.expectedHash)),
      }),
    deleteWikiPage: (wiki, path, hash) => io.request("DELETE", pagePath(wiki, path), withHeaders(ifMatch(hash))),
    previewWikiPage: (wiki, path, content, signal) => io.request("POST", `${pagePath(wiki, path)}/preview`, { body: { content }, ...(signal === undefined ? {} : { signal }) }),
    moveWikiPage: (wiki, path, body, signal) => io.request("POST", `${pagePath(wiki, path)}/move`, { body, ...(signal === undefined ? {} : { signal }) }),

    getWikiPageHistory: (wiki, path, limit) => io.request("GET", `${pagePath(wiki, path)}/history${query({ limit })}`),
    getWikiPageVersion: (wiki, path, version) => io.requestText("GET", `${pagePath(wiki, path)}/history/${version}`),
    restoreWikiPage: (wiki, path, body) => io.requestVersioned("POST", `${pagePath(wiki, path)}/restore`, { body }),

    getWikiLinkText: (wiki, body) => io.request("POST", `${wikiPath(wiki)}/link-text`, { body }),
    listWikiTemplates: (wiki) => io.request("GET", `${wikiPath(wiki)}/templates`),
    renderWikiTemplate: (wiki, templateId, body) => io.request("POST", `${wikiPath(wiki)}/templates/${enc(templateId)}/render`, { body }),

    searchWiki: (wiki, params, signal) =>
      io.request("GET", `${wikiPath(wiki)}/search${query({ q: params.q, prefix: params.prefix, tag: params.tags, limit: params.limit })}`, signal === undefined ? {} : { signal }),
    getWikiGraph: (wiki, params) => io.request("GET", `${wikiPath(wiki)}/graph${query({ center: params?.center, depth: params?.depth, limit: params?.limit })}`),
    getWikiLint: (wiki) => io.request("GET", `${wikiPath(wiki)}/lint`),
    listWikiChanges: (wiki, params) => io.request("GET", `${wikiPath(wiki)}/changes${changesQuery(params)}`),
    getWikiSyntax: (wiki) => io.request("GET", `${wikiPath(wiki)}/syntax`),
    scanWiki: (wiki) => io.request("POST", `${wikiPath(wiki)}/scan`),

    exportWiki: (wiki) => io.requestBlob("POST", `${wikiPath(wiki)}/export`),
    importWiki: async (wiki, zip, options = {}) => {
      const q = query({ policy: options.policy, dry_run: options.dryRun === true ? true : undefined });
      const r = await io.requestVersioned<WikiImportResult>("POST", `${wikiPath(wiki)}/import${q}`, { bytes: zip, headers: { "Content-Type": ZIP_TYPE } });
      return r.value;
    },

    listWikiRules: () => io.request("GET", "/wiki/rules"),
    getWikiRules: (id) => io.requestVersioned("GET", `/wiki/rules/${enc(id)}`),
    createWikiRules: (body) => io.requestVersioned("POST", "/wiki/rules", { body }),
    putWikiRules: (id, body, hash) => io.requestVersioned("PUT", `/wiki/rules/${enc(id)}`, { body, ...withHeaders(ifMatch(hash)) }),
    deleteWikiRules: (id, hash) => io.request("DELETE", `/wiki/rules/${enc(id)}`, withHeaders(ifMatch(hash))),
    checkWikiRules: (body) => io.request("POST", "/wiki/rules/check", { body }),
    listWikiRulesFiles: (id) => io.request("GET", `/wiki/rules/${enc(id)}/files`),
    readWikiRulesFile: async (id, path) => {
      const r = await io.requestBlob("GET", `/wiki/rules/${enc(id)}/files/${encodePath(path)}`, { headers: { Accept: "text/plain, application/octet-stream, */*" } });
      const isText = r.contentType.toLowerCase().startsWith("text/");
      return { text: isText ? await r.blob.text() : null, contentType: r.contentType, size: r.blob.size, version_hash: r.etag };
    },
    putWikiRulesFile: (id, path, content, hash, mediaType) =>
      io.requestVersioned("PUT", `/wiki/rules/${enc(id)}/files/${encodePath(path)}`, {
        ...(typeof content === "string" ? { text: content } : { bytes: content }),
        headers: { "If-Match": hash, "Content-Type": mediaType ?? (typeof content === "string" ? "text/plain; charset=utf-8" : "application/octet-stream") },
      }),
    deleteWikiRulesFile: (id, path, hash) => io.requestVersioned("DELETE", `/wiki/rules/${enc(id)}/files/${encodePath(path)}`, { headers: { "If-Match": hash } }),
  };
}
