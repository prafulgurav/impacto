"""The explainer, streaming and not (§2.5).

The event order is the product decision, not an implementation detail:

    event: composed   the complete, deterministic, fully-cited answer — immediately
    event: token      LLM narration, if a provider is configured
    event: done       compliance flags, whether the LLM was used, and the audit id

`composed` fires before any model is consulted, so the user never sees a spinner
where an answer should be and never sees an ungrounded answer. If narration fails
or trips the guardrail, the composed answer simply stands.

Nothing here is ever cached: a stale explanation attached to today's market move is
exactly the misleading output the compliance layer exists to prevent.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import date

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import StreamingResponse

from ...llm import LLMError, get_llm
from ...models import Explanation
from ..cache import NO_STORE
from ..deps import OptionalUser, ReposDep, ServiceDep

log = logging.getLogger(__name__)
router = APIRouter(tags=["explain"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'), default=str)}\n\n"


def _record(repos, question: str, explanation: Explanation, model: str) -> str:
    row = repos.audit.record(
        kind="explain",
        question=question,
        answer=explanation.answer,
        citations=[c.model_dump() for c in explanation.citations],
        compliance_flags=explanation.compliance_flags,
        model=model if explanation.used_llm else None,
        used_llm=explanation.used_llm,
    )
    repos.flush()
    return str(row.id)


@router.get("/explain", response_model=Explanation)
def explain(
    service: ServiceDep,
    repos: ReposDep,
    response: Response,
    q: str = Query(min_length=3, max_length=500),
    as_of: date | None = None,
    target: str | None = None,
) -> Explanation:
    """Non-streaming explainer. Same guardrail, same audit row."""
    response.headers["Cache-Control"] = NO_STORE
    result = service.explainer.explain(q, as_of=as_of or service.latest_event_date(), target=target)
    _record(repos, q, result, get_llm().model)
    return result


@router.get("/explain/stream")
def explain_stream(
    request: Request,
    service: ServiceDep,
    repos: ReposDep,
    user: OptionalUser,
    q: str = Query(min_length=3, max_length=500),
    as_of: date | None = None,
    target: str | None = None,
) -> StreamingResponse:
    explainer = service.explainer
    as_of = as_of or service.latest_event_date()
    user_id = user.id if user else None

    def stream() -> Iterator[str]:
        # 1. Compose first, always. This is the shippable answer.
        facts, citations = explainer.compose(q, as_of=as_of, target=target)
        composed = explainer.finalise(q, facts, citations, narrated=None)
        yield _sse(
            "composed",
            {
                "answer": composed.answer,
                "citations": [c.model_dump() for c in composed.citations],
                "disclaimer": composed.disclaimer,
            },
        )

        # 2. Narrate, if a provider is configured. Tokens are streamed for feel, but
        #    the guardrail runs on the *complete* narration — a partial rewrite
        #    cannot be compliance-checked, so nothing is swapped in until it ends.
        llm = get_llm()
        pieces: list[str] = []
        narration_failed = False
        if llm.name != "none":
            try:
                for token in explainer.narrate_stream(q, facts):
                    pieces.append(token)
                    yield _sse("token", {"t": token})
            except LLMError as exc:
                narration_failed = True
                log.info("narration failed, composed answer stands: %s", exc)
            except Exception as exc:
                narration_failed = True
                log.warning("narration errored, composed answer stands: %s", exc)

        narrated = "".join(pieces).strip() or None
        if narration_failed:
            narrated = None

        final = explainer.finalise(q, facts, citations, narrated)
        if narrated and not final.used_llm:
            # The narration was produced but rejected by the guardrail. Tell the
            # client explicitly so it can discard the tokens it already painted.
            yield _sse("revert", {"reason": "narration failed compliance"})

        audit_id = _record(repos, q, final, llm.model)
        yield _sse(
            "done",
            {
                "answer": final.answer,
                "complianceFlags": final.compliance_flags,
                "usedLlm": final.used_llm,
                "auditId": audit_id,
                "userId": str(user_id) if user_id else None,
            },
        )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": NO_STORE,
            # Without this an nginx in front of the API buffers the whole stream and
            # `composed` arrives with the rest — defeating the entire design.
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


class RenderedBeacon(dict):
    pass


@router.post("/explain/rendered", status_code=202)
def rendered_beacon(
    payload: dict,
    repos: ReposDep,
    response: Response,
) -> dict:
    """Confirm that an explanation actually painted (§6.6).

    The server's record is what it produced; this is what a user saw. For a
    five-year evidentiary record those are not the same claim.
    """
    response.headers["Cache-Control"] = NO_STORE
    audit_id = str(payload.get("auditId", "")).strip()
    if not audit_id:
        return {"recorded": False}
    repos.audit.record(kind="rendered", question=audit_id, answer="rendered")
    return {"recorded": True}


__all__ = ["router"]
