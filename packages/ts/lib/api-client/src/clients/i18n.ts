/** 화면 문구 묶음 REST(`mod-i18n`): 언어 목록과 언어별 묶음. 서버에 이 기능이 없으면 404다. */
import type { I18nInfo, MessageCatalog } from "@agent-console/contracts/i18n";
import { ApiError } from "../errors";
import { enc, type RestIo } from "../io";

export interface I18nClient {
  /** `GET /i18n`: 서버가 줄 수 있는 언어와 언어 해석 기본값. */
  getI18nInfo(opts?: { signal?: AbortSignal }): Promise<I18nInfo>;
  /**
   * `GET /i18n/{lang}`: 한 언어의 서버 문구 묶음. 서버에 그 언어 묶음이 없으면(404 `i18n.unknown_language`)
   * 오류 대신 `null`을 돌려준다(앱 묶음만으로 쓰면 된다). 그 밖의 실패는 `ApiError`.
   * @param opts.signal abort되면 요청을 끊는다(`network_error` `ApiError`).
   */
  getI18nCatalog(language: string, opts?: { signal?: AbortSignal }): Promise<MessageCatalog | null>;
}

export function createI18nClient(io: RestIo): I18nClient {
  return {
    getI18nInfo: (opts) => io.request("GET", "/i18n", opts?.signal ? { signal: opts.signal } : {}),
    async getI18nCatalog(language, opts) {
      try {
        return await io.request<MessageCatalog>("GET", `/i18n/${enc(language)}`, opts?.signal ? { signal: opts.signal } : {});
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
  };
}
