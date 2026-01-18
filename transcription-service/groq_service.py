"""Groq LLM service for transcript formatting and text generation."""

import asyncio
import logging
from groq import Groq, RateLimitError
from config import settings
from rate_limiter import tracker
from json_utils import call_with_retry, RateLimitException

logger = logging.getLogger(__name__)


class GroqService:
    """LLM service via Groq API."""
    
    def __init__(self):
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not set")
        self.client = Groq(api_key=settings.GROQ_API_KEY)
    
    def _build_billing(self, inp: int, out: int, input_cost: float, output_cost: float) -> dict:
        """Build billing response."""
        total = inp + out
        cost = inp * input_cost + out * output_cost
        tracker.record(total)
        return {
            "consumed": {"input_tokens": inp, "output_tokens": out, "total_tokens": total, "cost_usd": f"{cost:.6f}"},
            "limits": tracker.stats()
        }
    
    async def format_transcript(self, system_prompt: str, user_prompt: str) -> dict:
        """Format transcript with JSON validation and retry."""
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        result = await call_with_retry(
            self.client, messages, settings.GROQ_FORMAT_MODEL, 0.1,
            "finalTranscript", '{"finalTranscript": "text"}',
            tracker, settings.GROQ_FORMAT_INPUT_COST, settings.GROQ_FORMAT_OUTPUT_COST, self._build_billing
        )
        logger.info(f"Format: {result['billing']['consumed']['total_tokens']} tokens")
        return result
    
    async def generate_text(self, prompt: str) -> dict:
        """Generate text with JSON validation and retry."""
        result = await call_with_retry(
            self.client, [{"role": "user", "content": prompt}], settings.GROQ_PROMPT_MODEL, 0.2,
            "generatedText", '{"generatedText": "text"}',
            tracker, settings.GROQ_PROMPT_INPUT_COST, settings.GROQ_PROMPT_OUTPUT_COST, self._build_billing
        )
        logger.info(f"Generate: {result['billing']['consumed']['total_tokens']} tokens")
        return result
    
    async def generate_with_vision(self, user_query: str, context_text: str = None, images: list = None) -> dict:
        """Generate text using VLM with images."""
        try:
            content = []
            
            # Add images
            for img in (images or [])[:3]:
                if not img or len(img) < 10:
                    continue
                if img.startswith(("http://", "https://", "data:")):
                    img_url = img
                elif img.startswith("/9j/"):
                    img_url = f"data:image/jpeg;base64,{img}"
                elif img.startswith("iVBOR"):
                    img_url = f"data:image/png;base64,{img}"
                else:
                    img_url = f"data:image/jpeg;base64,{img}"
                content.append({"type": "image_url", "image_url": {"url": img_url}})
            
            # Add text
            text = "OUTPUT ONLY what is asked. NO intro phrases.\n\n"
            if context_text:
                text += f"CONTEXT:\n{context_text}\n\n"
            text += f"TASK: {user_query}"
            content.append({"type": "text", "text": text})
            
            # Call VLM (no JSON mode) - run in threadpool to avoid blocking
            def call_vlm():
                resp = self.client.chat.completions.with_raw_response.create(
                    messages=[{"role": "user", "content": content}],
                    model=settings.GROQ_PROMPT_MODEL, temperature=0.7, max_tokens=4096
                )
                tracker.update_headers(dict(resp.headers))
                return resp.parse()
            
            comp = await asyncio.to_thread(call_vlm)
            
            inp = comp.usage.prompt_tokens if comp.usage else 0
            out = comp.usage.completion_tokens if comp.usage else 0
            logger.info(f"VLM: {inp + out} tokens")
            
            return {
                "result": {"generatedText": comp.choices[0].message.content},
                "billing": self._build_billing(inp, out, settings.GROQ_PROMPT_INPUT_COST, settings.GROQ_PROMPT_OUTPUT_COST)
            }
        except RateLimitError:
            raise RateLimitException("Rate limit exceeded")
        except Exception as e:
            logger.error(f"VLM failed: {e}")
            raise
