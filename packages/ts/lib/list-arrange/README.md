# @agent-console/list-arrange

목록을 묶고(그룹) 정렬하고 폴더로 나누는 순수 함수 모음. React·DOM·저장소에 의존하지 않는다.
묶는 기준(`GroupByDef`)과 정렬(`SortDef`)은 호출자가 데이터로 넘기며, 이 패키지는 필드 이름이나 화면 종류를 모른다.

## 설치
저장소 안에서는 `pnpm install`이 로컬 패키지를 연결한다. 저장소 밖에서는 tarball(`pnpm pack:all` → `dist/npm`)을 설치한다.

```sh
npm install ./agent-console-list-arrange-0.1.0.tgz
```

## 최소 사용
```ts readme
import { byText, folderOf, groupItems, sortItems, withFolder, type GroupByDef } from "@agent-console/list-arrange";

interface Doc { name: string; attributes?: Record<string, unknown> }
const byFolder: GroupByDef<Doc> = { id: "folder", titleKey: "group.folder", tree: true, read: (d) => [folderOf(d.attributes) ?? ""] };
const docs: Doc[] = [{ name: "나", attributes: withFolder({}, "개발/백엔드") }, { name: "가" }];
const groups = groupItems(sortItems(docs, byText((d) => d.name)), byFolder);
const summary = groups.map((g) => `${g.key}:${g.count}`);
```

`summary`는 `["개발:0", "개발/백엔드:1", "\u0000none:1"]`이다(중간 폴더 `개발`은 직접 항목이 없다. 값이 없는 항목은 맨 아래 "없음" 묶음 `NONE_KEY`). 이 블록은 `test/readme.test.ts`와 같아야 한다.

## 공개 API
| 이름 | 용도 |
| --- | --- |
| `groupItems(items, def, options?)` | `GroupByDef`로 묶는다. `multi`(여러 묶음에 보임)·`tree`(`/` 계층)·빈 값("없음" 맨 아래). 평평한 `GroupNode[]` 반환 |
| `visibleGroups(nodes, collapsed)` · `revealGroup` · `groupKeysOf` · `hasNamedGroups` · `uniqueCount` | 접힘 처리·평면 판정·중복 없는 개수 |
| `sortItems(items, sortDef)` · `byText` · `byNumber` · `textCompare` | 안정 정렬, 한국어 기본 로케일 |
| `resolveGroupBy` · `checkUsable` · `usableUnlessAllDistinct` | 기준을 쓸 수 있는지(값이 모두 다르면 불가 등) |
| `resolveSort` · `availableSorts` | 쓸 수 있는 정렬만 |
| `folderOf(attributes)` · `withFolder(attributes, folder)` | 폴더는 `attributes.ui.folder`(문자열, `/` 계층). 다른 속성은 보존 |
| `buildFolderTree` · `flattenFolderTree` | 폴더 경로들로 이름순 트리 |
| `loadViewState`·`saveViewState`·`loadCollapsed`·`saveCollapsed` | 주입한 `KeyValueStorage`(보통 `localStorage`)에 보기·접힘 저장. 실패는 기본값 |

## 개발·재사용
- `pnpm build` · `pnpm typecheck` · `pnpm lint` · `pnpm test`는 이 폴더 안에서 단독으로 돈다.
- 공개 API는 `exports`에 적힌 경로뿐이다. 다른 패키지는 `src/`·`dist/`를 직접 import하지 않는다.
- 저장소 밖으로 복사해도 되는지는 `pnpm portability --package @agent-console/list-arrange`로 확인한다.
- 그리는 쪽은 `@agent-console/ui`의 `ListPane groups`·`GroupHeader`·`ListViewMenu`. 둘은 서로 import하지 않고 앱이 잇는다.
