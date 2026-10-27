/**
 * 백엔드 구독 로그인·로그아웃(5.2R.84). 세션은 서버 전체에서 하나다.
 * 입력 본문(코드)은 응답·오류에 되돌아오지 않는다. 이 클라이언트도 값을 기억하거나 기록하지 않는다.
 */
import type {
  BackendLoginInput,
  BackendLoginSession,
  BackendLoginStartRequest,
  BackendLogoutResult,
} from "@agent-console/contracts";
import { enc, type RestIo } from "../io";

export interface LoginClient {
  /** 로그인을 시작한다(201). 이미 진행 중이면 409 `backend.login_busy`(details.session_id), 능력 없음은 409 `backend.login_unsupported`. */
  startBackendLogin(backendId: string, request?: BackendLoginStartRequest): Promise<BackendLoginSession>;
  /** 진행 중인 세션. 없으면 null(204). 새로고침·다른 탭에서 이어 붙을 때 쓴다. */
  getCurrentBackendLogin(): Promise<BackendLoginSession | null>;
  /** 세션 조회. 호출이 하트비트를 겸한다(1초 폴링). 끝난 세션은 잠시 뒤 404 `backend.login_session_not_found`. */
  getBackendLogin(sessionId: string): Promise<BackendLoginSession>;
  /** 글자 또는 키 하나를 보낸다(202). 글자는 로그·캐시에 남기지 않는다. */
  sendBackendLoginInput(sessionId: string, input: BackendLoginInput): Promise<void>;
  /** 취소한다. 취소된 세션을 돌려준다. */
  cancelBackendLogin(sessionId: string): Promise<BackendLoginSession>;
  /** 로그아웃(409 `backend.logout_unsupported`·`backend.login_busy`). */
  logoutBackend(backendId: string): Promise<BackendLogoutResult>;
}

export function createLoginClient(io: RestIo): LoginClient {
  return {
    startBackendLogin: (id, request) => io.request("POST", `/backends/${enc(id)}/login`, { body: request ?? {} }),
    getCurrentBackendLogin: async () => (await io.request<BackendLoginSession | undefined>("GET", "/backends/login/current")) ?? null,
    getBackendLogin: (sid) => io.request("GET", `/backends/login/${enc(sid)}`),
    sendBackendLoginInput: async (sid, input) => {
      await io.request("POST", `/backends/login/${enc(sid)}/input`, { body: input });
    },
    cancelBackendLogin: (sid) => io.request("DELETE", `/backends/login/${enc(sid)}`),
    logoutBackend: (id) => io.request("POST", `/backends/${enc(id)}/logout`, { body: {} }),
  };
}
