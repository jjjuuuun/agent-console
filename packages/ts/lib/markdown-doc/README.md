# @agent-console/markdown-doc

마크다운 문서 편집기(`DocumentEditor`: text-editor + 미리보기 + 변경 비교 + 충돌·외부 변경·파일 없음·읽기 전용 띠 + 줄 이동)와
미리보기(`MarkdownPreview`: react-markdown + GFM, 원시 HTML 비허용, 링크·원문 훅), 그리고 스펙·위키 화면이 같이 쓰는 작은 표현 부품
(`ToneChip`·`DocumentStateChip` 상태 칩, `RulesSourceBadge` 값 출처 배지).
데이터와 콜백은 전부 props이고 API·저장소·`api-client`를 모른다. 상태·톤·출처 이름은 코드에 없고 호출자가 준 데이터다.
사내 의존은 `@agent-console/contracts`(타입만)와 `@agent-console/text-editor`뿐이다. react 19는 peer다.

공용 부품 위치(7R.6 결정): 칩·배지는 `ui`가 아니라 여기에 둔다. `ui`는 `sdd-view`가 쓰지 않는 의존이고(sdd-view는 `ui`를 import하지 않는다),
`sdd-view`·`wiki-view`가 둘 다 이미 이 패키지에 의존하므로 새 의존 간선이 생기지 않는다. `sdd-view`는 같은 이름으로 다시 내보낸다.

## 설치
저장소 안에서는 `pnpm install`이 로컬 패키지를 연결한다. 저장소 밖에서는 tarball(`pnpm pack:all` → `dist/npm`)을 설치한다(react 19 필요).
`@agent-console/ui/tokens.css`(디자인 토큰)와 이 패키지의 `styles.css`를 앱이 한 번씩 로드한다.

## 최소 사용
이 블록은 `test/readme.test.ts`와 같고, 테스트가 실제로 실행한다(`pnpm pkg-lint`가 일치를 검사).

```ts readme
import { formatMessage, resolveMessages, statusTone } from "@agent-console/markdown-doc";

const chip = statusTone("s2", [{ id: "s2", label: "검토", tone: "info" }]);
const text = resolveMessages({ "editor.save": "올리기" });
const line = formatMessage(text["editor.issue.line"], { line: 7 });
```

```tsx
import "@agent-console/markdown-doc/styles.css";
import { DocumentEditor, MarkdownPreview } from "@agent-console/markdown-doc";

<DocumentEditor document={doc} value={draft} onChange={setDraft} onSave={save} compare={{ before: saved }} previewHooks={{ renderLink }} />
<MarkdownPreview source={text} transformSource={linkify} renderLink={(href, children) => <a href={href}>{children}</a>} />
```

## 공개 API
| 이름 | 용도 |
| --- | --- |
| `DocumentEditor` | 편집기 + 미리보기. `mode`/`onModeChange`, `compare`·`defaultCompareOpen`, `conflict`·`externalChange`·`missing`·`readOnly`, `issues`(`DocumentIssue`), `initialLine`·`handleRef`(`openGoToLine`·`goToLine`), `toolbarExtra`, `previewHooks` |
| `MarkdownPreview` | `source`, `renderLink(href, children)`, `transformSource(text)`, `urlTransform(url)` |
| `ToneChip` / `DocumentStateChip` | 상태 칩(`data-tone`만 달고 색은 CSS가 정한다) |
| `RulesSourceBadge` | 규칙·문법 값 출처 배지(`source.<값>` 문구 키, 없으면 원문) |
| `toneAttr`·`statusTone`·`NEUTRAL_TONE` | 톤 이름 정리·상태 id → 칩 값 |
| `defaultMessages`·`resolveMessages`·`formatMessage`·`messageOr` | 문구 표(`messages` prop으로 부분 덮어쓰기) |

## 의존성(무엇을 / 왜 / 대안)
- `@agent-console/text-editor` — 편집기·비교(CodeMirror 6). 대안: 직접 CodeMirror 연결.
- `react-markdown` + `remark-gfm` — 미리보기(원시 HTML 비허용). 대안: marked + 직접 정화.

## 개발·재사용
- `pnpm build` · `pnpm typecheck` · `pnpm lint` · `pnpm test`는 이 폴더 안에서 단독으로 돈다.
- 공개 API는 `exports`에 적힌 경로(`.`, `./styles.css`)뿐이다. 다른 패키지는 `src/`·`dist/`를 직접 import하지 않는다.
- 저장소 밖으로 복사해도 되는지는 `pnpm portability --package markdown-doc`로 확인한다.
