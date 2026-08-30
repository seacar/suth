"use client";

import { useState } from "react";
import { ProjectModal } from "@/components/ProjectModal";
import { ADD_PROJECT_VALUE } from "@/lib/projects";
import { useProject } from "@/lib/project-context";
import type { ProjectRecord } from "@/lib/types";

export function HeaderProjectSelect() {
  const { projects, projectId, setProjectId, registerProject } = useProject();
  const [addOpen, setAddOpen] = useState(false);

  function handleChange(next: string) {
    if (next === ADD_PROJECT_VALUE) {
      setAddOpen(true);
      return;
    }
    setProjectId(next);
  }

  function handleSaved(project: ProjectRecord) {
    registerProject(project);
    setProjectId(project.id);
  }

  return (
    <>
      <div className="topbar-project">
        <label htmlFor="header-project" className="sr-only">
          Project
        </label>
        <select id="header-project" value={projectId} onChange={(e) => handleChange(e.target.value)}>
          <option value="">All projects</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
          <option value={ADD_PROJECT_VALUE}>+ Add project…</option>
        </select>
      </div>

      <ProjectModal open={addOpen} mode="create" onClose={() => setAddOpen(false)} onSaved={handleSaved} />
    </>
  );
}
