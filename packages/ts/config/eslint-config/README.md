# @agent-console/eslint-config

Agent Console TS 패키지가 함께 쓰는 ESLint flat config. 저장소 밖으로 복사한 패키지도 같은 규칙으로 린트한다.

## 설치
저장소 안에서는 `pnpm install`이 연결한다. 저장소 밖에서는 tarball(`pnpm pack:all` → `dist/npm`)을 개발 의존으로 설치하고,
peer(`eslint`, `@eslint/js`, `typescript-eslint`, `globals`)를 함께 설치한다. React Hooks 규칙(`/react`)은 `eslint-plugin-react-hooks`도 필요하다.

## 최소 사용
패키지의 `eslint.config.js`:

```js
import config from "@agent-console/eslint-config";

export default config;
```

옵션이 필요하면 `createConfig`를 쓴다.

```ts readme
import { createConfig } from "@agent-console/eslint-config";

const config = createConfig({ ignores: ["**/generated/**"] });
```

React 패키지는 `@agent-console/eslint-config/react`에서 `createReactConfig`를 가져온다.

## 개발·재사용
- `pnpm lint` · `pnpm test`는 이 폴더 안에서 단독으로 돈다.
- 규칙을 바꾸면 모든 패키지에 영향이 가므로 `CHANGELOG`에 적는다.
