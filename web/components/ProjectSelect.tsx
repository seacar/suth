"use client";

import { useState } from "react";
import { ProjectModal } from "@/components/ProjectModal";
import { ADD_PROJECT_VALUE } from "@/lib/projects";
import type { ProjectRecord } from "@/lib/types";

interface ProjectSelectProps {
  id?: string;
  label?: string;
  projects: ProjectRecord[];
  value: string;
  onChange: (projectId: string) => void;
  onProjectSaved: (project: ProjectRecord) => void;
  placeholder?: string;
}

export function ProjectSelect({
  id = "project-select",
  label = "Project",
  projects,
  value,
  onChange,
  onProjectSaved,
  placeholder = "Select a project",
}: ProjectSelectProps) {
  const [addOpen, setAddOpen] = useState(false);

  function handleChange(next: string) {
    if (next === ADD_PROJECT_VALUE) {
      setAddOpen(true);
      return;
    }
    onChange(next);
  }

  function handleSaved(project: ProjectRecord) {
    onProjectSaved(project);
    onChange(project.id);
  }

  return (
    <>
      <div className="field">
        <label htmlFor={id}>{label}</label>
        <select id={id} value={value} onChange={(e) => handleChange(e.target.value)}>
          <option value="">{placeholder}</option>
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
