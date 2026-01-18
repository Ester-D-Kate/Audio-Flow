"""Rate limit tracking for Groq API."""

import time
import datetime
import threading
from collections import deque


class RateLimitTracker:
    """Thread-safe rate limit tracking from headers + calculated RPM/TPD."""
    
    RPM_LIMIT = 30
    
    def __init__(self):
        self._lock = threading.Lock()
        self.start_time = datetime.datetime.now()
        self._request_times: deque = deque()
        self._tokens_today = 0
        self._today = datetime.date.today()
        self.rpd_limit = 0
        self.rpd_remaining = 0
        self.tpm_limit = 0
        self.tpm_remaining = 0
    
    def record(self, tokens: int):
        """Record request for RPM/TPD tracking."""
        with self._lock:
            now = time.time()
            self._request_times.append(now)
            while self._request_times and self._request_times[0] < now - 60:
                self._request_times.popleft()
            
            if datetime.date.today() != self._today:
                self._tokens_today = 0
                self._today = datetime.date.today()
            self._tokens_today += tokens
    
    def update_headers(self, headers: dict):
        """Update limits from Groq response headers."""
        with self._lock:
            try:
                self.rpd_limit = int(headers.get("x-ratelimit-limit-requests", 0))
                self.rpd_remaining = int(headers.get("x-ratelimit-remaining-requests", 0))
                self.tpm_limit = int(headers.get("x-ratelimit-limit-tokens", 0))
                self.tpm_remaining = int(headers.get("x-ratelimit-remaining-tokens", 0))
            except (ValueError, TypeError):
                pass
    
    def stats(self) -> dict:
        """Get current rate limit stats."""
        with self._lock:
            rpm_used = len(self._request_times)
            uptime = str(datetime.datetime.now() - self.start_time).split('.')[0]
            return {
                "rpd": {"limit": self.rpd_limit, "remaining": self.rpd_remaining},
                "tpm": {"limit": self.tpm_limit, "remaining": self.tpm_remaining},
                "rpm": {"limit": self.RPM_LIMIT, "remaining": max(0, self.RPM_LIMIT - rpm_used), "used": rpm_used},
                "tpd": {"used": self._tokens_today},
                "uptime": uptime
            }


tracker = RateLimitTracker()
