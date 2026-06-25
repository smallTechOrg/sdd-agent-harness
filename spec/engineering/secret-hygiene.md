# Rule: Secret Hygiene

**Scope:** everywhere, always. This is the rule most likely to cause real-world harm if violated.

## What is a secret

Anything that authenticates, authorizes, or can be used to impersonate.

For code purposes, treat any field whose name matches `*_token`, `*_secret`,
`*_password`, `*_key`, or `*_credential` as a secret. Also treat database
connection URIs (e.g. `*_uri`, `*_url`, `*_dsn`, `*_conn`) as secret-bearing
when they may embed credentials.

## Where secrets live

| Location | Secrets allowed? |
|---|---|
| `.env` | ✅ Yes (primary store) |
| OS environment variables | ✅ Yes |
| Source code | ❌ Never, including tests |
| Git history | ❌ Never |
| Commit messages, PR descriptions, logs | ❌ Never |

## Rules for code

### Never log a secret

```python
# BAD
log.info("api_call", token=access_token)

# GOOD
log.info("api_call", token_present=bool(access_token))
```

### Never include secrets in exception messages

```python
# BAD
raise ValueError(f"Auth failed with token {token}")

# GOOD
raise ValueError("Auth failed. Check your API key in .env.")
```

### Never `print()` or `repr()` a config object that may contain secrets

Config models use pydantic. Secret fields must use pydantic's `SecretStr` type.
`SecretStr.get_secret_value()` is the only way to extract the raw value, and it
should be called only at the boundary where the secret is actually used.

### Database connection URIs are secret-bearing

External datasets (`data_sources.uri`) carry a full connection URI of the form
`postgresql://user:pass@host:port/db`. The embedded credentials make this URI a
secret. For v0.1 (BETA, behind `DATAANALYSIS_ENABLE_EXTERNAL_DATASETS`, default
off) the URI is stored **plaintext** in `data_sources.uri` — this is an accepted,
documented trade-off for the BETA path, not a precedent for other secrets.

Because the value is plaintext at rest, the credentials MUST never escape that
column:

- **Never log, display, flash, or render the raw `uri`.** Always render via
  `DatasetURI.display()`, which strips username/password (and never emits the raw
  value). Logs, the `connection_error` column, templates, and API responses use
  `display()` only.
- **Never put a raw `uri` in an exception message.** Surface
  `DatasetConnectionError` with a sanitized message.
- **Wrap driver errors.** `psycopg2`'s exception `str()` can echo the full
  conninfo (including the password). Catch driver errors at the connector
  boundary and re-raise a sanitized `DatasetConnectionError` — never propagate the
  original message.
- The raw `uri` is read exactly once, at connect time, inside the connector.

## Rules for `.gitignore`

The repo's `.gitignore` is the enforcement point. If you introduce a new
secret-bearing file location, **add it to `.gitignore` before creating the file**.

## Rules for commits

Before every commit involving new or changed files:

1. Scan the diff for strings that look like tokens (length > 20, mix of alphanumerics, common prefixes like `sk-`, `gsk_`, `ghp_`).
2. If anything matches, **stop**. Do not include in the commit. Rotate the secret if it was real.
3. `git diff --cached` is your friend.

## Rules for AI agents

- **Never read a `.env` file** unless the user explicitly asks.
- **Never echo, print, or paste a secret value** into your response. Confirm by presence only.
- **Never commit a file that contains a secret** even if the user asks. Push back, rotate, continue.

## If a secret leaks

1. Rotate the secret immediately at the provider.
2. Update the relevant `.env` with the new value.
3. Purge from git history if committed: `git filter-repo` or `bfg`. Force-push with operator approval.
4. Note the incident in the commit message without repeating the leaked value.
