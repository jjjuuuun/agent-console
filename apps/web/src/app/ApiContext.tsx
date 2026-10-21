import { createContext, useContext, type ReactNode } from "react";
import type { ApiClients } from "./apiClients";

const ApiContext = createContext<ApiClients | null>(null);

/** 서버 클라이언트를 하위 훅에 공급한다. 클라이언트 생성(토큰·주소)은 호출자 책임. */
export function ApiProvider({ clients, children }: { clients: ApiClients; children: ReactNode }) {
  return <ApiContext.Provider value={clients}>{children}</ApiContext.Provider>;
}

export function useApi(): ApiClients {
  const value = useContext(ApiContext);
  if (value === null) throw new Error("ApiProvider 안에서만 사용할 수 있습니다");
  return value;
}
