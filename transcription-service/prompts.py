"""LLM prompts for transcript formatting and text generation."""

from typing import List, Dict, Any, Optional, Tuple

SYSTEM_PROMPT = """You are a transcription formatter. Clean up messy speech into perfect written text.

RULES:
1. REMOVE disfluencies: uh, um, like (when filler)
2. SELF-CORRECTIONS: "five, sorry, six" → "six"
3. LISTS: numbered with \\n: "1. Item\\n2. Item"
4. NUMBERS: words to digits, add % or $ as appropriate
5. QUOTES: "quote X unquote" → 'X'
6. GRAMMAR: fix tense, punctuation, capitalization
7. KEYWORDS: apply replacements if provided
8. HINGLISH: keep Hindi in romanized form, don't translate

OUTPUT: JSON with finalTranscript. Use \\n for newlines."""


GENERATOR_PROMPT = """You are a text generator. Output ONLY the requested text. NO intro phrases.

RULES:
1. NO placeholders like [Name]
2. Use \\n for lists/sections
3. Numbers as digits
4. For emails: greeting, body, closing only

OUTPUT: JSON with generatedText only."""


def build_llm_prompt(batches: List[Dict[str, Any]], keyword_preferences: Optional[Dict[str, str]] = None) -> Tuple[str, str]:
    """Build system and user prompts from batches."""
    if not batches:
        raise ValueError("No batches provided")
    
    raw_texts = []
    for batch in batches:
        text = batch.get("transcription", {}).get("fullTranscript", "")
        if text:
            raw_texts.append(text)
    
    raw_transcript = " ".join(raw_texts)
    
    keyword_section = ""
    if keyword_preferences:
        pairs = list(keyword_preferences.items())[:100]
        keyword_section = "\n\nREPLACE: " + ", ".join([f'"{k}"→"{v}"' for k, v in pairs])
    
    user_prompt = f'Format: "{raw_transcript}"{keyword_section}\n\nReturn: {{"finalTranscript": "..."}}'
    return SYSTEM_PROMPT, user_prompt


def build_generator_prompt(user_query: str, context_text: Optional[str] = None) -> str:
    """Build prompt for text generation."""
    ctx = f"\nCONTEXT: {context_text}\n" if context_text else ""
    return f"{GENERATOR_PROMPT}\n{ctx}REQUEST: {user_query}\n\nReturn: {{\"generatedText\": \"...\"}}"
