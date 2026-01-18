"""API Routes for Transcription Service."""

import logging
import mimetypes
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException

from schemas import FormatRequest, PromptRequest
from deepgram_service import DeepgramService
from groq_service import GroqService
from json_utils import RateLimitException, HallucinationException
from prompts import build_llm_prompt, build_generator_prompt

logger = logging.getLogger(__name__)

deepgram = DeepgramService()
groq = GroqService()
router = APIRouter()


@router.get("/")
async def root():
    return {"status": "running"}


@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...), start_time: float = 0,
    end_time: Optional[float] = None, language: str = "multi"
):
    """Transcribe audio. Language: en, hi, multi."""
    try:
        audio = await file.read()
        mime = file.content_type
        if not mime or mime == "application/octet-stream":
            mime, _ = mimetypes.guess_type(file.filename or "") or ("audio/wav", None)
        
        result = await deepgram.transcribe(audio, mime or "audio/wav", language)
        duration = result.get("duration", 20)
        if end_time is None:
            end_time = start_time + duration
        
        return {
            "chunk": {"startTime": start_time, "endTime": end_time, "duration": duration},
            "transcription": result.get("transcription", {}),
            "billing": result.get("billing")
        }
    except RateLimitException:
        raise HTTPException(429, "Rate limit exceeded")
    except Exception as e:
        logger.error(f"Transcribe: {e}")
        raise HTTPException(500, str(e))


@router.post("/format")
async def format_transcript(request: FormatRequest):
    """Format batches into final transcript."""
    if not request.batches:
        raise HTTPException(400, "No batches")
    try:
        batches = [b.model_dump() for b in request.batches]
        system_prompt, user_prompt = build_llm_prompt(batches, request.keyword_preferences)
        return await groq.format_transcript(system_prompt, user_prompt)
    except RateLimitException:
        raise HTTPException(429, "Rate limit exceeded")
    except HallucinationException:
        raise HTTPException(500, "LLM produced invalid response")
    except Exception as e:
        logger.error(f"Format: {e}")
        raise HTTPException(500, str(e))


@router.post("/prompt")
async def generate_text(request: PromptRequest):
    """Generate text from query + context."""
    if not request.user_query:
        raise HTTPException(400, "No user_query")
    try:
        valid_images = [
            img for img in (request.context_images or [])
            if img and img != "string" and (img.startswith("http") or len(img) > 50)
        ][:3]
        
        if valid_images:
            return await groq.generate_with_vision(
                request.user_query,
                request.context_text if request.context_text != "string" else None,
                valid_images
            )
        else:
            ctx = request.context_text if request.context_text != "string" else None
            return await groq.generate_text(build_generator_prompt(request.user_query, ctx))
    except RateLimitException:
        raise HTTPException(429, "Rate limit exceeded")
    except HallucinationException:
        raise HTTPException(500, "LLM produced invalid response")
    except Exception as e:
        logger.error(f"Prompt: {e}")
        raise HTTPException(500, str(e))


@router.post("/prompt/upload")
async def generate_with_upload(
    user_query: str, context_text: Optional[str] = None,
    images: list[UploadFile] = File(default=[])
):
    """Generate text with uploaded images."""
    if not user_query:
        raise HTTPException(400, "No user_query")
    try:
        import base64
        image_b64 = [base64.b64encode(await f.read()).decode() for f in images[:3]]
        
        if image_b64:
            return await groq.generate_with_vision(user_query, context_text, image_b64)
        else:
            return await groq.generate_text(build_generator_prompt(user_query, context_text))
    except RateLimitException:
        raise HTTPException(429, "Rate limit exceeded")
    except HallucinationException:
        raise HTTPException(500, "LLM produced invalid response")
    except Exception as e:
        logger.error(f"Prompt upload: {e}")
        raise HTTPException(500, str(e))
