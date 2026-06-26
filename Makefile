.PHONY: test eval
test:
	uv run pytest
eval:
	uv run python evals/run_evals.py
