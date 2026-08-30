"use client";

import { useState } from "react";
import { ProjectModal } from "@/components/ProjectModal";
import { useApi } from "@/lib/api-context";
import { useProject } from "@/lib/project-context";
import { PageHeader } from "@/components/PageHeader";
import { deleteProject } from "@/lib/projects-api";
import type { ProjectRecord } from "@/lib/types";

export default function ProjectsPage() {
  const api = useApi();
  const { projects, projectId, setProjectId, refreshProjects, registerProject } = useProject();
  const [createOpen, setCreateOpen] = useState(false);
  const [editProjectId, setEditProjectId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function handleSaved(project: ProjectRecord) {
    registerProject(project);
    refreshProjects();
  }

  async function handleDelete(project: ProjectRecord) {
    const confirmed = window.confirm(
      `Delete "${project.name}"?\n\nThis removes the project from the registry and deletes its sessions, batches, budgets, and stored screenshots/videos. The config file on disk is kept.`
    );
    if (!confirmed) return;

    setDeletingId(project.id);
    setError(null);
    try {
      await deleteProject(api, project.id);
      if (projectId === project.id) setProjectId("");
      if (editProjectId === project.id) setEditProjectId(null);
      refreshProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Registry"
        title="Projects"
        description="Register a target app so runs can drive against it. Pick a config folder, edit settings, and save to mcp_projects.json."
        actions={
          <button type="button" className="primary" onClick={() => setCreateOpen(true)}>
            Add project
          </button>
        }
      />

      {error ? <p className="error-text">{error}</p> : null}

      <section className="panel">
        <div className="panel-head">
          <h2>Registered projects</h2>
          <span className="muted">{projects.length}</span>
        </div>
        <div className="panel-body" style={{ paddingTop: "0.5rem" }}>
          {projects.length === 0 ? (
            <div className="empty">
              <strong>No projects yet</strong>
              Add one to choose a config folder and settings.
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Base URL</th>
                    <th>Config</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {projects.map((p) => (
                    <tr key={p.id}>
                      <td className="mono">{p.id}</td>
                      <td>{p.name}</td>
                      <td className="mono">{p.base_url}</td>
                      <td className="mono">{p.config_path ?? "—"}</td>
                      <td>
                        <div className="table-actions">
                          <button type="button" onClick={() => setEditProjectId(p.id)}>
                            Edit
                          </button>
                          <button
                            type="button"
                            className="danger"
                            disabled={deletingId === p.id}
                            onClick={() => handleDelete(p)}
                          >
                            {deletingId === p.id ? "Deleting…" : "Delete"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      <ProjectModal
        open={createOpen}
        mode="create"
        onClose={() => setCreateOpen(false)}
        onSaved={handleSaved}
      />

      <ProjectModal
        open={editProjectId !== null}
        mode="edit"
        projectId={editProjectId ?? undefined}
        onClose={() => setEditProjectId(null)}
        onSaved={handleSaved}
      />
    </>
  );
}
