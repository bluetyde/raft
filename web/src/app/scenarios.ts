/**
 * The scenarios the app ships with (docs/m5-scenarios-design.md, D1a). Each file is checked against its library
 * by the runtime's validator when it starts (and by a test for every shipped file).
 */

import type { ScenarioFile } from "../runtime/scenario";

const FILES = import.meta.glob("./scenarios/*.json", { eager: true, import: "default" }) as Record<string, ScenarioFile>;

export const SCENARIOS: ScenarioFile[] = Object.values(FILES).sort((a, b) => a.title.localeCompare(b.title) || a.id.localeCompare(b.id));

export function scenariosFor(libraryId: string): ScenarioFile[] {
  return SCENARIOS.filter((s) => s.library === libraryId);
}

export function scenarioById(id: string): ScenarioFile | undefined {
  return SCENARIOS.find((s) => s.id === id);
}
