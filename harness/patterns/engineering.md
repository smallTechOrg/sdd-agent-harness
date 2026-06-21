# Engineering Principles

Timeless principles that apply to every codebase, regardless of language or framework.
These are constraints on how code is written — not optional style preferences.

---

## Design Principles

### Single Responsibility
Every module, class, and function does one thing. If you need "and" to describe it,
split it. A file that owns two concerns becomes the place where both concerns rot.

### DRY — Don't Repeat Yourself
Every piece of knowledge has one authoritative location. Duplication is not just a style
problem — it means two places that must be kept in sync, and they won't be.

The exception: duplication is better than the wrong abstraction. Three similar lines is
not always a smell; a premature abstraction that forces unrelated code to share a
contract is worse.

### YAGNI — You Aren't Gonna Need It
Build what the spec asks for now. Do not design for hypothetical future requirements.
Unused abstractions, extension points, and config knobs are debt with no corresponding
asset.

### Separation of Concerns
Keep distinct responsibilities in distinct layers. The data model should not know about
the HTTP layer. The agent loop should not know about the DB schema. Mixing concerns
makes testing hard and change expensive.

### Loose Coupling, High Cohesion
Things that change together belong together; things that are used independently should
not depend on each other. A module's public interface should be narrow — expose the
minimum needed for callers to do their job.

### Fail Fast
Detect invalid state as early as possible and stop. Validate all required config and
inputs at startup or at the boundary where they enter the system. A crash at startup is
infinitely better than a silent wrong answer at runtime.

Do not add fallbacks or defaults for impossible states. If it should not happen, let it
crash and surface the bug.

---

## System Design

### Idempotency
Operations that may be retried (external calls, event handlers, job runners) must
produce the same outcome when run more than once. Design these paths to be safe to
replay before assuming they are.

### Retry and Backoff
Transient failures (network blips, rate limits, cold starts) are expected. Retry with
exponential backoff and jitter. Set a hard retry ceiling. Log every retry attempt with
the failure reason.

Never retry on permanent errors (auth failure, bad request, not found) — retrying them
wastes time and obscures the real problem.

### Validate at Boundaries, Trust Internally
Validate all inputs at system boundaries: user input, external API responses, queue
messages, config values. Inside the system, trust that internal contracts hold — do not
re-validate data that has already been validated and typed.

Defensive checks scattered through internal code create noise and mask real bugs.

### Stateless Services
Services should not hold mutable state in memory between requests. State belongs in the
DB, cache, or message queue — not in a module-level variable. Stateless services scale
horizontally and restart cleanly.

### Configuration Over Hardcoding
Any value that could change between environments (URLs, limits, model names, timeouts,
feature flags) goes in config or environment variables. Hardcoded values in source code
are change-resistant and untestable.

### Minimal Surface Area
The public API of a module, service, or agent should be as small as possible. Every
public function is a promise to callers. More surface area means more breakage when
internals change.

---

## Testing

### Test Pyramid
Write tests at the level that gives the most confidence per unit of cost:

```
        ▲  e2e / smoke
       ▲▲▲  integration
      ▲▲▲▲▲  unit
```

Unit tests are fast and numerous. Integration tests confirm contracts between
components. E2e/smoke tests confirm the system works as a whole — keep them few and
focused on the golden path.

### Test Behaviour, Not Implementation
Tests should assert what the system does from the outside, not how it does it. A test
that breaks when you rename a private function is a test that costs more than it earns.

### Same DB as Production
If production uses PostgreSQL, tests use PostgreSQL. A test suite that passes on SQLite
and fails on Postgres is not a passing test suite — it is a false signal. See
[spec/rules/](../../spec/rules/) for the gate rule.

### Every External Call Must Be Stubbable
Design the boundary between your code and external providers (LLMs, APIs, DBs) so that
tests can substitute a stub without patching internals. A thin client behind an
interface makes this cheap.

### Tests Are Documentation
A well-named test describes a contract. `test_agent_retries_on_transient_failure` tells
the next engineer more than any comment. Name tests for the behaviour they assert, not
the code path they exercise.
