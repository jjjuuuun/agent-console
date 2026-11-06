# @agent-console/wiki-view

위키 표현 컴포넌트와 순수 함수 패키지(React 19). 데이터와 콜백은 전부 props이고 API·저장소를 모른다(`api-client` import 없음).
링크 패턴·머리말 키·규칙 id·동작/종류/심각도 이름은 코드에 없다. 서버가 준 링크 범위·상태와 앱이 준 표시 표(`WikiDisplay`)로 그리고, 표에 없는 값은 원문 + 중립 톤이다.

## 설치
저장소 안에서는 `pnpm install`이 로컬 패키지를 연결한다. 저장소 밖에서는 tarball(`pnpm pack:all` → `dist/npm`)을 설치한다.

```sh
npm install ./agent-console-wiki-view-0.1.0.tgz
```

앱은 `tokens.css`와 `@agent-console/wiki-view/styles.css`를 한 번씩 로드한다(색·간격은 `--ac-*` 토큰만 쓴다).

## 최소 사용
```ts readme
import { linkifySource } from "@agent-console/wiki-view";

const content = "가나 😀 [[다라]] 끝";
// 서버가 준 링크 범위(UTF-16): content.slice(start, end) === "[[다라]]"
const link = { start: 6, end: 12, raw: "[[다라]]", kind: "wikilink", rule_id: "r", label: "다라", status: "ok", resolved: "da" };
const text = linkifySource(content, [link]);
```

`text`는 `"가나 😀 [다라](ac-wiki:6) 끝"`이다. 이 블록은 `test/readme.test.ts`와 같아야 한다.

## 부품
| 부품 | 용도 |
| --- | --- |
| `PageTree` | 페이지 트리(가상 목록, `role="tree"`, 폴더 먼저·한국어 숫자 정렬) |
| `PageView` | 본문 보기. 서버 링크 범위로 `linkifySource` → `MarkdownPreview`(markdown-doc), 상태별 링크 모양 |
| `OutlinksPanel` | 나가는 링크 목록(본문 위치 이동·강조 연동 콜백) |
| `PageHistory` / `HistoryDiff` | 기록 목록(동작·쓴 주체 칩) / 비교(text-editor `TextDiff`) |
| `LinkGraph` / `LinkList` | 링크 그래프(@xyflow/react + elkjs stress, 읽기 전용) / 같은 정보를 글로 |
| `LintTable` | 점검 표(가상 그리드, 거르기·정렬) |
| `SearchResults` | 검색 결과(서버 `marks` 강조) |
| `NewPageForm` / `MovePageForm` | 새 페이지(틀·변수) / 이름 바꾸기(링크 고치기 미리보기) |
| `RuleListEditor` / `SyntaxValueTree` | 쓰는 규칙 순서·빼기·더하기 / 유효 문법 값 트리와 출처 배지 |
| `AuthorChip` / `OpChip` | 쓴 주체 / 기록 동작 칩 |

순수 함수: `linkifySource`·`usableLinks`·`linkMarks`(링크 범위 → 마크다운 링크·편집기 장식), `splitByMarks`, `buildTree`, `graphToFlow`·`createElkGraphLayout`·`nearestNode`·`edgeGeometry`, `authorLabel`·`resolveDisplay`.

## 링크 범위(UTF-16)
`WikiLink.start`/`end`는 UTF-16 코드 유닛 오프셋이다. `content.slice(start, end)`에 그대로 쓰고 코드 포인트로 바꾸지 않는다.
치환은 `start` 내림차순으로 해서 앞쪽 오프셋이 밀리지 않게 한다. 겹치거나 본문 밖인 범위는 버린다. 검색 `marks`도 같은 규칙이다(서로게이트 쌍은 쪼개지 않는다).

## 의존
contracts(타입 + 상수 전용 진입점), `markdown-doc`(미리보기·칩·출처 배지), `text-editor`(비교), @xyflow/react + elkjs(그래프), @tanstack/react-virtual(가상 목록).
`sdd-view`·`api-client`는 import하지 않는다.

## 개발·재사용
- `pnpm build` · `pnpm typecheck` · `pnpm lint` · `pnpm test`는 이 폴더 안에서 단독으로 돈다.
- 공개 API는 `exports`에 적힌 경로뿐이다. 다른 패키지는 `src/`·`dist/`를 직접 import하지 않는다.
- 저장소 밖으로 복사해도 되는지는 `pnpm portability --package @agent-console/wiki-view`로 확인한다.
