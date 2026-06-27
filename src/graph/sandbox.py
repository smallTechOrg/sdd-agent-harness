"""Pandas eval sandbox for `execute_action`.

The agent's single "tool" is eval/exec of a pandas expression the model emits as
text. This module builds the fixed namespace that expression runs in and the safe
`eval_expression` helper that captures the result, any Plotly figure, and any error.

Per `spec/agent.md` -> "## Tools & Tool Calling":
- Namespace: `df` (first DataFrame), `df1`/`df2`/... per dataset (ordered by
  `dataset_ids`), a `<filename_stem>` alias per dataset, plus the libraries
  `pd, np, px, go, plt, sns, scipy, stats, sklearn, sm`, plus `save_dataset`.
- No filesystem/network builtins beyond these are exposed.

Phase 4 scope: `save_dataset` is REAL — it materialises the DataFrame as a
registered DERIVED dataset (CSV + Parquet + a `datasets` row with lineage) via
`graph.derived.register_derived_dataset` (C25). The module-level `save_dataset`
here is a thin best-effort wrapper with no run/parent lineage; `nodes.execute_action`
binds a *run-aware* closure into the per-run namespace that supplies the producing
`run_id` + parent `dataset_ids` + the exact action expression as `derivation_code`.
Chart capture is wired here (C4) and must never crash a run.
"""
from __future__ import annotations

import re
import traceback
from typing import Any

import numpy as np
import pandas as pd

# Heavier optional libs imported lazily-ish at module load so the namespace is
# complete; all are guaranteed present by pyproject.
import plotly.express as px
import plotly.graph_objects as go
import matplotlib

matplotlib.use("Agg")  # headless: never try to open a window in the sandbox
import matplotlib.pyplot as plt  # noqa: E402
import seaborn as sns  # noqa: E402
import scipy  # noqa: E402
from scipy import stats  # noqa: E402
import sklearn  # noqa: E402
import statsmodels.api as sm  # noqa: E402

from graph.derived import register_derived_dataset  # noqa: E402
from observability.events import get_logger  # noqa: E402

logger = get_logger("graph.sandbox")


_IDENTIFIER_RE = re.compile(r"[^0-9a-zA-Z_]")


def _safe_alias(stem: str) -> str | None:
    """Turn a filename stem into a valid python identifier alias, or None."""
    alias = _IDENTIFIER_RE.sub("_", stem).strip("_")
    if not alias or alias[0].isdigit():
        alias = f"_{alias}" if alias else ""
    return alias or None


def _extract_derivation_expr(code: str) -> str:
    """Recover the DataFrame-producing expression from the recorded action.

    The model usually emits the whole call, e.g.
    `save_dataset(df.dropna(), 'cleaned', 'desc')`. For a re-derivable
    `derivation_code` we want the FIRST argument expression (`df.dropna()`), not
    the wrapping `save_dataset(...)` call (which would create another dataset). If
    the code is not a recognisable `save_dataset(...)` call, return it unchanged.
    """
    code = (code or "").strip()
    marker = "save_dataset("
    idx = code.find(marker)
    if idx == -1:
        return code
    start = idx + len(marker)
    depth = 1
    arg_chars: list[str] = []
    in_str: str | None = None
    i = start
    while i < len(code):
        ch = code[i]
        if in_str is not None:
            arg_chars.append(ch)
            if ch == in_str and code[i - 1] != "\\":
                in_str = None
        elif ch in ("'", '"'):
            in_str = ch
            arg_chars.append(ch)
        elif ch in "([{":
            depth += 1
            arg_chars.append(ch)
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                break  # end of save_dataset(...) args
            arg_chars.append(ch)
        elif ch == "," and depth == 1:
            break  # end of the FIRST argument (the df expression)
        else:
            arg_chars.append(ch)
        i += 1
    first_arg = "".join(arg_chars).strip()
    return first_arg or code


def make_save_dataset(
    *,
    run_id: str | None,
    parent_ids: list[str],
    on_registered=None,
):
    """Build a run-aware `save_dataset(df, name, desc)` for a single run.

    The returned callable has the model-visible signature `save_dataset(df, name,
    desc="")` but closes over the producing `run_id` and parent `dataset_ids` and
    captures the current action expression as `derivation_code` (C25). On success
    it registers a real DERIVED dataset, invokes `on_registered(new_id)` (so the
    node can collect created ids), and returns a confirmation string. A disk/db
    failure is CAUGHT and returned as an error string — it never crashes the run.

    `derivation_code` is bound per-action via the mutable `_code` cell so the node
    can set it to the exact expression that produced `df` just before eval.
    """
    state = {"code": ""}

    def _set_code(expr: str) -> None:
        state["code"] = expr or ""

    def save_dataset(df: Any, name: str, desc: str = "") -> str:
        try:
            # Record the df-producing expression (not the whole save_dataset call)
            # so /re-derive can re-run it against current parents (C25).
            derivation_code = _extract_derivation_expr(state["code"])
            new_id = register_derived_dataset(
                df,
                name,
                desc,
                run_id=run_id,
                parent_ids=list(parent_ids or []),
                derivation_code=derivation_code,
            )
            if on_registered is not None:
                try:
                    on_registered(new_id)
                except Exception:  # noqa: BLE001 — collection is best-effort
                    pass
            rows = int(getattr(df, "shape", (0, 0))[0])
            cols = int(getattr(df, "shape", (0, 0))[1])
            return (
                f"save_dataset('{name}'): registered derived dataset {new_id} "
                f"({rows} rows x {cols} cols)."
            )
        except Exception as exc:  # noqa: BLE001 — recorded as a step error
            logger.warning("save_dataset_failed", run_id=run_id, error=str(exc))
            return f"save_dataset('{name}') failed: {type(exc).__name__}: {exc}"

    # Expose the per-action code setter on the callable so the node can update it.
    save_dataset.set_code = _set_code  # type: ignore[attr-defined]
    return save_dataset


