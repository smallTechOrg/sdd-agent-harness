from collections.abc import Iterator
from dataclasses import dataclass

from google import genai
from google.genai import types


@dataclass(frozen=True)
class Usage:
    """Token usage for a single LLM call.

    prompt_tokens     -> Gemini `usage_metadata.prompt_token_count`
    completion_tokens -> Gemini `usage_metadata.candidates_token_count`
    Missing usage_metadata is handled gracefully as 0s.
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class StreamChunk:
    """One yield from a streaming generation.

    text  -> incremental text delta (may be "" on a usage-only final chunk)
    usage -> the running/final Usage carried by chunks that expose usage_metadata;
             None on chunks that do not. The LAST chunk carrying a non-None usage
             holds the final cumulative token counts for the whole stream.
    """

    text: str
    usage: Usage | None = None


def _extract_usage(response) -> Usage:
    """Read Usage from a Gemini response/chunk; 0s if usage_metadata is absent."""
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return Usage(prompt_tokens=0, completion_tokens=0)
    prompt = getattr(meta, "prompt_token_count", None) or 0
    completion = getattr(meta, "candidates_token_count", None) or 0
    return Usage(prompt_tokens=int(prompt), completion_tokens=int(completion))


class GeminiProvider:
    # DataChat default per spec is gemini-2.0-flash. However, as of build time,
    # gemini-2.0-flash (and -001) are *listed* by ListModels but return
    # 404 "no longer available" on generate_content for this key. We therefore
    # default to gemini-2.5-flash, which generates successfully. See the slice
    # handoff note. Override via AGENT_LLM_MODEL when 2.0-flash is restored.
    DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model or self.DEFAULT_MODEL

    def _config(self, system: str | None):
        return (
            types.GenerateContentConfig(system_instruction=system)
            if system
            else None
        )

    def call_model_with_usage(
        self, prompt: str, *, system: str | None = None
    ) -> tuple[str, Usage]:
        """Generate once, returning (text, Usage)."""
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=self._config(system),
        )
        return response.text or "", _extract_usage(response)

    def call_model(self, prompt: str, *, system: str | None = None) -> str:
        """Base interface — text only, implemented via call_model_with_usage."""
        text, _usage = self.call_model_with_usage(prompt, system=system)
        return text

    def stream_model(
        self, prompt: str, *, system: str | None = None
    ) -> Iterator[StreamChunk]:
        """Stream generation, yielding StreamChunk(text, usage).

        Each StreamChunk carries a text delta. Usage is attached whenever the
        underlying SDK chunk exposes usage_metadata; the last such chunk holds
        the final cumulative token counts. Callers accumulate text and keep the
        most recent non-None `usage` as the call's final usage.
        """
        stream = self._client.models.generate_content_stream(
            model=self._model,
            contents=prompt,
            config=self._config(system),
        )
        for chunk in stream:
            meta = getattr(chunk, "usage_metadata", None)
            usage = _extract_usage(chunk) if meta is not None else None
            yield StreamChunk(text=chunk.text or "", usage=usage)
