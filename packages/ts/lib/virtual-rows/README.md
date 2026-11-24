# @agent-console/virtual-rows

가상 스크롤 행 훅(@tanstack/react-virtual 어댑터). 의존: @tanstack/react-virtual(검증된 가상 스크롤, 대안: 직접 구현·react-window).

## 설치
저장소 안에서는 `pnpm install`이 로컬 패키지를 연결한다. 저장소 밖에서는 tarball(`pnpm pack:all` → `dist/npm`)을 설치한다.

```sh
npm install ./agent-console-<이름>-0.1.0.tgz
```

## 최소 사용
```ts readme
import { useRef } from "react";
import { useVirtualRows } from "@agent-console/virtual-rows";

// 목록 컴포넌트 안에서: 스크롤 컨테이너 ref와 행 수·행 높이를 주고, 보이는 행만 그린다.
export function useRows(count: number) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualRows({ count, rowHeight: 32, scrollRef });
  return { scrollRef, items: virtualizer.getVirtualItems(), totalSize: virtualizer.getTotalSize() };
}
```

`items`의 각 항목은 `index`·`start`(px)·`size`(px)를 가진다. 높이는 숫자 또는 행 번호 → 높이 함수이고, 함수가 돌려주는 값이 바뀌면 `measureKey`를 바꿔 알린다. `keepIndex`는 화면 밖이어도 DOM에 남길 행(포커스)이다. 뷰포트 높이를 읽을 수 없으면 `fallbackHeight`(기본 480)로 첫 화면 분량을 그린다. 이 블록은 `test/readme.test.ts`와 같아야 한다.

## 개발·재사용
- `pnpm build` · `pnpm typecheck` · `pnpm lint` · `pnpm test`는 이 폴더 안에서 단독으로 돈다.
- 공개 API는 `exports`에 적힌 경로뿐이다. 다른 패키지는 `src/`·`dist/`를 직접 import하지 않는다.
- 저장소 밖으로 복사해도 되는지는 `pnpm portability --package @agent-console/virtual-rows`로 확인한다.
