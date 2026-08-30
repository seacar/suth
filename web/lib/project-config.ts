import type { SuthConfigRecord } from "@/lib/types";
import { credentialRefForProvider, providerDefinition, resolveProviderId } from "@/lib/llm-providers";

export const DEFAULT_DEV_MODEL = "default";
export const DEFAULT_LLM_MODEL = "gemma4";

export function defaultSuthConfig(projectId: string, baseUrl: string): SuthConfigRecord {
  return {
    project_id: projectId,
    base_url: baseUrl.replace(/\/$/, ""),
    default_personas: [],
    environments: {
      dev: {
        headed: true,
        model: DEFAULT_DEV_MODEL,
        max_steps: 20,
      },
    },
    llm_providers: {
      [DEFAULT_DEV_MODEL]: {
        provider: "ollama",
        model: DEFAULT_LLM_MODEL,
        base_url: "http://localhost:11434",
      },
    },
  };
}

export function devEnvironment(config: SuthConfigRecord) {
  return config.environments.dev ?? { model: DEFAULT_DEV_MODEL, headed: true, max_steps: 20 };
}

export function devProvider(config: SuthConfigRecord) {
  const modelKey = devEnvironment(config).model ?? DEFAULT_DEV_MODEL;
  return config.llm_providers[modelKey] ?? { provider: "ollama", model: DEFAULT_LLM_MODEL, base_url: "http://localhost:11434" };
}

export function applyDevSettings(
  config: SuthConfigRecord,
  settings: {
    baseUrl: string;
    headed: boolean;
    maxSteps: number;
    provider: string;
    llmModel: string;
    llmBaseUrl: string;
    defaultPersonas: string[];
  }
): SuthConfigRecord {
  const modelKey = devEnvironment(config).model ?? DEFAULT_DEV_MODEL;
  const providerId = resolveProviderId(settings.provider);
  const providerDef = providerDefinition(providerId);
  const credential = credentialRefForProvider(settings.provider);
  const baseUrl =
    providerId === "ollama"
      ? settings.llmBaseUrl
      : providerId === "custom"
        ? settings.llmBaseUrl || null
        : providerDef?.defaultBaseUrl ?? null;

  return {
    ...config,
    base_url: settings.baseUrl.replace(/\/$/, ""),
    default_personas: settings.defaultPersonas,
    environments: {
      ...config.environments,
      dev: {
        ...config.environments.dev,
        headed: settings.headed,
        headless: settings.headed ? false : true,
        model: modelKey,
        max_steps: settings.maxSteps,
      },
    },
    llm_providers: {
      ...config.llm_providers,
      [modelKey]: {
        ...config.llm_providers[modelKey],
        provider: settings.provider,
        model: settings.llmModel,
        base_url: baseUrl,
        credential,
      },
    },
  };
}

export function projectIdFromPath(path: string): string {
  const trimmed = path.replace(/^\.\//, "").replace(/\/$/, "");
  const segment = trimmed.split("/").pop() ?? "project";
  return segment
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/^(\d)/, "p-$1");
}
