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
  /** Whether the backend has an adapter for it (src/suth/brain/providers/). */
  supported: boolean;
}

export const LLM_PROVIDER_OPTIONS: LlmProviderDefinition[] = [
  {
    id: "ollama",
    label: "Ollama (local)",
    remote: false,
    defaultBaseUrl: "http://localhost:11434",
    credentialEnv: null,
    defaultModel: DEFAULT_LLM_MODEL,
    supported: true,
  },
  {
    id: "anthropic",
    label: "Anthropic",
    remote: true,
    defaultBaseUrl: null,
    credentialEnv: "ANTHROPIC_API_KEY",
    defaultModel: "claude-opus-5-5",
    supported: true,
  },
  {
    id: "openai",
    label: "OpenAI (not yet supported)",
    remote: true,
    defaultBaseUrl: null,
    credentialEnv: "OPENAI_API_KEY",
    defaultModel: "gpt-4o",
    supported: false,
  },
  {
    id: "custom",
    label: "Custom remote API (not yet supported)",
    remote: true,
    defaultBaseUrl: null,
    credentialEnv: null,
    defaultModel: "",
    supported: false,
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
