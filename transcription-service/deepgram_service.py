"""Deepgram transcription service."""

import httpx
import logging
from typing import Optional, Dict, Any
from config import settings
from json_utils import RateLimitException

logger = logging.getLogger(__name__)


class DeepgramService:
    """Transcription via Deepgram API."""
    
    BASE_URL = "https://api.deepgram.com/v1"
    
    def __init__(self):
        if not settings.DEEPGRAM_API_KEY:
            raise ValueError("DEEPGRAM_API_KEY not set")
        self._project_id: Optional[str] = None
    
    def _headers(self) -> dict:
        return {"Authorization": f"Token {settings.DEEPGRAM_API_KEY}"}
    
    async def _get_project_id(self) -> Optional[str]:
        if self._project_id:
            return self._project_id
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get(f"{self.BASE_URL}/projects", headers=self._headers())
                if r.status_code == 200:
                    projects = r.json().get("projects", [])
                    if projects:
                        self._project_id = projects[0]["project_id"]
        except Exception as e:
            logger.warning(f"Project ID failed: {e}")
        return self._project_id
    
    async def get_balance(self) -> Optional[float]:
        pid = await self._get_project_id()
        if not pid:
            return None
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get(f"{self.BASE_URL}/projects/{pid}/balances", headers=self._headers())
                if r.status_code == 200:
                    for b in r.json().get("balances", []):
                        if float(b.get("amount", 0)) > 0:
                            return float(b["amount"])
        except Exception as e:
            logger.warning(f"Balance failed: {e}")
        return None
    
    async def get_request_cost(self, request_id: str) -> Optional[float]:
        pid = await self._get_project_id()
        if not pid:
            return None
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get(f"{self.BASE_URL}/projects/{pid}/requests/{request_id}", headers=self._headers())
                if r.status_code == 200:
                    cost = r.json().get("response", {}).get("details", {}).get("usd")
                    return float(cost) if cost else None
        except Exception as e:
            logger.warning(f"Cost failed: {e}")
        return None
    
    async def transcribe(self, audio_data: bytes, mimetype: str = "audio/wav", language: str = "multi") -> Dict[str, Any]:
        """Transcribe audio. Language: en, hi, multi (Hinglish)."""
        params = {
            "model": settings.DEEPGRAM_MODEL,
            "smart_format": "true", "punctuate": "true", "utterances": "true",
            "detect_entities": "true", "sentiment": "true", "intents": "true", "topics": "true",
        }
        
        if language == "multi":
            params["detect_language"] = "true"
        else:
            params["language"] = language
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as c:
                r = await c.post(
                    f"{self.BASE_URL}/listen", params=params,
                    headers={**self._headers(), "Content-Type": mimetype}, content=audio_data
                )
                r.raise_for_status()
                request_id = r.headers.get("dg-request-id")
                data = r.json()
            
            results = data.get("results", {})
            channels = results.get("channels", [])
            
            transcript = ""
            if channels and channels[0].get("alternatives"):
                transcript = channels[0]["alternatives"][0].get("transcript", "")
            
            duration = data.get("metadata", {}).get("duration", 0.0)
            
            transcription = {
                "fullTranscript": transcript,
                "utterances": [
                    {"transcript": u.get("transcript", ""), "confidence": u.get("confidence", 0),
                     "start": u.get("start", 0), "end": u.get("end", 0)}
                    for u in results.get("utterances", [])
                ],
                "sentiments": [{"sentiment": s.get("sentiment", "")} for s in results.get("sentiments", {}).get("segments", [])],
                "topics": [t.get("topic", "") for seg in results.get("topics", {}).get("segments", []) for t in seg.get("topics", [])]
            }
            
            cost = await self.get_request_cost(request_id) if request_id else None
            balance = await self.get_balance()
            
            return {
                "transcript": transcript,
                "duration": round(duration, 1),
                "transcription": transcription,
                "billing": {
                    "consumed": {"duration_seconds": round(duration, 1), "cost_usd": f"{cost:.5f}" if cost else "N/A"},
                    "left": {"credits": f"{balance:.2f}" if balance else "N/A"}
                }
            }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitException("Rate limit exceeded")
            logger.error(f"HTTP error: {e}")
            raise
        except Exception as e:
            logger.error(f"Transcribe failed: {e}")
            raise
