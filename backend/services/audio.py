import os
import time
import json
import logging
import httpx
from typing import Dict, Any
from parser import parse_deepgram_response

logger = logging.getLogger(__name__)


class DeepgramTranscriptionService:
    """
    Transcription service using Deepgram REST API directly.
    Uses httpx for HTTP requests instead of SDK to avoid version compatibility issues.
    Returns parsed structured response.
    """
    
    def __init__(self):
        self.api_key = os.getenv("DEEPGRAM_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPGRAM_API_KEY environment variable not set")
        self.base_url = "https://api.deepgram.com/v1/listen"
        logger.info("Deepgram transcription service initialized")

    async def transcribe(self, audio_buffer: bytes, mimetype: str = "audio/wav") -> Dict[str, Any]:
        """
        Transcribe audio using Deepgram's Nova-3 model with Audio Intelligence features.
        Returns parsed structured response with transcription and billing data.
        """
        start_time = time.time()
        logger.info("Transcription started")
        
        try:
            params = {
                "model": "nova-3",
                "smart_format": "true",
                "punctuate": "true",
                "paragraphs": "true",
                "utterances": "true",
                "sentiment": "true",
                "intents": "true",
                "topics": "true",
                "summarize": "v2",
                "detect_entities": "true",
            }

            headers = {
                "Authorization": f"Token {self.api_key}",
                "Content-Type": mimetype,
            }

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    self.base_url,
                    params=params,
                    headers=headers,
                    content=audio_buffer,
                )
                response.raise_for_status()
                
                raw_response = json.loads(response.text)
                result = parse_deepgram_response(raw_response, start_time)
                logger.info("Transcription completed successfully")
                return result
                
        except Exception as e:
            logger.error("Deepgram transcription failed")
            return {
                "success": False,
                "transcription": None,
                "billing": None,
                "warnings": [f"Transcription error: {str(e)}"]
            }

