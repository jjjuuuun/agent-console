/** 설정 › 구조도 섹션의 공개 API. 설정 화면이 이 파일로만 import한다. */
import "./archSettings.css";
export { ArchitectureSettingsEditor, PROFILES_WIDGET, type ArchitectureSettingsEditorProps } from "./ArchitectureSettingsEditor";
export { ProfilesPanel, type ProfilesPanelProps } from "./ProfilesPanel";
export { ProfileEditor, type ProfileEditorProps } from "./ProfileEditor";
export { archSettingsMessages } from "./messages";
export { buildRows, deleteProfile, disableProfile, removeKey, setProfile, type ProfileRow, type ProfilesMap } from "./profileLogic";
