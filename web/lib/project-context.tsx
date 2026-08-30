"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useApi } from "@/lib/api-context";
import { parseProjects } from "@/lib/projects";
import type { ProjectRecord } from "@/lib/types";

interface ProjectContextValue {
  projects: ProjectRecord[];
  /** Empty string means all projects. */
  projectId: string;
  setProjectId: (id: string) => void;
  refreshProjects: () => void;
  registerProject: (project: ProjectRecord) => void;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);

export function ProjectProvider({ children }: { children: ReactNode }) {
  const api = useApi();
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [projectId, setProjectId] = useState("");

  const refreshProjects = useCallback(() => {
    api
      .request<unknown>("/projects")
      .then((raw) => setProjects(parseProjects(raw)))
      .catch(() => {});
  }, [api]);

  useEffect(() => {
    refreshProjects();
  }, [refreshProjects]);

  const registerProject = useCallback((project: ProjectRecord) => {
    setProjects((prev) => [...prev.filter((p) => p.id !== project.id), project]);
  }, []);

  return (
    <ProjectContext.Provider
      value={{ projects, projectId, setProjectId, refreshProjects, registerProject }}
    >
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject() {
  const context = useContext(ProjectContext);
  if (!context) {
    throw new Error("useProject must be used within ProjectProvider");
  }
  return context;
}
