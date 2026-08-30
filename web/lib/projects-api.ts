import type {
  BrowseResponse,
  ConfigAtResponse,
  ProjectDetail,
  ProjectRecord,
  SuthConfigRecord,
} from "@/lib/types";

type ApiClient = {
  request<T>(path: string, init?: RequestInit): Promise<T>;
};

export interface CreateProjectPayload {
  project_id: string;
  name: string;
  config_dir: string;
  config: SuthConfigRecord;
  provider_credentials?: Record<string, string>;
}

export interface UpdateProjectPayload {
  name?: string;
  config: SuthConfigRecord;
  provider_credentials?: Record<string, string>;
}

export async function browseProjects(api: ApiClient, path = "."): Promise<BrowseResponse> {
  return api.request<BrowseResponse>(`/projects/browse?path=${encodeURIComponent(path)}`);
}

export async function fetchConfigAt(api: ApiClient, dir: string): Promise<ConfigAtResponse> {
  return api.request<ConfigAtResponse>(`/projects/config-at?dir=${encodeURIComponent(dir)}`);
}

export async function fetchProject(api: ApiClient, projectId: string): Promise<ProjectDetail> {
  return api.request<ProjectDetail>(`/projects/${encodeURIComponent(projectId)}`);
}

export async function createProject(api: ApiClient, input: CreateProjectPayload): Promise<ProjectRecord> {
  return api.request<ProjectRecord>("/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function updateProject(
  api: ApiClient,
  projectId: string,
  input: UpdateProjectPayload
): Promise<ProjectRecord> {
  return api.request<ProjectRecord>(`/projects/${encodeURIComponent(projectId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export interface DeleteProjectResult {
  id: string;
  deleted_sessions: number;
}

export async function deleteProject(api: ApiClient, projectId: string): Promise<DeleteProjectResult> {
  return api.request<DeleteProjectResult>(`/projects/${encodeURIComponent(projectId)}`, {
    method: "DELETE",
  });
}
