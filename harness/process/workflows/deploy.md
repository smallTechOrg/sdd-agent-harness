# Workflow: Deploy

`planner → executor → reviewer → deployer → analyser ↺`

The deploy workflow ships a system that has already been built and reviewed. It starts at
the planner — no new requirements, no new code design. Use this when the build is done
and a deployment target needs to be set up or updated.

---

## When to use

- Promoting a reviewed build to a new environment (staging, production)
- Re-deploying after config or infrastructure changes
- First-time production deploy at the end of the build lifecycle

Not for new features or bug fixes — those start at **build** or **fix**.

---

## Stages

### 1. planner — plan the deployment

Defines the deployment steps: target environment, config changes, migration steps,
rollback plan. Records in the session report.

### 2. executor — prepare

Applies any pre-deploy changes: migrations, config updates, build artefacts. Does not
write new feature code.

### 3. reviewer — sign off

Confirms the deployment plan is safe, the build is clean, and the gate tests pass against
the target config. Signs off before the deployer runs.

### 4. deployer — ship

Executes the deployment to the target environment. Records the result (success, URL,
errors) in the session report.

### 5. analyser — confirm

Reads runtime logs from the deployed environment. Confirms the outcome matches the spec.
Flags any post-deploy drift for the fix workflow.
