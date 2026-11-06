/**
 * @agent-console/wiki-view — 위키 표현 컴포넌트와 순수 함수.
 * 페이지 트리·보기·나가는 링크·기록·비교, 링크 그래프·연결 목록, 점검 표, 검색 결과, 새 페이지/이름 바꾸기/쓰는 규칙 폼, 유효 문법 값 트리, 쓴 주체·동작 칩.
 * 데이터와 콜백은 전부 props이고 API·저장소·api-client를 모른다. 링크 패턴·머리말 키·규칙 id·동작/종류/심각도 이름은 코드에 없다 —
 * 서버가 준 범위·상태와 앱이 준 표시 표(`WikiDisplay`)로 그린다. 표시 표에 없는 값은 원문 + 중립 톤이다.
 */
export { AuthorChip, OpChip } from "./Chips";
export type { AuthorChipProps, OpChipProps } from "./Chips";
export { PageTree, expandAllFolders } from "./PageTree";
export type { PageTreeProps } from "./PageTree";
export { PageView, wikiUrlTransform } from "./PageView";
export type { PageViewHandle, PageViewProps } from "./PageView";
export { OutlinksPanel } from "./OutlinksPanel";
export type { OutlinksPanelProps } from "./OutlinksPanel";
export { PageHistory } from "./PageHistory";
export type { PageHistoryProps } from "./PageHistory";
export { HistoryDiff } from "./HistoryDiff";
export type { HistoryDiffBase, HistoryDiffProps } from "./HistoryDiff";
export { LinkGraph } from "./LinkGraph";
export type { LinkGraphProps } from "./LinkGraph";
export { LinkList } from "./LinkList";
export type { LinkListProps } from "./LinkList";
export { LintTable } from "./LintTable";
export type { LintSortKey, LintTableProps } from "./LintTable";
export { SearchResults, searchOptionId } from "./SearchResults";
export type { SearchResultsHandle, SearchResultsProps } from "./SearchResults";
export { NewPageForm, folderSuggestions, inputVariables } from "./NewPageForm";
export type { NewPageFormProps, NewPageValue } from "./NewPageForm";
export { MovePageForm, moveTotals } from "./MovePageForm";
export type { MovePageFormProps } from "./MovePageForm";
export { RuleListEditor } from "./RuleListEditor";
export type { RuleListChange, RuleListEditorProps, RuleSummary } from "./RuleListEditor";
export { SyntaxValueTree } from "./SyntaxValueTree";
export type { SyntaxValueTreeProps } from "./SyntaxValueTree";
export { VirtualList } from "./VirtualList";
export type { VirtualListHandle, VirtualListProps, VirtualRowContext } from "./VirtualList";

// 순수 함수
export { WIKI_LINK_HREF_PREFIX, defaultLinkHref, escapeLinkText, linkLabel, linkMarks, linkifySource, parseLinkHref, usableLinks } from "./linkify";
export type { LinkifyOptions } from "./linkify";
export { splitByMarks } from "./marks";
export type { TextSegment } from "./marks";
export { allFolders, ancestorFolders, buildTree, pageName } from "./tree";
export type { BuildTreeOptions, TreeRow, TreeTitleMode } from "./tree";
export { GRAPH_DEFAULTS, boundaryPoint, createElkGraphLayout, edgeGeometry, graphToFlow, gridPositions, nearestNode } from "./graph";
export type { ArrowDirection, ElkLike, FlowEdge, FlowNode, GraphEdgeData, GraphFlowOptions, GraphLayoutEngine, GraphLayoutInput, GraphNodeData } from "./graph";
export { authorFacts, authorLabel, resolveDisplay, severityRank } from "./display";
export type { DisplayEntry, ResolvedDisplay, WikiDisplay } from "./display";
export { linkBehavior, statusKey } from "./semantics";
export type { LinkBehavior } from "./semantics";
export { formatAbsolute, formatRelative, lastSegment } from "./format";
export { defaultMessages, formatMessage, resolveMessages } from "./messages";
export type { WikiViewMessageKey, WikiViewMessages } from "./messages";
