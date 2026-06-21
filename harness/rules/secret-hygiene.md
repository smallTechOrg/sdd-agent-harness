# Secret Hygiene

- Never commit secrets — API keys, tokens, passwords, or connection strings with
  credentials. `.env` is git-ignored; `.env.example` lists every variable with
  placeholder values only.
- Read secrets from the environment (or a secrets manager), never hard-coded.
- Never print secrets to `logs/` or to stdout. Redact before logging.
- If a secret is committed by accident: rotate it immediately, then scrub history. Treat
  any exposed secret as compromised.
- Never paste real secrets into the spec, session reports, or PR descriptions.
- API keys/providers are configured flexibly via env (`provider=auto`): the build works
  offline with stubs when no key is set, and uses the real provider when a key is present.
