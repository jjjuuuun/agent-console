# @agent-console/virtual-rows

A virtual-scroll row hook (an adapter over @tanstack/react-virtual). Dependency: @tanstack/react-virtual (proven virtual scrolling; alternatives: a custom implementation, react-window).

## Installation
Inside the repository, `pnpm install` links the local package. Outside the repository, install the tarball (`pnpm pack:all` → `dist/npm`).

```sh
npm install ./agent-console-<name>-0.1.0.tgz
```

## Minimal usage
```ts readme
import { useRef } from "react";
import { useVirtualRows } from "@agent-console/virtual-rows";

// Inside a list component: pass the scroll container ref, the row count, and the row height, then render only the visible rows.
export function useRows(count: number) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualRows({ count, rowHeight: 32, scrollRef });
  return { scrollRef, items: virtualizer.getVirtualItems(), totalSize: virtualizer.getTotalSize() };
}
```

Each entry in `items` has `index`, `start` (px), and `size` (px). The row height is a number or a function from row index to height; when the values the function returns change, change `measureKey` to tell the hook. `keepIndex` is a row that stays in the DOM even when it is off screen (for focus). When the viewport height cannot be read, the hook renders one screenful of rows using `fallbackHeight` (default 480). This block must match `test/readme.test.ts`.

## Development and standalone reuse
- `pnpm build`, `pnpm typecheck`, `pnpm lint`, and `pnpm test` each run on their own inside this folder.
- The public API is only the paths listed in `exports`. Other packages do not import `src/` or `dist/` directly.
- To check that the package still works when copied out of the repository, run `pnpm portability --package @agent-console/virtual-rows`.
