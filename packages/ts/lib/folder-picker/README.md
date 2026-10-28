# @agent-console/folder-picker

폴더 고르기: [폴더 선택…] 주 버튼(OS 선택 창 또는 앱 안 찾아보기), 선택한 폴더 상자, 접힌 직접 입력, 확인 결과, 찾아보기 패널(가상 목록), 가운데 줄임 경로 표시. 서버(api-client)를 모른다.
`check`·`list`·`createFolder`·`onPickNative`를 콜백 props로 받으므로 어떤 백엔드에도 붙일 수 있다.

## 설치
저장소 안에서는 `pnpm install`이 로컬 패키지를 연결한다. 저장소 밖에서는 tarball(`pnpm pack:all` → `dist/npm`)을 설치한다.

```sh
npm install ./agent-console-folder-picker-0.1.0.tgz
```

peer: `react`·`react-dom` 19. 의존: `@tanstack/react-virtual`(찾아보기 가상 목록, 대안: 직접 윈도잉 — 검증된 라이브러리를 쓴다).
스타일은 `@agent-console/ui`의 `tokens.css`(`--ac-*` 변수)와 이 패키지의 `@agent-console/folder-picker/styles.css`를 앱이 한 번씩 로드한다.

## 최소 사용
```ts readme
import { deriveCheckState, middleEllipsis } from "@agent-console/folder-picker";

const short = middleEllipsis("/home/me/work/payments/services/api", 27);
const state = deriveCheckState("/srv/app", {
  kind: "checked",
  check: { input: "/srv/app", path: "/srv/app", exists: true, is_dir: true, readable: true, writable: true, can_create: false },
});
```

`short`는 `"/home/me/work…/services/api"`, `state.id`는 `"ok"`(제출 가능)다. 이 블록은 `test/readme.test.ts`와 같아야 한다.

화면은 컨테이너 하나로 쓴다.

```tsx
<FolderPicker
  id="add-folder"
  value={path}
  onValueChange={setPath}
  check={(req, signal) => api.checkFolder(req, signal)}   // FolderCheckOutcome을 돌려준다
  list={(req, signal) => api.listFolders(req, signal)}    // FolderListingData
  createFolder={(req, signal) => api.createFolder(req, signal)}
  roots={roots}
  capabilities={caps}                                      // { browse, native_dialog } 또는 null(조회 중)
  onPickNative={(initial, signal) => api.pickFolder({ initial }, signal)}   // FolderPickOutcome
  configDir=".my-config"                                   // 선택: "{dir} 폴더를 만듭니다" 줄·문구
  autoFocus
  onStateChange={(s) => setCanSubmit(s.submittable)}
  onSelectPhaseChange={(p) => setPicking(p === "waiting")}
  onSubmit={submit}
/>
```

- **선택 우선**: 첫 포커스는 [폴더 선택…]이다. `capabilities.native_dialog === true`(또는 아직 모름 = null)이고 `onPickNative`가 있으면 OS 선택 창을, 아니면 같은 버튼이 앱 안 찾아보기 패널을 연다. `browse: false`면 버튼을 막고 직접 입력을 자동으로 연다.
- **선택 흐름**: 대기(`waiting`: [선택 취소]·"창이 안 보이면" 안내, 30초 뒤 [앱 안에서 찾아보기]) → `picked`·`cancelled`·`unavailable`·`busy`·`timeout`·`failed`. `unavailable`·`failed`(reject 포함, 모르는 값)는 패널을 자동으로 열고, `unavailable`이면 이후 같은 버튼이 곧바로 패널을 연다. 대기 중 Esc는 선택을 취소한다(상위 대화상자로 올리지 않는다). `onPickNative`는 `signal`이 abort되면 요청을 끊어야 한다.
- **확인 타이밍**: 선택한 경로(선택 창·찾아보기·붙여넣기·blur·Enter)는 즉시, 접힌 "경로를 직접 입력"에서 타이핑한 값만 300ms 디바운스한다. `onPickNative` 결과에 `check`(또는 충돌까지 담은 `outcome`)가 있으면 다시 요청하지 않는다. 오래된 응답은 버린다.
- `check`는 409(등록됨·겹침)·403(원격 차단)을 `FolderCheckOutcome`의 `taken`·`overlap`·`remote_disabled`로 돌려준다. 그 밖의 실패는 reject하면 "확인하지 못했습니다"가 된다.
- 기존 구성 안내: `FolderCheckData.manifest`(선택 필드)가 있으면 `manifest_found`(info, 이름·개수), `valid: false`면 `manifest_invalid`(warning). 없으면 안내를 그리지 않는다. 쓰기 불가는 `ok_readonly`(`configDir`가 있으면 `{dir}` 문구).
- 경로 다시 지정: `excludeProjectId`(요청에 실림)와 `currentFolder`(같은 경로 판정, 선택 전에 선택 창·찾아보기 시작 위치)를 준다.
- 문구는 `messages`(일부만 덮어쓰기), 색은 토큰이다. 모듈·기능·폴더 이름은 코드에 없다(`configDir`는 앱이 준다).

## 구성
| 이름 | 역할 |
| --- | --- |
| `FolderPicker` | 선택 버튼 + 선택한 폴더 상자 + 상태 줄 + 접힌 직접 입력 + 결과 + 찾아보기를 묶은 컨테이너 |
| `SelectedFolder` / `FolderPickStatusLine` | 선택한 폴더 상자, 선택 흐름 상태 줄(표현 부품) |
| `FolderPathInput` / `FolderCheckResult` / `FolderBrowser` | 표현 부품(각각 단독 사용 가능) |
| `useFolderCheck` | 디바운스·즉시 확인·오래된 응답 버리기 훅 |
| `deriveCheckState` / `browseStartPath` | 확인 결과 → 화면 상태, 찾아보기 시작 위치(순수 함수) |
| `middleEllipsis` / `MiddleEllipsisPath` | 경로 가운데 줄임(순수 함수 + ResizeObserver 부품) |

## 개발·재사용
- `pnpm build` · `pnpm typecheck` · `pnpm lint` · `pnpm test`는 이 폴더 안에서 단독으로 돈다.
- 공개 API는 `exports`에 적힌 경로뿐이다. 다른 패키지는 `src/`·`dist/`를 직접 import하지 않는다.
- 저장소 밖으로 복사해도 되는지는 `pnpm portability --package folder-picker`로 확인한다.