def save_dataset(df: Any, name: str, desc: str = "") -> str:
    """Module-level `save_dataset` — the default bound in `build_namespace`.

    This best-effort variant registers a derived dataset WITHOUT run/parent
    lineage (no producing run is known at module scope). `nodes.execute_action`
    overrides it in the per-run namespace with a run-aware closure from
    `make_save_dataset` that supplies lineage + `derivation_code`. A failure is
    caught and returned as an error string so a model call never crashes the run.
    """
    try:
        new_id = register_derived_dataset(
            df, name, desc, run_id=None, parent_ids=[], derivation_code=""
        )
        rows = int(getattr(df, "shape", (0, 0))[0])
        cols = int(getattr(df, "shape", (0, 0))[1])
        return (
            f"save_dataset('{name}'): registered derived dataset {new_id} "
            f"({rows} rows x {cols} cols)."
        )
    except Exception as exc:  # noqa: BLE001 — recorded as a step error
        return f"save_dataset('{name}') failed: {type(exc).__name__}: {exc}"


def build_namespace(
    dataframes: list[pd.DataFrame],
    filenames: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble the eval namespace for a run.

    `dataframes` are ordered by `dataset_ids`. `filenames` (same order, optional)
    provide the `<filename_stem>` aliases.
    """
    ns: dict[str, Any] = {
        "pd": pd,
        "np": np,
        "px": px,
        "go": go,
        "plt": plt,
        "sns": sns,
        "scipy": scipy,
        "stats": stats,
        "sklearn": sklearn,
        "sm": sm,
        "save_dataset": save_dataset,
    }

    filenames = filenames or []
    for idx, frame in enumerate(dataframes):
        # df1 / df2 / ... (1-based) per dataset
        ns[f"df{idx + 1}"] = frame
        # <filename_stem> alias when we have a usable name
        if idx < len(filenames) and filenames[idx]:
            stem = filenames[idx].rsplit(".", 1)[0]
            stem = stem.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            alias = _safe_alias(stem)
            if alias and alias not in ns:
                ns[alias] = frame

    # `df` is the first DataFrame (most questions are single-dataset)
    if dataframes:
        ns["df"] = dataframes[0]

    return ns


def _capture_charts(result: Any) -> list[str]:
    """If the eval result is a Plotly figure (or list of them), serialise to JSON.

    A failed serialisation is swallowed — chart capture must never abort a run.
    """
    charts: list[str] = []
    candidates = result if isinstance(result, (list, tuple)) else [result]
    for item in candidates:
        if isinstance(item, go.Figure):
            try:
                charts.append(item.to_json())
            except Exception:
                pass
    return charts


def _stringify(result: Any) -> str:
    """Convert an arbitrary eval result to a readable string for the transcript."""
    if result is None:
        return "None"
    if isinstance(result, go.Figure):
        return "[Plotly figure captured]"
    try:
        if isinstance(result, (pd.DataFrame, pd.Series)):
            n = len(result)
            # Cap rows before calling to_string() — huge frames would OOM before truncation.
            if isinstance(result, pd.DataFrame) and n > 100:
                text = result.head(100).to_string()
                text += f"\n... [{n - 100} more rows not shown]"
            else:
                text = result.to_string()
            if len(text) > 6000:
                text = text[:6000] + "\n... [truncated]"
            return text
    except Exception:
        pass
    text = str(result)
    if len(text) > 6000:
        text = text[:6000] + "\n... [truncated]"
    return text


def eval_expression(
    expr: str, namespace: dict[str, Any]
) -> tuple[str, list[str], bool, str | None]:
    """Evaluate `expr` in `namespace`, capturing result, charts, error.

    Returns `(result_str, charts_json_list, is_error, error_str)`.

    Tries `eval` first (expressions, the common case); on a `SyntaxError` falls
    back to `exec` (statements, e.g. multi-line assignments) and reports the value
    of a trailing `_` / last expression where possible. Any exception is caught and
    reported — execution errors are recoverable (the graph loops back to plan).
    """
    expr = (expr or "").strip()
    if not expr:
        return "", [], True, "empty expression"

    # When a run-aware `save_dataset` is bound (it carries a `.set_code` hook),
    # tell it the exact expression that is about to produce the df, so a derived
    # dataset records the right `derivation_code` (C25).
    saver = namespace.get("save_dataset")
    set_code = getattr(saver, "set_code", None)
    if callable(set_code):
        try:
            set_code(expr)
        except Exception:  # noqa: BLE001 — best-effort
            pass

    try:
        try:
            result = eval(expr, namespace)  # noqa: S307 — sandboxed, intentional
        except SyntaxError:
            # Statement(s) rather than a single expression: exec, then surface the
            # value of the last bare expression if the model left one on its own line.
            exec(expr, namespace)  # noqa: S102 — sandboxed, intentional
            last = expr.strip().splitlines()[-1].strip()
            try:
                result = eval(last, namespace)  # noqa: S307
            except Exception:
                result = "[executed statements; no return value]"

        charts = _capture_charts(result)
        return _stringify(result), charts, False, None
    except Exception as exc:  # noqa: BLE001 — recoverable, recorded in transcript
        err = f"{type(exc).__name__}: {exc}"
        # One compact traceback line helps the model self-correct.
        tb = traceback.format_exc().strip().splitlines()
        if tb:
            err = f"{err}\n{tb[-1]}"
        return "", [], True, err
