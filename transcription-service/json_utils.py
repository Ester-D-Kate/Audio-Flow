"""JSON parsing and LLM response handling."""

import asyncio
import json
import logging
from groq import RateLimitError

logger = logging.getLogger(__name__)


class RateLimitException(Exception):
    """API rate limit hit - return 429."""
    pass


class HallucinationException(Exception):
    """LLM failed to produce valid JSON after retry."""
    pass


def parse_json(content: str, expected_key: str = None) -> dict:
    """Parse JSON from LLM response. Raises ValueError if invalid."""
    try:
        result = json.loads(content)
        if expected_key and expected_key not in result:
            raise ValueError(f"Missing key: {expected_key}")
        return result
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")


def make_fix_prompt(response: str, error: str, expected_format: str) -> str:
    """Create retry prompt for invalid JSON."""
    return f"""Fix your invalid JSON response.
ERROR: {error}
YOUR RESPONSE: {response[:500]}
REQUIRED: {expected_format}
Return ONLY valid JSON."""


async def call_with_retry(client, messages, model, temp, expected_key, expected_format, 
                          tracker, input_cost, output_cost, build_billing):
    """Call LLM with JSON validation and retry on failure. Runs sync calls in threadpool."""
    total_in, total_out = 0, 0
    
    def call_llm(msgs):
        resp = client.chat.completions.with_raw_response.create(
            messages=msgs, model=model, temperature=temp,
            max_tokens=4096, response_format={"type": "json_object"}
        )
        tracker.update_headers(dict(resp.headers))
        comp = resp.parse()
        return (
            comp.choices[0].message.content,
            comp.usage.prompt_tokens if comp.usage else 0,
            comp.usage.completion_tokens if comp.usage else 0
        )
    
    try:
        content, inp, out = await asyncio.to_thread(call_llm, messages)
        total_in, total_out = inp, out
        
        try:
            result = parse_json(content, expected_key)
            return {"result": result, "billing": build_billing(total_in, total_out, input_cost, output_cost)}
        except ValueError as e:
            logger.warning(f"JSON parse failed, retrying: {e}")
            fix = make_fix_prompt(content, str(e), expected_format)
            retry_content, ri, ro = await asyncio.to_thread(call_llm, [{"role": "user", "content": fix}])
            total_in += ri
            total_out += ro
            
            try:
                result = parse_json(retry_content, expected_key)
                logger.info(f"Recovered via retry")
                return {"result": result, "billing": build_billing(total_in, total_out, input_cost, output_cost)}
            except ValueError:
                raise HallucinationException("LLM failed to produce valid JSON after retry")
    
    except RateLimitError as e:
        logger.warning(f"Rate limit: {e}")
        raise RateLimitException("Rate limit exceeded")
