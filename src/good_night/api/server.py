"""FastAPI server for Good Night."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..config import load_config
from ..daemon.lifecycle import DaemonLifecycle, get_runtime_dir
from ..dreaming.events import AgentEvent, AgentEventStream
from ..storage.resolutions import ResolutionStorage
from ..storage.state import StateManager


class StatusResponse(BaseModel):
    """Response model for status endpoint."""

    daemon_running: bool
    daemon_pid: int | None
    runtime_dir: str
    provider: str
    api_port: int
    last_dream_run: str | None
    total_dream_runs: int
    total_issues_found: int
    total_resolutions: int


class TriggerRequest(BaseModel):
    """Request model for trigger endpoint."""

    connector: str | None = None
    module: str | None = None
    dry_run: bool = False


class TriggerResponse(BaseModel):
    """Response model for trigger endpoint."""

    success: bool
    run_id: str | None = None
    message: str


class ConfigResponse(BaseModel):
    """Response model for config endpoint."""

    daemon: dict[str, Any]
    api: dict[str, Any]
    provider: dict[str, Any]
    enabled: dict[str, Any]
    dreaming: dict[str, Any]


class HistoryItem(BaseModel):
    """Model for a history item."""

    id: str
    created_at: str
    conversations_analyzed: int
    issues_found: int
    resolutions_count: int


class HistoryResponse(BaseModel):
    """Response model for history endpoint."""

    items: list[HistoryItem]


class DreamStatusResponse(BaseModel):
    """Response model for dream status endpoint."""

    running: bool
    run_id: str | None
    active_agents: dict[str, dict[str, Any]]
    recent_events: list[dict[str, Any]]


# Global event stream for sharing across requests
_global_event_stream: AgentEventStream | None = None


def get_event_stream() -> AgentEventStream:
    """Get or create the global event stream."""
    global _global_event_stream
    if _global_event_stream is None:
        _global_event_stream = AgentEventStream()
    return _global_event_stream


def create_app(runtime_dir: Path | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if runtime_dir is None:
        runtime_dir = get_runtime_dir()

    config = load_config(runtime_dir)
    lifecycle = DaemonLifecycle(runtime_dir)
    state_manager = StateManager(runtime_dir)
    resolution_storage = ResolutionStorage(runtime_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        yield
        # Shutdown

    app = FastAPI(
        title="Good Night API",
        description="API for the Good Night AI reflection system",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/status", response_model=StatusResponse)
    async def get_status() -> StatusResponse:
        """Get daemon and system status."""
        state = state_manager.state

        return StatusResponse(
            daemon_running=lifecycle.is_running(),
            daemon_pid=lifecycle.get_pid(),
            runtime_dir=str(runtime_dir),
            provider=config.provider.default,
            api_port=config.api.port,
            last_dream_run=(
                state.dreaming.last_run.isoformat()
                if state.dreaming.last_run
                else None
            ),
            total_dream_runs=state.dreaming.total_runs,
            total_issues_found=state.dreaming.issues_found_total,
            total_resolutions=state.dreaming.resolutions_generated_total,
        )

    @app.post("/api/v1/dream/trigger", response_model=TriggerResponse)
    async def trigger_dream(request: TriggerRequest) -> TriggerResponse:
        """Trigger a dreaming cycle."""
        from ..dreaming.orchestrator import DreamingOrchestrator

        try:
            event_stream = get_event_stream()

            orchestrator = DreamingOrchestrator(
                runtime_dir=runtime_dir,
                config=config,
                dry_run=request.dry_run,
                event_stream=event_stream,
            )

            if request.connector:
                orchestrator.set_connector_filter([request.connector])
            if request.module:
                orchestrator.set_prompt_filter([request.module])

            # Run in background
            result = await orchestrator.run()

            if result.success:
                return TriggerResponse(
                    success=True,
                    run_id=result.run_id,
                    message=(
                        f"Dreaming cycle completed. "
                        f"Analyzed {result.conversations_analyzed} conversations, "
                        f"found {result.issues_found} issues, "
                        f"generated {result.resolutions_generated} resolutions."
                    ),
                )
            else:
                return TriggerResponse(
                    success=False,
                    message=result.error or "Unknown error",
                )

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/v1/dream/status", response_model=DreamStatusResponse)
    async def get_dream_status() -> DreamStatusResponse:
        """Get current dreaming status with active agents."""
        event_stream = get_event_stream()

        active_agents = {
            agent_id: event.to_dict()
            for agent_id, event in event_stream.get_active_agents().items()
        }

        recent_events = [e.to_dict() for e in event_stream.get_recent(20)]

        return DreamStatusResponse(
            running=event_stream.is_running,
            run_id=event_stream.run_id,
            active_agents=active_agents,
            recent_events=recent_events,
        )

    @app.websocket("/api/v1/dream/events")
    async def dream_events_websocket(websocket: WebSocket) -> None:
        """WebSocket endpoint for real-time event streaming."""
        await websocket.accept()

        event_stream = get_event_stream()
        event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()

        def on_event(event: AgentEvent) -> None:
            try:
                event_queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # Drop events if queue is full

        event_stream.subscribe(on_event)

        try:
            # Send any recent events first
            for event in event_stream.get_recent(10):
                await websocket.send_json(event.to_dict())

            # Stream new events
            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                    await websocket.send_json(event.to_dict())
                except asyncio.TimeoutError:
                    # Send keepalive ping
                    await websocket.send_json({"type": "ping"})

        except WebSocketDisconnect:
            pass
        finally:
            event_stream.unsubscribe(on_event)

    @app.get("/api/v1/dream/history", response_model=HistoryResponse)
    async def get_history(limit: int = 10) -> HistoryResponse:
        """Get dreaming history."""
        resolutions = resolution_storage.list_recent(limit=limit)

        items = []
        for res in resolutions:
            action_count = sum(len(cr.actions) for cr in res.resolutions)
            items.append(HistoryItem(
                id=res.id,
                created_at=res.created_at.isoformat(),
                conversations_analyzed=res.metadata.get("conversations_analyzed", 0),
                issues_found=len(res.metadata.get("issues", [])),
                resolutions_count=action_count,
            ))

        return HistoryResponse(items=items)

    @app.get("/api/v1/config", response_model=ConfigResponse)
    async def get_config() -> ConfigResponse:
        """Get current configuration."""
        return ConfigResponse(
            daemon={
                "poll_interval": config.daemon.poll_interval,
                "dream_interval": config.daemon.dream_interval,
                "log_level": config.daemon.log_level,
            },
            api={
                "enabled": config.api.enabled,
                "host": config.api.host,
                "port": config.api.port,
            },
            provider={
                "default": config.provider.default,
                "anthropic": {
                    "model": config.provider.anthropic.model,
                },
                "bedrock": {
                    "region": config.provider.bedrock.region,
                    "model": config.provider.bedrock.model,
                },
            },
            enabled={
                "connectors": config.enabled.connectors,
                "artifacts": config.enabled.artifacts,
                "prompts": config.enabled.prompts,
            },
            dreaming={
                "exploration_agents": config.dreaming.exploration_agents,
                "historical_lookback": config.dreaming.historical_lookback,
            },
        )

    @app.patch("/api/v1/config")
    async def update_config(updates: dict[str, Any]) -> dict[str, str]:  # noqa: ARG001
        """Update configuration (partial update)."""
        # For now, just return a message
        # Full implementation would update the config file
        _ = updates  # Will be used when implemented
        return {"message": "Config update not yet implemented"}

    @app.get("/api/v1/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy"}

    return app


def run_server(host: str = "127.0.0.1", port: int = 7777) -> None:
    """Run the API server."""
    import uvicorn

    app = create_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
