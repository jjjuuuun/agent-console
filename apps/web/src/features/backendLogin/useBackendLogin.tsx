import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@agent-console/api-client";
import { ERROR_CODES, type BackendDescriptor, type BackendLoginSession, type BackendLogoutResult, type LoginMethodInfo, type ReadinessAction } from "@agent-console/contracts";
import { useApi } from "../../app/ApiContext";
import { describeError } from "../../app/errors";
import { useNow } from "../../app/useNow";
import { LoginBusyDialog, LoginConfirmDialog, LoginSessionDialog, LogoutDialog } from "./LoginDialogs";
import { loginMessages as t } from "./messages";
import { isTerminalPhase } from "./types";

type Flow =
  | { kind: "idle" }
  | { kind: "confirm"; backendId: string; methodId: string | null; starting: boolean; error?: string }
  | { kind: "busy"; backendId: string; methodId: string | null; sessionId: string; working: boolean }
  | { kind: "session"; sessionId: string; backendId: string; methodId: string | null }
  | { kind: "logout"; backendId: string; running: boolean; result: BackendLogoutResult | null; error?: string };

export interface UseBackendLoginOptions {
  backends: readonly BackendDescriptor[];
  /** 로그인·로그아웃이 끝났을 때(성공·실패 모두) 그 백엔드의 상태를 다시 읽는다 */
  onSettled: (backendId: string) => void;
}

export interface BackendLoginController {
  /** 카드의 동작 버튼이 눌렸을 때. 모르는 kind는 무시한다 */
  run: (backendId: string, action: ReadinessAction) => void;
  /** 대화상자들. 화면 아무 곳에 한 번 그린다 */
  dialogs: ReactNode;
}

const sessionKey = (sid: string) => ["backend-login", sid] as const;

function findMethod(backends: readonly BackendDescriptor[], backendId: string, methodId: string | null): LoginMethodInfo | undefined {
  const methods = backends.find((b) => b.id === backendId)?.login_methods ?? [];
  return methods.find((m) => m.id === methodId) ?? (methodId === null ? methods[0] : undefined);
}

/**
 * 로그인·로그아웃 흐름의 데이터 연결(서버 전체에서 세션 하나).
 * 폴링은 세션 대화상자가 열린 동안만 1초 간격(하트비트 겸용). 붙여 넣은 코드는 상태·캐시·로그에 남기지 않는다.
 */
