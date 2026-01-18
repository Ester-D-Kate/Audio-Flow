import os
import logging
from groq import Groq

logger = logging.getLogger(__name__)


class GroqLLMService:
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY environment variable not set")
        self.client = Groq(api_key=self.api_key)
        logger.info("Groq LLM service initialized")

    async def generate_response(self, message: str, model: str = "llama-3.3-70b-versatile") -> str:
        """Generate a response using Groq's LLM."""
        logger.info("LLM response generation started")
        try:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": message,
                    }
                ],
                model=model,
            )
            logger.info("LLM response generated successfully")
            return chat_completion.choices[0].message.content
        except Exception as e:
            logger.error("Groq LLM request failed")
            raise e

