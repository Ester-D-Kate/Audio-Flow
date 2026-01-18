"""
Deepgram Response Parser v2

Parses raw Deepgram API responses into a clean, structured format
with transcription data, billing information, and proper error handling.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import time


def parse_deepgram_response(response: Dict[str, Any], start_time: Optional[float] = None) -> Dict[str, Any]:
    """
    Parse Deepgram API response into structured transcription and billing data.
    
    Args:
        response: Raw Deepgram API response dictionary
        start_time: Optional start time for processing time calculation
        
    Returns:
        Structured dictionary with 'success', 'transcription', 'billing', and 'warnings'
    """
    warnings = []
    
    try:
        transcription = _parse_transcription(response, warnings)
        billing = _parse_billing(response, start_time)
        
        return {
            "success": True,
            "transcription": transcription,
            "billing": billing,
            "warnings": warnings
        }
    except Exception as e:
        return {
            "success": False,
            "transcription": None,
            "billing": None,
            "warnings": [f"Parser error: {str(e)}"]
        }


def _parse_transcription(response: Dict[str, Any], warnings: List[str]) -> Dict[str, Any]:
    """Extract all transcription-related data."""
    results = response.get("results", {})
    channels = results.get("channels", [])
    
    # Get first channel's first alternative (best result)
    alternatives = []
    if channels and len(channels) > 0:
        alternatives = channels[0].get("alternatives", [])
    
    first_alt = alternatives[0] if alternatives else {}
    words = first_alt.get("words", [])
    
    # Calculate statistics
    statistics = _calculate_statistics(words, response)
    
    return {
        "fullTranscript": first_alt.get("transcript", ""),
        "statistics": statistics,
        "paragraphs": _parse_paragraphs(first_alt, results),
        "utterances": _parse_utterances(results),
        "sentiment": _parse_overall_sentiment(results),
        "entities": _parse_entities(first_alt),
        "intents": _parse_intents(results),
        "topics": _parse_topics(results),
        "wordTimestamps": _format_word_timestamps_optimized(words)
    }


def _calculate_statistics(words: List[Dict], response: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate transcription statistics."""
    duration = response.get("metadata", {}).get("duration", 0)
    
    total_words = len(words)
    avg_confidence = 0
    
    if words:
        confidences = [w.get("confidence", 0) for w in words]
        avg_confidence = sum(confidences) / len(confidences)
    
    return {
        "totalWords": total_words,
        "duration": round(duration, 2),
        "averageConfidence": round(avg_confidence, 3)
    }


