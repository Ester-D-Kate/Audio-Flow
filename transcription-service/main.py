"""Transcription Microservice."""

import logging
import mimetypes

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from routes import router
from config import settings

logging.basicConfig(level=logging.INFO)
mimetypes.add_type("audio/ogg", ".opus")

app = FastAPI(title="Transcription Service")


@app.middleware("http")
async def verify_internal_key(request: Request, call_next):
    if settings.INTERNAL_API_KEY:
        if request.url.path not in ["/docs", "/openapi.json", "/"]:
            if request.headers.get("x-internal-api-key") != settings.INTERNAL_API_KEY:
                return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.TRANSCRIPTION_SERVICE_PORT, reload=True)
