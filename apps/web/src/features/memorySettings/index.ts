/** 설정 › 메모리와 리소스 폼 범위 위젯의 공개 API. 설정 화면·앱 조립 층(`links/`)이 이 파일로만 import한다. */
import "@agent-console/memory-view/styles.css";
import "./memorySettings.css";
export { MemorySettingsEditor, type MemorySettingsEditorProps } from "./MemorySettingsEditor";
export { ScopeKindWidget } from "./ScopeKindWidget";
export { WIDGETS as MEMORY_SETTINGS_WIDGETS } from "./memorySettingsConfig";
export { memorySettingsMessages } from "./messages";
