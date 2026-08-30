export const DEFAULT_DEV_MODEL = "default";
export const DEFAULT_LLM_MODEL = "gemma4";

export type LlmProviderId = "ollama" | "anthropic" | "openai" | "custom";

export interface LlmProviderDefinition {
  id: LlmProviderId;
  label: string;
  remote: boolean;
  defaultBaseUrl: string | null;
  credentialEnv: string | null;
  defaultModel: string;
}

export const LLM_PROVIDER_OPTIONS: LlmProviderDefinition[] = [
  {
    id: "ollama",
    label: "Ollama (local)",
    remote: false,
    defaultBaseUrl: "http://localhost:11434",
    credentialEnv: null,
    defaultModel: DEFAULT_LLM_MODEL,
  },
  {
    id: "anthropic",
    label: "Anthropic",
    remote: true,
    defaultBaseUrl: null,
    credentialEnv: "ANTHROPIC_API_KEY",
    defaultModel: "claude-sonnet-4-20250514",
  },
  {
    id: "openai",
    label: "OpenAI",
    remote: true,
    defaultBaseUrl: null,
    credentialEnv: "OPENAI_API_KEY",
    defaultModel: "gpt-4o",
  },
  {
    id: "custom",
    label: "Custom remote API",
    remote: true,
    defaultBaseUrl: null,
    credentialEnv: null,
    defaultModel: "",
  },
];

export function providerDefinition(provider: string): LlmProviderDefinition | undefined {
  return LLM_PROVIDER_OPTIONS.find((option) => option.id === provider);
}

export function providerIsRemote(provider: string): boolean {
  const known = providerDefinition(provider);
  if (known) return known.remote;
  return provider !== "ollama";
}

export function credentialEnvForProvider(provider: string): string | null {
  const known = providerDefinition(provider);
  if (known?.credentialEnv) return known.credentialEnv;
  if (provider === "ollama") return null;
  const normalized = provider
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return normalized ? `SUTH_${normalized.toUpperCase()}_API_KEY` : null;
}

export function credentialRefForProvider(provider: string): string | null {
  const envVar = credentialEnvForProvider(provider);
  return envVar ? `env:${envVar}` : null;
}

export function resolveProviderId(provider: string): LlmProviderId {
  const known = providerDefinition(provider);
  if (known) return known.id;
  return providerIsRemote(provider) ? "custom" : "ollama";
}
