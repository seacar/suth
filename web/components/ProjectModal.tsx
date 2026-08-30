"use client";

import { useEffect, useState } from "react";
import { FolderBrowser } from "@/components/FolderBrowser";
import { newProjectConfig, ProjectConfigForm, providerCredentialRef, remoteProviderNeedsCredential } from "@/components/ProjectConfigForm";
import { useApi } from "@/lib/api-context";
import { projectIdFromPath } from "@/lib/project-config";
import { createProject, fetchConfigAt, fetchProject, updateProject } from "@/lib/projects-api";
import type { ProjectRecord, SuthConfigRecord } from "@/lib/types";

interface ProjectModalProps {
  open: boolean;
  mode: "create" | "edit";
  projectId?: string;
  onClose: () => void;
  onSaved: (project: ProjectRecord) => void;
}

export function ProjectModal({ open, mode, projectId, onClose, onSaved }: ProjectModalProps) {
  const api = useApi();
  const [configDir, setConfigDir] = useState(".");
  const [configPath, setConfigPath] = useState("");
  const [configExists, setConfigExists] = useState(false);
  const [registryId, setRegistryId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [config, setConfig] = useState<SuthConfigRecord>(() => newProjectConfig("my-app"));
  const [apiKey, setApiKey] = useState("");
  const [configuredCredentials, setConfiguredCredentials] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;

    setError(null);
    setSaving(false);
    setApiKey("");
    setConfiguredCredentials({});

    if (mode === "edit" && projectId) {
      setLoading(true);
      fetchProject(api, projectId)
        .then((detail) => {
          setRegistryId(detail.id);
          setDisplayName(detail.name);
          setConfigDir(detail.config_dir ?? ".");
          setConfigPath(detail.config_path ?? "");
          setConfigExists(true);
          setConfig(detail.config);
          setConfiguredCredentials(detail.provider_credentials_configured ?? {});
        })
        .catch((err) => setError(err instanceof Error ? err.message : String(err)))
        .finally(() => setLoading(false));
      return;
    }

    setConfigDir(".");
    setConfigPath("./suth_config.json");
    setConfigExists(false);
    setRegistryId("");
    setDisplayName("");
    setConfig(newProjectConfig("my-app"));
    setApiKey("");
    setConfiguredCredentials({});
    setLoading(false);
  }, [api, mode, open, projectId]);

  useEffect(() => {
    if (!open || mode === "edit") return;

    let cancelled = false;
    fetchConfigAt(api, configDir)
      .then((preview) => {
        if (cancelled) return;
        setConfigPath(preview.config_path);
        setConfigExists(preview.exists);
        if (preview.exists && preview.config) {
          setConfig(preview.config);
          setRegistryId(preview.config.project_id);
          setDisplayName((current) => current || preview.config!.project_id);
          setConfiguredCredentials(preview.provider_credentials_configured ?? {});
        } else {
          const suggestedId = projectIdFromPath(configDir);
          const next = newProjectConfig(suggestedId || "my-app");
          setConfig(next);
          setRegistryId((current) => current || suggestedId);
          setDisplayName((current) => current || suggestedId);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });

    return () => {
      cancelled = true;
    };
  }, [api, configDir, mode, open]);

  if (!open) return null;

  const credentialRef = providerCredentialRef(config);
  const credentialConfigured = Boolean(credentialRef && configuredCredentials[credentialRef]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const payloadConfig = { ...config, project_id: registryId };
      const credentialRef = providerCredentialRef(payloadConfig);
      const providerCredentials =
        credentialRef && apiKey.trim() ? { [credentialRef]: apiKey.trim() } : undefined;

      if (remoteProviderNeedsCredential(payloadConfig) && !credentialConfigured && !apiKey.trim()) {
        throw new Error("Enter an API key for the selected remote provider.");
      }
      if (remoteProviderNeedsCredential(payloadConfig) && !credentialRef) {
        throw new Error("Enter a provider ID for custom remote APIs.");
      }

      const project =
        mode === "edit" && projectId
          ? await updateProject(api, projectId, {
              name: displayName,
              config: payloadConfig,
              provider_credentials: providerCredentials,
            })
          : await createProject(api, {
              project_id: registryId,
              name: displayName,
              config_dir: configDir,
              config: payloadConfig,
              provider_credentials: providerCredentials,
            });
      onSaved(project);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  const canSave = registryId !== "" && displayName !== "" && config.base_url !== "" && !saving && !loading;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal project-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{mode === "edit" ? "Edit project" : "Add project"}</h3>
          <button type="button" className="ghost" onClick={onClose}>
            Close
          </button>
        </div>

        {loading ? (
          <p className="muted">Loading project…</p>
        ) : (
          <div className="stack">
            {mode === "create" ? (
              <div className="field">
                <span className="field-label">Config folder</span>
                <p className="field-hint">
                  Pick where <span className="mono">suth_config.json</span> should live. Use Choose folder, or paste a path. An existing file will be loaded for editing.
                </p>
                <FolderBrowser path={configDir} onPathChange={setConfigDir} />
              </div>
            ) : (
              <div className="field">
                <span className="field-label">Config path</span>
                <p className="mono field-hint">{configPath || "—"}</p>
              </div>
            )}

            <div className="row stretch">
              <div className="field">
                <label htmlFor="registry-project-id">Registry ID</label>
                <input
                  id="registry-project-id"
                  value={registryId}
                  disabled={mode === "edit"}
                  onChange={(e) => setRegistryId(e.target.value)}
                  placeholder="my-app"
                />
              </div>
              <div className="field">
                <label htmlFor="registry-project-name">Display name</label>
                <input
                  id="registry-project-name"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="My App"
                />
              </div>
            </div>

            <div className="field">
              <span className="field-label">Config settings</span>
              <p className="field-hint">
                {configExists ? "Loaded from disk — edits will be saved back to the config file." : "No config file yet — one will be created on save."}
              </p>
              <ProjectConfigForm
                config={config}
                onChange={setConfig}
                projectIdLocked={mode === "edit"}
                apiKey={apiKey}
                onApiKeyChange={setApiKey}
                credentialConfigured={credentialConfigured}
              />
            </div>

            {error && <p className="error-text">{error}</p>}

            <div className="row">
              <button type="button" className="primary" disabled={!canSave} onClick={save}>
                {saving ? "Saving…" : mode === "edit" ? "Save changes" : "Save project"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
