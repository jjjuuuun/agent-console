/** 프리셋 REST. */
import type { ApplyPresetRequest, ApplyPresetResult, PresetSummary } from "@agent-console/contracts";
import { enc, type RestIo } from "../io";

export interface PresetsClient {
  listPresets(): Promise<PresetSummary[]>;
  applyPreset(id: string, request?: ApplyPresetRequest): Promise<ApplyPresetResult>;
}

export function createPresetsClient(io: RestIo): PresetsClient {
  return {
    listPresets: () => io.request("GET", "/presets"),
    applyPreset: (id, req) => io.request("POST", `/presets/${enc(id)}/apply`, { body: req ?? {} }),
  };
}
