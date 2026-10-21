/**
 * 화면 테스트 공용 도구(앱 코드에서 import하지 않는다). 부팅·셸·라우터를 실제 조립 그대로 올리고 가짜 서버 클라이언트를 넣는다.
 * 노드 타입·연결 종류·리소스 종류 이름은 호출하는 테스트가 임의 문자열로 정한다.
 */
import { render } from "@testing-library/react";
import { beforeAll } from "vitest";
import { createMemoryRouter } from "react-router";
import type { ApiClients } from "../app/apiClients";
import { AppRoot } from "../app/AppRoot";
import { createAppQueryClient } from "../app/queries";
import { createSafeStorage } from "../app/storage";
import type { LinkPartDef } from "../modules";
import type { RouteDef } from "../shell/routeConfig";
import { buildAppRoutes, preloadScreens, type PageTable } from "../shell/routes";

// 화면은 처음 열 때 내려받는다(lazyScreen). 느린 파일시스템에서 첫 이동이 테스트 제한 시간을 넘지 않게 미리 불러온다.
beforeAll(preloadScreens, 120_000);

export interface MountOptions {
  /** 라우트 설정 데이터(생략하면 앱 기본) */
  routes?: readonly RouteDef[];
  pages?: PageTable;
  /** 연동 부분 등록 데이터(생략하면 앱 기본) */
  linkParts?: readonly LinkPartDef[];
}

export function mountApp(clients: ApiClients, path: string, options: MountOptions = {}) {
  const router = createMemoryRouter(buildAppRoutes({ platform: "other", ...(options.routes ? { routes: options.routes } : {}), ...(options.pages ? { pages: options.pages } : {}) }), { initialEntries: [path] });
  const view = render(
    <AppRoot
      createClients={async () => clients}
      router={router}
      storage={createSafeStorage(null)}
      queryClient={createAppQueryClient({ retry: false })}
      {...(options.linkParts ? { linkParts: options.linkParts } : {})}
    />,
  );
  return { router, ...view };
}
