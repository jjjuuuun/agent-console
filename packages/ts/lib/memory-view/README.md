# @agent-console/memory-view

공유 메모리 표현 컴포넌트. 범위 나무, 항목 표(가상 목록), 본문 편집기, 항목 정보, 버전 목록·비교, 정리 미리보기와
순수 함수(`groupScopes`·`scopeLabel`·`formatAuthor`·`visibleScopes`)를 낸다.
API·저장소·`api-client`·`log-view`·`ui`를 모른다. 데이터와 콜백은 전부 props, 문구는 `messages`다. 화면 명세: `docs/design/screen-memory.md`.

- **범위 종류·범위 이름·도구 이름은 코드에 없다.** 서버가 준 범위 종류 목록(`label`·`id` 틀·`context_fields`)과 범위 요약만으로 그린다.
  프로젝트·팀을 알아보는 것도 종류 이름이 아니라 종류의 `context_fields`와 id 틀로 한다(`visibleScopes`). 이름을 바꿔도 결과가 같다.
- 항목 표는 6열(고정·키·쓴 주체·수정·크기·버전)을 폭이 줄어도 숨기지 않고, 폭 720 이상일 때만 태그 열을 **더한다**.
  10,000행에서도 보이는 행 + 위아래 8행만 그린다.
- 본문 편집기는 text-editor를 그대로 쓰고, IME 조합 중에는 저장(Ctrl+S, 핸들의 `requestSave`)을 미뤘다가 조합이 끝나면 한 번 저장한다.
- 모르는 계약 어휘(`op`·`author.kind`)는 원문을 그대로 보인다.

## 설치
저장소 안에서는 `pnpm install`이 로컬 패키지를 연결한다. 저장소 밖에서는 tarball(`pnpm pack:all` → `dist/npm`)을 설치한다.

```sh
npm install ./agent-console-memory-view-0.1.0.tgz
```

사용하는 앱은 토큰 CSS(`--ac-*` 변수, `@agent-console/ui/tokens.css`)와 이 패키지의 `@agent-console/memory-view/styles.css`를 한 번씩 불러온다.
이 패키지가 쓰는 토큰은 `styles.css`의 `var(--ac-…)` 참조뿐이다. 핀 아이콘은 `--ac-icon-pin`이 있으면 그것을, 없으면 내장 기본 모양을 쓴다.

| 의존 | 왜 | 대안 |
| --- | --- | --- |
| `@agent-console/text-editor` | 본문 편집(`TextEditor`, 조합 상태 API)과 버전 비교(`TextDiff`, 안쪽에서 `@codemirror/merge`). 새 편집 UI를 만들지 않는다 | 편집기 슬롯(`renderEditor`)으로 다른 편집기를 꽂기 |
| `@tanstack/react-virtual` | 항목 표·정리 미리보기의 가상 목록(10,000행) | 직접 만든 윈도잉 |
| `@agent-console/contracts` | `MemoryEntrySummary` 등 타입만 (`import type`) | — |

`@codemirror/merge`는 직접 의존이 아니다(text-editor가 이미 쓰고 있어 `TextDiff`로 받는다). dependency-cruiser(`memory-view-allowed-deps`)가 이 패키지의 사내 의존을 contracts(타입)·text-editor로 제한한다.

## 최소 사용
```ts readme
import { groupScopes, scopeLabel, visibleScopes } from "@agent-console/memory-view";
import { sampleKinds, sampleScopes } from "@agent-console/memory-view/testing";

const kinds = sampleKinds();
const scopes = sampleScopes();
const { visible, hidden } = visibleScopes(scopes, kinds, "P1", ["g1"]);
const tree = groupScopes(kinds, visible);
const label = scopeLabel({ kind: "desk", id: "g1" }, kinds[1], { graph_id: () => ({ status: "named", name: "개발팀" }) });
```

프로젝트 `P1`(팀 구성 `g1`이 보임)을 고르면 `visible`은 4개, `hidden`은 6개(나무 아래 "다른 프로젝트 범위 6개 숨김")이고,
`tree.groups`는 종류를 서버가 준 순서로 묶으며, `label.text`는 `"개발팀"`이다. 이 블록은 `test/readme.test.ts`와 같아야 한다.

