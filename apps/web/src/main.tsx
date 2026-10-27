import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter } from "react-router";
import "./styles/fonts.css";
import "@agent-console/ui/tokens.css";
import "@agent-console/graph-editor/styles.css";
import "@agent-console/schema-form/styles.css";
import "@agent-console/trace-view/styles.css";
import "@agent-console/chat/styles.css";
import "@agent-console/log-view/styles.css";
import "./styles/app.css";
import { AppRoot, type ClientHooks } from "./app/AppRoot";
import { bootClients } from "./app/boot";
import { appStorage } from "./app/storage";
import { browserInstallEnvironment, createInstallStore } from "./pwa/installPrompt";
import { PwaProvider } from "./pwa/PwaContext";
import { registerServiceWorker } from "./pwa/registerSw";
import { buildAppRoutes } from "./shell/routes";

const root = document.getElementById("root");
if (!root) throw new Error("#root 요소가 없습니다");

const router = createBrowserRouter(buildAppRoutes());
// 서버 주소: /config.json → 빌드 변수 → 같은 출처(개발·미리보기 서버는 /api, /ws를 프록시)
const configUrl = `${import.meta.env.BASE_URL}config.json`;
const envUrl = import.meta.env["VITE_AGENT_CONSOLE_API_URL"] as string | undefined;
const createClients = (hooks: ClientHooks) => bootClients({ origin: window.location.origin, configUrl, envUrl, ...hooks });

// 설치 안내 이벤트는 React가 뜨기 전에 올 수 있어 먼저 붙잡아 둔다. 서비스 워커는 빌드·미리보기에서만 등록한다.
const services = {
  install: createInstallStore(browserInstallEnvironment(), appStorage),
  update: import.meta.env.PROD ? registerServiceWorker() : null,
};

createRoot(root).render(
  <StrictMode>
    <PwaProvider services={services}>
      <AppRoot createClients={createClients} router={router} />
    </PwaProvider>
  </StrictMode>,
);
