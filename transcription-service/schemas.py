"""Pydantic schemas for request/response models."""

from typing import List, Optional
from pydantic import BaseModel, Field


class ChunkInfo(BaseModel):
    startTime: float
    endTime: float
    duration: Optional[float] = None


class Utterance(BaseModel):
    transcript: str
    confidence: float
    start: float
    end: float


class TranscriptionData(BaseModel):
    fullTranscript: str
    utterances: List[Utterance] = Field(default_factory=list)
    sentiments: List[dict] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)


class BatchData(BaseModel):
    chunk: ChunkInfo
    transcription: TranscriptionData


class FormatRequest(BaseModel):
    batches: List[BatchData]
    keyword_preferences: Optional[dict] = Field(None, example={"btech": "B.Tech"})


class PromptRequest(BaseModel):
    user_query: str
    context_text: Optional[str] = None
    context_images: Optional[List[str]] = Field(None, description="URLs or base64 images (max 3)")