export function useBackendLogin({ backends, onSettled }: UseBackendLoginOptions): BackendLoginController {
  const { rest } = useApi();
  const queryClient = useQueryClient();
  const [flow, setFlow] = useState<Flow>({ kind: "idle" });
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | undefined>(undefined);
  const settledRef = useRef<string | null>(null);
  const onSettledRef = useRef(onSettled);
  useEffect(() => {
    onSettledRef.current = onSettled;
  });
  const nowMs = useNow(flow.kind === "session", 1000);

  // 새로고침·다른 탭에서 시작한 진행 중 세션에 이어 붙는다(없거나 기능이 꺼져 있으면 조용히 넘어감).
  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const current = await rest.getCurrentBackendLogin();
        if (!alive || !current) return;
        queryClient.setQueryData(sessionKey(current.session_id), current);
        setFlow((f) => (f.kind === "idle" ? { kind: "session", sessionId: current.session_id, backendId: current.backend_id, methodId: current.method_id } : f));
      } catch {
        // 로그인 기능이 없는 서버: 버튼도 없으므로 알릴 것이 없다
      }
    })();
    return () => {
      alive = false;
    };
  }, [rest, queryClient]);

  const sessionId = flow.kind === "session" ? flow.sessionId : null;
  const query = useQuery<BackendLoginSession, Error>({
    queryKey: sessionKey(sessionId ?? ""),
    queryFn: () => rest.getBackendLogin(sessionId ?? ""),
    enabled: sessionId !== null,
    gcTime: 0,
    retry: false,
    refetchOnWindowFocus: false,
    refetchInterval: (q) => (q.state.data && isTerminalPhase(q.state.data.phase) ? false : 1000),
  });
  const session = query.data;

  // 끝난 세션을 한 번만 알린다(상태 카드 다시 읽기)
  useEffect(() => {
    if (!session || !isTerminalPhase(session.phase) || settledRef.current === session.session_id) return;
    settledRef.current = session.session_id;
    onSettledRef.current(session.backend_id);
  }, [session]);

  const close = useCallback(() => {
    setSendError(undefined);
    setFlow({ kind: "idle" });
  }, []);

  const start = useCallback(
    async (backendId: string, methodId: string | null) => {
      setFlow({ kind: "confirm", backendId, methodId, starting: true });
      try {
        const created = await rest.startBackendLogin(backendId, methodId === null ? {} : { method_id: methodId });
        queryClient.setQueryData(sessionKey(created.session_id), created);
        setFlow({ kind: "session", sessionId: created.session_id, backendId, methodId });
      } catch (e) {
        if (e instanceof ApiError && e.code === ERROR_CODES.BACKEND_LOGIN_BUSY && typeof e.details["session_id"] === "string") {
          setFlow({ kind: "busy", backendId, methodId, sessionId: e.details["session_id"], working: false });
          return;
        }
        setFlow({ kind: "confirm", backendId, methodId, starting: false, error: describeError(e, t.startFailed).message });
      }
    },
    [rest, queryClient],
  );

  const cancel = useCallback(async () => {
    if (!sessionId) return;
    try {
      const done = await rest.cancelBackendLogin(sessionId);
      queryClient.setQueryData(sessionKey(sessionId), done);
    } catch (e) {
      setSendError(describeError(e, t.lost).message);
    }
  }, [rest, queryClient, sessionId]);

  const sendText = useCallback(
    async (text: string) => {
      if (!sessionId) return;
      setSending(true);
      setSendError(undefined);
      try {
        await rest.sendBackendLoginInput(sessionId, { text });
        await query.refetch();
      } catch (e) {
        setSendError(describeError(e, t.codeSendFailed).message);
      } finally {
        setSending(false);
      }
    },
    [rest, sessionId, query],
  );

  const sendKey = useCallback(
    async (key: string) => {
      if (!sessionId) return;
      setSending(true);
      setSendError(undefined);
      try {
        await rest.sendBackendLoginInput(sessionId, { key });
        await query.refetch();
      } catch (e) {
        setSendError(describeError(e, t.codeSendFailed).message);
      } finally {
        setSending(false);
      }
    },
    [rest, sessionId, query],
  );

  const logout = useCallback(
    async (backendId: string) => {
      setFlow({ kind: "logout", backendId, running: true, result: null });
      try {
        const result = await rest.logoutBackend(backendId);
        setFlow({ kind: "logout", backendId, running: false, result });
        onSettledRef.current(backendId);
      } catch (e) {
        setFlow({ kind: "logout", backendId, running: false, result: null, error: describeError(e, t.logoutFailed).message });
      }
    },
    [rest],
  );

  const run = useCallback((backendId: string, action: ReadinessAction) => {
    if (action.kind === "login") setFlow({ kind: "confirm", backendId, methodId: action.method_id ?? null, starting: false });
    else if (action.kind === "logout") setFlow({ kind: "logout", backendId, running: false, result: null });
  }, []);

  const titleOf = (backendId: string, methodId: string | null) => findMethod(backends, backendId, methodId)?.label || t.titleFallback;

  let dialogs: ReactNode = null;
  if (flow.kind === "confirm") {
    dialogs = (
      <LoginConfirmDialog
        open
        title={titleOf(flow.backendId, flow.methodId)}
        method={findMethod(backends, flow.backendId, flow.methodId)}
        starting={flow.starting}
        error={flow.error}
        onCancel={close}
        onStart={() => void start(flow.backendId, flow.methodId)}
      />
    );
  } else if (flow.kind === "busy") {
    const { backendId, methodId, sessionId: otherId } = flow;
    dialogs = (
      <LoginBusyDialog
        open
        title={titleOf(backendId, methodId)}
        busy={flow.working}
        onClose={close}
        onResume={() => setFlow({ kind: "session", sessionId: otherId, backendId, methodId })}
        onCancelOther={() => {
          setFlow({ ...flow, working: true });
          void rest
            .cancelBackendLogin(otherId)
            .catch(() => undefined)
            .then(() => setFlow({ kind: "confirm", backendId, methodId, starting: false }));
        }}
      />
    );
  } else if (flow.kind === "session") {
    if (session) {
      dialogs = (
        <LoginSessionDialog
          open
          title={titleOf(session.backend_id, session.method_id)}
          session={session}
          nowMs={nowMs}
          sending={sending}
          sendError={sendError}
          method={findMethod(backends, session.backend_id, session.method_id)}
          onSendText={(text) => void sendText(text)}
          onSendKey={(key) => void sendKey(key)}
          onCancel={() => void cancel()}
          onClose={close}
          onRetry={() => void start(flow.backendId, flow.methodId)}
        />
      );
    } else if (query.error) {
      // 끝난 세션이 보관 기간을 넘겨 사라졌거나 서버가 응답하지 않는다
      const flowRef = flow;
      dialogs = (
        <LoginConfirmDialog
          open
          title={titleOf(flowRef.backendId, flowRef.methodId)}
          method={undefined}
          starting={false}
          error={describeError(query.error, t.lost).message}
          onCancel={close}
          onStart={() => void start(flowRef.backendId, flowRef.methodId)}
        />
      );
    }
  } else if (flow.kind === "logout") {
    const id = flow.backendId;
    dialogs = (
      <LogoutDialog
        open
        title={`${backends.find((b) => b.id === id)?.title ?? ""} ${t.logoutTitle}`.trim()}
        running={flow.running}
        result={flow.result}
        error={flow.error}
        onCancel={close}
        onConfirm={() => void logout(id)}
        onClose={close}
      />
    );
  }
  return { run, dialogs };
}
