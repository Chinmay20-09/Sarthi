Environment variables for Hermes integration

Create a .env from .env.example and fill in secrets. Do NOT commit .env to source control.

Variables:
- HERMES_PROVIDER: which provider Hermes uses. Supported values:
  - "local" | "ollama" — local Ollama only (no cloud calls) — **the
    default when HERMES_PROVIDER is unset**
  - "openrouter" — OpenRouter primary, local Ollama fallback
  - "openai_compatible" | "openai" — any OpenAI-compatible endpoint
    (OPENAI_COMPATIBLE_URL), local Ollama fallback
  Unknown values fall back to the local provider with a logged warning.
  Remote providers are opt-in; they are only ever contacted when
  HERMES_PROVIDER names them.
- HERMES_MODEL: model identifier used when calling the provider
- HERMES_TEMPERATURE: float
- HERMES_TIMEOUT: seconds
- HERMES_SANDBOX_PATH: path to store sandbox data

Local Hermes-specific (provider=local|ollama, and the automatic fallback
for remote providers):
- LOCAL_HERMES_URL: http://localhost:11434 (Ollama's default port; the local
  provider talks to Ollama's /api/chat endpoint)
- LOCAL_HERMES_API_KEY: optional API key for local Hermes
- LOCAL_HERMES_MODEL: model name as installed in Ollama (default: hermes3:8b)
- LOCAL_HERMES_TIMEOUT: seconds before a local generation is considered failed
  (default: 180 — CPU inference is slow)

OpenRouter-specific (provider=openrouter):
- OPENROUTER_API_KEY: your OpenRouter key (keep secret)
- OPENROUTER_URL: override OpenRouter endpoint if needed
- OPENROUTER_HTTP_REFERER, OPENROUTER_X_TITLE: optional headers

OpenAI-compatible (provider=openai_compatible | openai):
- OPENAI_COMPATIBLE_URL: base URL of any /v1-compatible endpoint, e.g.
  https://api.openai.com/v1 (default), http://localhost:1234/v1 (LM Studio)
- OPENAI_COMPATIBLE_API_KEY: key for that endpoint. Empty is fine for
  keyless local servers (no Authorization header is sent).

Usage:
- Copy .env.example -> .env and set values
- Run Hermes via python -m hermes.main or as your project starts

Adding a provider:
- Write one adapter subclassing hermes.providers.base.AIProvider (map
  ModelRequest -> the provider's wire format and the response ->
  ProviderResponse), register it in hermes/providers/registry.py, and set
  HERMES_PROVIDER to its name. No Hermes core, Brain, skill, or API code
  changes. Check GET /hermes/status to see the active provider, model and
  capabilities.