def _parse_paragraphs(alternative: Dict[str, Any], results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract paragraphs with sentiment data."""
    paragraphs_data = alternative.get("paragraphs", {})
    paragraphs_list = paragraphs_data.get("paragraphs", [])
    
    parsed = []
    for para in paragraphs_list:
        sentences = para.get("sentences", [])
        if not sentences:
            continue
            
        # Combine sentence texts
        text = " ".join(s.get("text", "") for s in sentences)
        start_time = sentences[0].get("start", 0) if sentences else 0
        end_time = sentences[-1].get("end", 0) if sentences else 0
        
        # Get sentiment directly from paragraph object
        sentiment = para.get("sentiment", "neutral")
        sentiment_score = para.get("sentiment_score", 0)
        
        parsed.append({
            "text": text,
            "startTime": round(start_time, 2),
            "endTime": round(end_time, 2),
            "sentiment": sentiment,
            "sentimentScore": round(sentiment_score, 3)
        })
    
    return parsed



def _parse_utterances(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract utterances with sentiment data."""
    utterances = results.get("utterances", [])
    
    parsed = []
    for utt in utterances:
        # Get sentiment directly from utterance object
        sentiment = utt.get("sentiment", "neutral")
        sentiment_score = utt.get("sentiment_score", 0)
        
        parsed.append({
            "text": utt.get("transcript", ""),
            "startTime": round(utt.get("start", 0), 2),
            "endTime": round(utt.get("end", 0), 2),
            "confidence": round(utt.get("confidence", 0), 3),
            "sentiment": sentiment,
            "sentimentScore": round(sentiment_score, 3)
        })
    
    return parsed



def _find_sentiment_for_time(segments: List[Dict], start: float, end: float) -> Dict[str, Any]:
    """Find sentiment segment that best overlaps with given time range."""
    best_match = None
    best_overlap = 0
    
    for seg in segments:
        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", 0)
        
        # Calculate overlap
        overlap_start = max(start, seg_start)
        overlap_end = min(end, seg_end)
        overlap = max(0, overlap_end - overlap_start)
        
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = seg
    
    if best_match:
        return {
            "sentiment": best_match.get("sentiment", "neutral"),
            "sentiment_score": best_match.get("sentiment_score", 0)
        }
    
    return {"sentiment": "neutral", "sentiment_score": 0}


def _parse_overall_sentiment(results: Dict[str, Any]) -> Dict[str, Any]:
    """Extract overall sentiment from results."""
    sentiments = results.get("sentiments", {})
    average = sentiments.get("average", {})
    
    return {
        "overall": average.get("sentiment", "neutral"),
        "score": round(average.get("sentiment_score", 0), 3)
    }


def _parse_entities(alternative: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract detected entities."""
    entities = alternative.get("entities", [])
    words = alternative.get("words", [])
    
    parsed = []
    for entity in entities:
        # Try to get timestamp from word_index or start_word
        timestamp = entity.get("start", 0)
        if timestamp == 0:
            word_index = entity.get("word_index", entity.get("start_word"))
            if word_index is not None and word_index < len(words):
                timestamp = words[word_index].get("start", 0)
        
        parsed.append({
            "type": entity.get("label", "UNKNOWN"),
            "value": entity.get("value", ""),
            "confidence": round(entity.get("confidence", 0), 4),
            "timestamp": round(timestamp, 2)
        })
    
    return parsed


def _parse_intents(results: Dict[str, Any]) -> List[str]:
    """Extract intent descriptions."""
    intents_data = results.get("intents", {})
    segments = intents_data.get("segments", [])
    
    intent_descriptions = []
    for seg in segments:
        intents = seg.get("intents", [])
        for intent in intents:
            desc = intent.get("intent", "")
            if desc and desc not in intent_descriptions:
                intent_descriptions.append(desc)
    
    return intent_descriptions


def _parse_topics(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract detected topics."""
    topics_data = results.get("topics", {})
    segments = topics_data.get("segments", [])
    
    parsed = []
    for seg in segments:
        text = seg.get("text", "")
        topics = seg.get("topics", [])
        
        for topic in topics:
            # Note: Deepgram uses 'confidence_score' not 'confidence'
            confidence = topic.get("confidence_score", topic.get("confidence", 0))
            parsed.append({
                "topic": topic.get("topic", ""),
                "confidence": round(confidence, 3),
                "text": text
            })
    
    return parsed


def _format_word_timestamps_optimized(words: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Format word timestamps with summary and optional full string."""
    if not words:
        return {
            "summary": {
                "totalWords": 0,
                "firstWord": None,
                "lastWord": None
            },
            "full": ""
        }
    
    # Build full string
    formatted = []
    for word in words:
        w = word.get("word", "").lower()
        start = round(word.get("start", 0), 1)
        end = round(word.get("end", 0), 1)
        formatted.append(f"{w}({start}-{end})")
    
    full_string = ", ".join(formatted)
    
    first_word = words[0]
    last_word = words[-1]
    
    return {
        "summary": {
            "totalWords": len(words),
            "firstWord": {
                "word": first_word.get("word", ""),
                "start": round(first_word.get("start", 0), 2),
                "end": round(first_word.get("end", 0), 2)
            },
            "lastWord": {
                "word": last_word.get("word", ""),
                "start": round(last_word.get("start", 0), 2),
                "end": round(last_word.get("end", 0), 2)
            }
        },
        "full": full_string
    }


def _parse_billing(response: Dict[str, Any], start_time: Optional[float] = None) -> Dict[str, Any]:
    """Extract billing and metadata information."""
    metadata = response.get("metadata", {})
    results = response.get("results", {})
    
    # Model info
    model_info = metadata.get("model_info", {})
    first_model_key = list(model_info.keys())[0] if model_info else ""
    model_data = model_info.get(first_model_key, {})
    
    # Token usage from results
    sentiments = results.get("sentiments", {})
    topics = results.get("topics", {})
    intents = results.get("intents", {})
    summary = results.get("summary", {})
    
    # Calculate duration
    duration = metadata.get("duration", 0)
    
    # Cost calculation
    # Transcription: $0.0043 per minute -> per second = $0.0043/60
    transcription_cost = duration * (0.0043 / 60)
    
    # AI features cost (simplified estimate based on tokens)
    sentiment_tokens = _get_token_count(sentiments)
    topics_tokens = _get_token_count(topics)
    intents_tokens = _get_token_count(intents)
    
    # Approximate AI cost ($0.00015 per 1000 tokens)
    total_ai_tokens = (
        sentiment_tokens.get("input", 0) + sentiment_tokens.get("output", 0) +
        topics_tokens.get("input", 0) + topics_tokens.get("output", 0) +
        intents_tokens.get("input", 0) + intents_tokens.get("output", 0)
    )
    ai_cost = (total_ai_tokens / 1000) * 0.00015
    
    # Calculate processing time
    processing_time = None
    if start_time:
        processing_time = round(time.time() - start_time, 3)
    
    billing = {
        "requestId": metadata.get("request_id", ""),
        "duration": round(duration, 2),
        "model": {
            "name": model_data.get("name", "unknown"),
            "version": model_data.get("version", "unknown"),
            "architecture": model_data.get("arch", "unknown")
        },
        "tokensUsed": {
            "transcription": 0,  # STT doesn't use tokens in traditional sense
            "sentiment": sentiment_tokens,
            "topics": topics_tokens,
            "intents": intents_tokens,
            "summary": _get_token_count(summary)
        },
        "estimatedCost": {
            "transcription": round(transcription_cost, 6),
            "audioIntelligence": round(ai_cost, 6),
            "total": round(transcription_cost + ai_cost, 6),
            "currency": "USD"
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "channels": metadata.get("channels", 1)
    }
    
    if processing_time is not None:
        billing["processingTime"] = processing_time
    
    return billing


def _get_token_count(section: Dict[str, Any]) -> Dict[str, int]:
    """Extract token counts from a section's usage info."""
    usage = section.get("usage", {})
    return {
        "input": usage.get("input_tokens", 0),
        "output": usage.get("output_tokens", 0)
    }
