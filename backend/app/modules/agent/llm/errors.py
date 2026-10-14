"""Provider-level failures. Internal to the LLM layer: FallbackLlm turns them into LlmUnavailable.

Messages never include API keys or request headers.
"""


class ProviderError(Exception):
    """The provider could not be reached or answered with an HTTP error."""


class InvalidOutput(Exception):
    """The provider answered, but not with JSON matching the requested schema."""
