import { useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { CommandPalette, filterCommandGroups, Icon } from "@agent-console/ui";
import { useApi } from "../app/ApiContext";
import { useLookupMessage, useShellMessages } from "../app/shellMessages";
import { languageChoices, useLanguage } from "../i18n";
import { queryKeys } from "../app/queries";
import { useCommands } from "./commands";
import { buildQuickGroups, QUICK_GROUP_SOURCES, type QuickGroupSource } from "./quickNavGroups";
import type { RouteDef } from "./routeConfig";

const MAX_PER_GROUP = 8;

export interface QuickNavProps {
  open: boolean;
  onClose: () => void;
  routes: readonly RouteDef[];
  recent: readonly { path: string; label: string }[];
  go: (path: string) => void;
  sources?: readonly QuickGroupSource[];
  /** `language`면 언어 목록을 보인다("언어 바꾸기…" 명령이 연다). 기본 `commands` */
  mode?: QuickNavMode;
}

export type QuickNavMode = "commands" | "language";

/**
 * 빠른 이동(Ctrl+K) 컨테이너. 목록은 열려 있는 동안에만 불러오고(이미 받은 캐시는 재사용),
 * 한 그룹이 실패하면 그 그룹만 빠진다. 표시는 `@agent-console/ui`의 `CommandPalette`.
 */
export function QuickNav({ open, onClose, routes, recent, go, sources = QUICK_GROUP_SOURCES, mode = "commands" }: QuickNavProps) {
  const m = useShellMessages();
  const lookup = useLookupMessage();
  const language = useLanguage();
  const { rest } = useApi();
  const commands = useCommands();
  const [query, setQuery] = useState("");
  const visibleSources = useMemo(() => sources.filter((s) => routes.some((r) => r.serves === s.serves)), [sources, routes]);
  const results = useQueries({
    queries: visibleSources.map((s) => ({
      queryKey: queryKeys.list(s.listName, s.listName === "conversations" ? { archived: false } : s.listName === "runs" ? { limit: 20 } : undefined),
      queryFn: () => s.load(rest),
      enabled: open,
    })),
  });

  const groups = useMemo(() => {
    const built = buildQuickGroups({
      routes,
      results: visibleSources.map((source, i) => ({ source, rows: results[i]?.data, loading: results[i]?.isLoading === true })),
      commands,
      recent,
      query,
      go,
      icon: (name) => <Icon name={name} />,
      text: m,
      lookup,
    });
    return filterCommandGroups(built, query, MAX_PER_GROUP);
  }, [routes, visibleSources, results, commands, recent, query, go, m, lookup]);

  // 언어 목록: 자동 + 코드순 언어. 고르면 팔레트가 닫히고 바로 바뀐다(저장 단추 없음).
  const languageGroups = (() => {
    if (mode !== "language" || language === null) return [];
    const items = languageChoices(language.bundled, language.info, language.state.preference).map((c) => ({
      id: `language:${c.code ?? "auto"}`,
      label: c.code === null ? m.palette.language.auto : c.name,
      ...(c.code === null ? {} : { hint: c.code }),
      ...(c.current ? { badge: m.palette.language.current } : c.partial ? { badge: m.palette.language.partial } : {}),
      run: () => language.select(c.code),
    }));
    return filterCommandGroups([{ id: "languages", title: m.palette.language.title, items }], query, items.length);
  })();

  const loading = useMemo(
    () => Object.fromEntries(visibleSources.map((s, i) => [s.id, results[i]?.isLoading === true && open])),
    [visibleSources, results, open],
  );

  return (
    <CommandPalette
      open={open}
      onClose={() => {
        setQuery("");
        onClose();
      }}
      groups={mode === "language" ? languageGroups : groups}
      query={query}
      onQueryChange={setQuery}
      loading={loading}
      messages={
        mode === "language"
          ? { title: m.palette.language.title, inputLabel: m.palette.language.inputLabel, placeholder: m.palette.language.placeholder, empty: m.palette.language.empty, loading: m.palette.loading }
          : { title: m.palette.title, inputLabel: m.palette.inputLabel, placeholder: m.palette.placeholder, empty: m.palette.empty, loading: m.palette.loading }
      }
    />
  );
}
