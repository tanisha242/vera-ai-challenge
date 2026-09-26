"""
FastAPI application serving Vera AI Assistant HTTP API endpoints for magicpin AI Challenge.
Exposes /v1/healthz, /v1/metadata, /v1/context, /v1/tick, /v1/reply.
"""

import time
from datetime import datetime
from typing import Any
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

import config
from core.models import (
    ContextPush,
    ContextPushAck,
    ContextPushReject,
    HealthCheckResponse,
    MetadataResponse,
    TickRequest,
    TickResponse,
    ReplyRequest,
    ReplyResponse,
    TeardownResponse,
    Action,
)
from core.store import store as global_store
from core.suppression import suppression_engine as global_suppression
from engine.controller import VeraEngine

START_TIME = time.time()
engine = VeraEngine(store=global_store, suppression=global_suppression)

app = FastAPI(
    title="magicpin Vera AI Assistant API",
    version=config.BOT_VERSION,
    description="Merchant AI Assistant HTTP API for magicpin AI Challenge",
)


@app.post("/v1/teardown", response_model=TeardownResponse)
async def teardown():
    """
    Teardown protocol endpoint clearing all loaded contexts, suppression records,
    and conversation state to reset the bot state between evaluation runs.
    """
    engine.teardown()
    return TeardownResponse(status="ok", cleared=True)


@app.get("/v1/healthz", response_model=HealthCheckResponse)
async def healthz():
    """Liveness probe returning uptime and loaded context counts per scope."""
    uptime = int(time.time() - START_TIME)
    counts = global_store.get_counts()
    return HealthCheckResponse(
        status="ok",
        uptime_seconds=uptime,
        contexts_loaded=counts,
    )


@app.get("/v1/metadata", response_model=MetadataResponse)
async def metadata():
    """Bot metadata returning team name, model, approach, and version."""
    return MetadataResponse(
        team_name=config.TEAM_NAME,
        team_members=config.TEAM_MEMBERS,
        model=config.MODEL_NAME,
        approach=config.APPROACH_SUMMARY,
        contact_email=config.CONTACT_EMAIL,
        version=config.BOT_VERSION,
        submitted_at="2026-04-26T08:00:00Z",
    )


@app.post(
    "/v1/context",
    responses={
        200: {"model": ContextPushAck},
        409: {"model": ContextPushReject},
        400: {"model": ContextPushReject},
    },
)
async def push_context(body: ContextPush):
    """
    Receive context update (category, merchant, customer, trigger).
    Atomic versioning check: version <= stored returns 409 Conflict.
    Invalid scope returns 400 Bad Request.
    """
    success, ack_or_reason, cur_ver = global_store.put(
        scope=body.scope,
        context_id=body.context_id,
        version=body.version,
        payload=body.payload,
    )

    if success:
        now_iso = datetime.utcnow().isoformat() + "Z"
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "accepted": True,
                "ack_id": ack_or_reason,
                "stored_at": now_iso,
            },
        )

    if ack_or_reason == "stale_version":
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "accepted": False,
                "reason": "stale_version",
                "current_version": cur_ver,
            },
        )

    if ack_or_reason == "invalid_scope":
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "accepted": False,
                "reason": "invalid_scope",
                "details": f"Scope '{body.scope}' is invalid. Allowed scopes: category, merchant, customer, trigger.",
            },
        )

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"accepted": False, "reason": ack_or_reason},
    )


@app.post("/v1/tick", response_model=TickResponse)
async def tick(body: TickRequest):
    """
    Periodic wake-up request. Evaluates active triggers and returns proactive actions.
    """
    try:
        raw_actions = engine.process_tick(now_iso=body.now, available_trigger_ids=body.available_triggers)
        actions = [Action(**act) for act in raw_actions]
        return TickResponse(actions=actions)
    except Exception as e:
        # Prevent stack trace leakage in API responses
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing tick request.",
        )


@app.post("/v1/reply", response_model=ReplyResponse)
async def reply(body: ReplyRequest):
    """
    Receive incoming turn reply from simulated merchant/customer and process state transition.
    """
    try:
        reply_dict = engine.process_reply(
            conversation_id=body.conversation_id,
            merchant_id=body.merchant_id,
            customer_id=body.customer_id,
            from_role=body.from_role,
            message=body.message,
            received_at=body.received_at,
            turn_number=body.turn_number,
        )
        return ReplyResponse(**reply_dict)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing reply turn.",
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)
