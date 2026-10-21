# @agent-console/tsconfig

Agent Console TS 패키지가 함께 쓰는 tsconfig. 저장소 밖으로 복사한 패키지도 같은 설정으로 타입검사·빌드한다.

| 파일 | 용도 |
| --- | --- |
| `base.json` | 엄격한 공통 옵션(번들러 해석, `noEmit`) |
| `library.json` | `base.json` + 선언 파일·소스맵. 라이브러리 패키지가 `extends`한다 |

## 설치
저장소 안에서는 `pnpm install`이 연결한다. 저장소 밖에서는 tarball(`pnpm pack:all` → `dist/npm`)을 개발 의존으로 설치한다.

## 최소 사용
패키지의 `tsconfig.json`:

```json
{ "extends": "@agent-console/tsconfig/library.json", "include": ["src"] }
```

코드에서 파일 경로가 필요하면:

```ts readme
import { configPath } from "@agent-console/tsconfig";

const path = configPath("library");
```

## 개발·재사용
- `pnpm lint` · `pnpm test`는 이 폴더 안에서 단독으로 돈다.
- 옵션을 바꾸면 모든 패키지에 영향이 가므로 `CHANGELOG`에 적고, 범위를 깨면 버전을 올린다.
