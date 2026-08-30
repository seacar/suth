"use client";

import { applyDevSettings, defaultSuthConfig, devEnvironment, devProvider } from "@/lib/project-config";
import {
  LLM_PROVIDER_OPTIONS,
  providerDefinition,
  providerIsRemote,
  resolveProviderId,
  type LlmProviderId,
} from "@/lib/llm-providers";
import type { SuthConfigRecord } from "@/lib/types";

interface ProjectConfigFormProps {
  config: SuthConfigRecord;
  onChange: (config: SuthConfigRecord) => void;
  projectIdLocked?: boolean;
  apiKey: string;
  onApiKeyChange: (value: string) => void;
  credentialConfigured?: boolean;
}

export function ProjectConfigForm({
  config,
  onChange,
  projectIdLocked = false,
  apiKey,
  onApiKeyChange,
  credentialConfigured = false,
}: ProjectConfigFormProps) {
  const dev = devEnvironment(config);
  const provider = devProvider(config);
  const providerId = resolveProviderId(provider.provider);
  const remote = providerIsRemote(provider.provider);
  const selectedProvider = providerDefinition(providerId);

  function update(settings: Partial<{
    baseUrl: string;
    headed: boolean;
    maxSteps: number;
    provider: string;
    llmModel: string;
    llmBaseUrl: string;
    defaultPersonas: string[];
  }>) {
    onChange(
      applyDevSettings(config, {
        baseUrl: settings.baseUrl ?? config.base_url,
        headed: settings.headed ?? dev.headed ?? true,
        maxSteps: settings.maxSteps ?? dev.max_steps ?? 20,
        provider: settings.provider ?? provider.provider,
        llmModel: settings.llmModel ?? provider.model,
        llmBaseUrl: settings.llmBaseUrl ?? provider.base_url ?? "",
        defaultPersonas: settings.defaultPersonas ?? config.default_personas,
      })
    );
  }

  function setProviderChoice(nextId: LlmProviderId) {
    const next = providerDefinition(nextId);
    if (!next) return;
    if (nextId !== resolveProviderId(provider.provider)) {
      onApiKeyChange("");
    }
    update({
      provider: nextId === "custom" ? "" : nextId,
      llmModel: next.defaultModel || provider.model,
      llmBaseUrl: next.defaultBaseUrl ?? "",
    });
  }

  return (
    <div className="stack">
      <div className="row stretch">
        <div className="field">
          <label htmlFor="cfg-project-id">Config project ID</label>
          <input
            id="cfg-project-id"
            value={config.project_id}
            disabled={projectIdLocked}
            onChange={(e) => onChange({ ...config, project_id: e.target.value })}
          />
        </div>
        <div className="field">
          <label htmlFor="cfg-base-url">Base URL</label>
          <input id="cfg-base-url" value={config.base_url} onChange={(e) => update({ baseUrl: e.target.value })} />
        </div>
      </div>

      <div className="field">
        <label htmlFor="cfg-personas">Default personas</label>
        <textarea
          id="cfg-personas"
          rows={2}
          value={config.default_personas.join("\n")}
          onChange={(e) =>
            update({ defaultPersonas: e.target.value.split("\n").map((s) => s.trim()).filter(Boolean) })
          }
          placeholder="One persona ID per line"
        />
      </div>

      <div className="field">
        <span className="field-label">LLM provider</span>
        <p className="field-hint">Local Ollama needs no API key. Remote providers store credentials locally in `.suth/credentials.json`.</p>
      </div>

      <div className="row stretch">
        <div className="field">
          <label htmlFor="cfg-provider">Provider</label>
          <select
            id="cfg-provider"
            value={providerId}
            onChange={(e) => setProviderChoice(e.target.value as LlmProviderId)}
          >
            {LLM_PROVIDER_OPTIONS.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="cfg-llm-model">Model</label>
          <input
            id="cfg-llm-model"
            value={provider.model}
            onChange={(e) => update({ llmModel: e.target.value })}
            placeholder={selectedProvider?.defaultModel || "model name"}
          />
        </div>
      </div>

      {providerId === "custom" && (
        <div className="field">
          <label htmlFor="cfg-custom-provider">Provider ID</label>
          <input
            id="cfg-custom-provider"
            value={provider.provider}
            onChange={(e) => update({ provider: e.target.value.trim().toLowerCase() })}
            placeholder="e.g. groq"
          />
          <p className="field-hint">Lowercase identifier used in config and for credential storage.</p>
        </div>
      )}

      {(providerId === "ollama" || providerId === "custom") && (
        <div className="field">
          <label htmlFor="cfg-llm-base-url">{providerId === "ollama" ? "Ollama base URL" : "API base URL"}</label>
          <input
            id="cfg-llm-base-url"
            value={provider.base_url ?? ""}
            onChange={(e) => update({ llmBaseUrl: e.target.value })}
            placeholder={providerId === "ollama" ? "http://localhost:11434" : "https://api.example.com/v1"}
          />
        </div>
      )}

      {remote && (
        <div className="field">
          <label htmlFor="cfg-api-key">API key</label>
          <input
            id="cfg-api-key"
            type="password"
            value={apiKey}
            onChange={(e) => onApiKeyChange(e.target.value)}
            placeholder={credentialConfigured ? "Saved — enter a new key to replace" : "sk-..."}
            autoComplete="off"
          />
          <p className="field-hint">
            {credentialConfigured
              ? "A key is already saved for this provider. Leave blank to keep it."
              : "Required for remote providers. Stored outside suth_config.json."}
          </p>
        </div>
      )}

      <div className="field">
        <span className="field-label">Dev runtime</span>
        <p className="field-hint">Defaults used when running in the dev environment.</p>
      </div>

      <div className="field">
        <label htmlFor="cfg-max-steps">Max steps</label>
        <input
          id="cfg-max-steps"
          type="number"
          min={1}
          max={200}
          value={dev.max_steps ?? 20}
          onChange={(e) => update({ maxSteps: Number(e.target.value) })}
        />
      </div>

      <div className="setting-row">
        <div className="setting-copy">
          <span className="setting-label">Headed browser</span>
          <span className="setting-hint">Show the browser window during dev runs. Turn off for headless.</span>
        </div>
        <label className="switch">
          <input
            type="checkbox"
            checked={dev.headed ?? true}
            onChange={(e) => update({ headed: e.target.checked })}
          />
        </label>
      </div>
    </div>
  );
}

export function newProjectConfig(projectId: string, baseUrl = "http://localhost:3000"): SuthConfigRecord {
  return defaultSuthConfig(projectId, baseUrl);
}

export function providerCredentialRef(config: SuthConfigRecord): string | null {
  return devProvider(config).credential ?? null;
}

export function remoteProviderNeedsCredential(config: SuthConfigRecord): boolean {
  const profile = devProvider(config);
  return providerIsRemote(profile.provider);
}