그림 컴포넌트:

```tsx
import "@agent-console/memory-view/styles.css";
import { MemoryScopeTree, MemoryEntryTable, MemoryEntryEditor, MemoryEntryMeta, MemoryVersionList, MemoryVersionDiff, RetentionPreview } from "@agent-console/memory-view";

<MemoryScopeTree kinds={kinds} scopes={visible} selected={scope} onSelect={setScope} resolvers={{ graph_id: resolveGraph }} hiddenCount={hidden.length} onShowHidden={showAll} />;
<MemoryEntryTable entries={entries} hasMore={!!cursor} onLoadMore={next} selectedId={id} onSelect={open} query={q} showScope={scope === null} scopeText={label} />;
<MemoryEntryEditor value={body} onChange={setBody} entryKey={entry.key} contentType={entry.content_type} onSave={save} saveState="dirty" maxBytes={limit} handleRef={editorRef} />;
```

## 공개 API
| 이름 | 역할 |
| --- | --- |
| `MemoryScopeTree` | 모든 범위 → 종류 → 범위 나무. 쓸 수 없는 범위(알 수 없는·꺼진 종류) 모음, 숨김 줄, `⋯` 메뉴, 키보드 이동 |
| `MemoryEntryTable` | 항목 표(가상 목록, `role="grid"`). 행 32/52, 6열 고정 + 태그 열 조건부, roving tabindex, 끝 5행 앞 다음 쪽 요청 |
| `MemoryEntryEditor` | text-editor + 상태 줄(줄·열 / 바이트·한도 / 형식 / 저장 상태). 조합 중 저장 보류, 한도 초과 시 저장 막기 |
| `MemoryEntryMeta` | 정보 격자: 범위·버전·크기·해시·만든 이·고친 이·태그 입력·형식·고정·보관 |
| `MemoryVersionList` | 버전 목록(최신순, 동작 칩·쓴 주체·시각·크기 변화) |
| `MemoryVersionDiff` | 직전/현재 비교, 나란히/한 줄, 본문 없는 동작은 글자 설명, [이 버전으로 되돌리기] |
| `RetentionPreview` | 정리 계획 요약 + 가상 표(최대 200행) + [지금 적용]. 호출·확인 창은 앱 |
| `groupScopes(kinds, scopes)` | 종류별로 묶기(서버 순서, 범위는 라벨 순), 항목 합계, `selfScope`, 쓸 수 없는 범위 분리 |
| `scopeLabel(scope, kind, resolvers)` | 범위 라벨. 맥락 필드별 이름 풀기, 삭제됨/알 수 없는 종류 표지 |
| `visibleScopes(scopes, kinds, project, graphs)` | 프로젝트 전환기 거르기(`context_fields`·id 틀로만 판단) |
| `formatAuthor(author, options)` | 쓴 주체 표시(에이전트 아바타·이름, 사용자·정리·가져오기 칩, 모르는 종류는 원문) |
| `validateKey`·`languageForContentType`·`formatBytes`·`formatRelativeTime`·`utf8Bytes` | 키 글자 규칙, 본문 형식 → 편집기 언어, 크기·시각 표기 |
| `defaultMessages`·`resolveMessages` | 한국어 문구 표(`memory.*` 키에서 접두를 뺀 이름) |
| `@agent-console/memory-view/testing` | 표본 데이터(`sampleKinds`·`sampleScopes`·`makeEntries`·`sampleVersions`·`samplePlan`·`renameKinds`) |

## 개발·재사용
- `pnpm build` · `pnpm typecheck` · `pnpm lint` · `pnpm test`는 이 폴더 안에서 단독으로 돈다.
- 공개 API는 `exports`에 적힌 경로뿐이다. 다른 패키지는 `src/`·`dist/`를 직접 import하지 않는다.
- 저장소 밖으로 복사해도 되는지는 `pnpm portability --package @agent-console/memory-view`로 확인한다.
