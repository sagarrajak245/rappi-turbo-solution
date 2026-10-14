"""App startup builds the agent service from the configured LLM providers (no network call)."""

from app.main import create_app
from app.modules.agent.service import AgentService


async def test_lifespan_builds_agent_service() -> None:
    app = create_app()
    async with app.router.lifespan_context(app):
        assert isinstance(app.state.agent_service, AgentService)
    assert app.state.agent_service is None
