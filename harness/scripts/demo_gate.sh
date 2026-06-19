#!/usr/bin/env bash
# DEMO gate checks 2-6 (harness/workflows/gates.md). Exit 0 = done. Seeds demo data, boots the server,
# proves /health, a real run, the outcome+trajectory eval, and visible traces.
set -euo pipefail
PORT="${1:-8001}"
GOAL="${2:-Which product category has the highest total sales, and what is that total?}"
BASE="http://localhost:${PORT}"

cd "$(dirname "$0")/../.."                 # repo root (script lives at harness/scripts/)
set -a; [ -f .env ] && . ./.env; set +a    # load APP_LLM_API_KEY from .env into env for the guard + children
: "${APP_LLM_API_KEY:?fund a key for a real run}"

# 1 — seed a demo dataset for the run to query (prints the dataset id)
DSID="$(python -m agent.seed)"
echo "seeded dataset: $DSID"

# 2 — boot the server, ensure we kill it on any exit
python -m agent & SERVER=$!
trap 'kill "$SERVER" 2>/dev/null || true' EXIT

# 3 — wait up to 30s for /health 200
for i in $(seq 1 30); do
  curl -fsS "${BASE}/health" >/dev/null 2>&1 && break
  sleep 1
  [ "$i" = 30 ] && { echo "FAIL: /health never came up"; exit 1; }
done
curl -fsS "${BASE}/health" | grep -q '"ok": *true' || { echo "FAIL: /health not ok"; exit 1; }

# 4 — one real run; require data.status == completed, capture run_id + answer
RESP="$(curl -fsS -X POST "${BASE}/runs" -H 'content-type: application/json' \
        -d "$(jq -n --arg g "$GOAL" --arg d "$DSID" '{goal:$g, dataset_id:$d}')")"
echo "$RESP" | jq -e '.data.status == "completed"' >/dev/null \
  || { echo "FAIL: run did not complete: $RESP"; exit 1; }
RUN_ID="$(echo "$RESP" | jq -r '.data.run_id')"
echo "run: $RUN_ID"
echo "answer: $(echo "$RESP" | jq -r '.data.answer')"

# 5 — outcome + trajectory eval on THAT run (reads the spec's EARS criterion + spans)
python -m agent.gate_eval --run-id "$RUN_ID" --goal "$GOAL" \
  || { echo "FAIL: eval gate (outcome score < threshold or bad trajectory)"; exit 1; }

# 6 — traces present for that run
curl -fsS "${BASE}/traces" | grep -q "$(echo "$GOAL" | head -c 12)" \
  || { echo "FAIL: run not visible at /traces"; exit 1; }

echo "DEMO GATE PASS"
