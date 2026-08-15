Environment variables for Hermes integration

Create a .env from .env.example and fill in secrets. Do NOT commit .env to source control.

Variables:
- HERMES_PROVIDER: "local" or "openrouter/free" (controls which provider is initialized)
- HERMES_MODEL: model identifier used when calling the provider
- HERMES_TEMPERATURE: float
- HERMES_TIMEOUT: seconds
- HERMES_SANDBOX_PATH: path to store sandbox data

Local Hermes-specific:
- LOCAL_HERMES_URL: http://localhost:8088 (example)
- LOCAL_HERMES_API_KEY: optional API key for local Hermes

OpenRouter-specific:
- OPENROUTER_API_KEY: your OpenRouter key (keep secret)
- OPENROUTER_URL: override OpenRouter endpoint if needed
- OPENROUTER_HTTP_REFERER, OPENROUTER_X_TITLE: optional headers

Usage:
- Copy .env.example -> .env and set values
- Run Hermes via python -m hermes.main or as your project starts
