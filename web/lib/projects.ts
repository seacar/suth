import type { ProjectRecord } from "@/lib/types";

export const ADD_PROJECT_VALUE = "__add_project__";

export {
  browseProjects,
  createProject,
  fetchConfigAt,
  fetchProject,
  updateProject,
  type CreateProjectPayload,
  type UpdateProjectPayload,
} from "@/lib/projects-api";

/** Normalize GET /projects payloads — supports both legacy string[] and ProjectRecord[]. */
export function parseProjects(raw: unknown): ProjectRecord[] {
  if (!Array.isArray(raw)) return [];

  const byId = new Map<string, ProjectRecord>();
  for (const item of raw) {
    let record: ProjectRecord | null = null;
    if (typeof item === "string" && item) {
      record = { id: item, name: item, base_url: "" };
    } else if (item && typeof item === "object") {
      const candidate = item as Partial<ProjectRecord>;
      if (typeof candidate.id === "string" && candidate.id) {
        record = {
          id: candidate.id,
          name: candidate.name ?? candidate.id,
          base_url: candidate.base_url ?? "",
          config_path: candidate.config_path,
          config_dir: candidate.config_dir,
        };
      }
    }
    if (record) byId.set(record.id, record);
  }
  return [...byId.values()];
}
