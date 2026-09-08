from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.ml.text_to_sql import answer_question
from app.services.rate_limit import assistant_rate_limiter

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

MAX_QUESTION_LENGTH = 500


class AskRequest(BaseModel):
    question: str = Field(max_length=MAX_QUESTION_LENGTH)


@router.post("/ask")
def ask(req: AskRequest, request: Request) -> dict:
    """Text-to-SQL over the real warehouse via Gemini. See
    app/ml/text_to_sql.py for the grounding schema and the read-only /
    keyword-denylist safety checks on the generated query.

    Rate-limited (app/services/rate_limit.py) — this is the one endpoint in
    this app that costs real money per call and has no login system in
    front of it, so a per-IP + global-daily cap bounds worst-case exposure
    rather than leaving it open."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question is required")

    client_ip = request.client.host if request.client else "unknown"
    allowed, reason = assistant_rate_limiter.check(client_ip)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    try:
        return answer_question(req.question)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
