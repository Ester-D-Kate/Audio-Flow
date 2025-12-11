import os
import queue
import tempfile
import threading
import time
from pathlib import Path
from typing import List, Optional

import numpy as np
import sounddevice as sd
import soundfile as sf

from .llm_client import GroqLLM, GroqRateLimitError


class RecordingSegment(threading.Thread):
    def __init__(
        self,
        amplitude_queue: "queue.Queue[float]",
        stop_event: threading.Event,
        max_duration: float = 15.0,
        sample_rate: int = 16000,
        block_size: int = 1024,
    ) -> None:
        super().__init__(daemon=True)
        self.amplitude_queue = amplitude_queue
        self.stop_event = stop_event
        self.max_duration = max_duration
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.file_path: Optional[Path] = None
        self._started_at: float = time.time()

    def run(self) -> None:
        frames: List[np.ndarray] = []
        start = time.time()
        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=self.block_size,
            ) as stream:
                while not self.stop_event.is_set():
                    chunk, _ = stream.read(self.block_size)
                    frames.append(chunk.copy())
                    rms = float(np.sqrt(np.mean(np.square(chunk))))
                    # Normalize to [0,1] range for UI; guard division by zero
                    level = min(rms * 10.0, 1.0)
                    self.amplitude_queue.put(level)
                    if time.time() - start >= self.max_duration:
                        break
        except Exception:
            return

        if not frames:
            return
        data = np.concatenate(frames, axis=0)
        fd, temp_path = tempfile.mkstemp(prefix="seg_", suffix=".wav")
        os.close(fd)
        Path(temp_path).unlink(missing_ok=True)  # soundfile will recreate
        self.file_path = Path(temp_path)
        sf.write(self.file_path, data, self.sample_rate)


class OverlapAudioManager:
    """
    Recording: overlapping threads (new segment every 12s, each records up to 15s)
    As each segment finishes, immediately transcribe and append to transcript.
    On stop: wait for any in-flight transcriptions, then return.
    On new start: clear old transcript.
    """

    def __init__(
        self,
        llm: GroqLLM,
        transcript_path: Path,
        amplitude_queue: "queue.Queue[float]",
        segment_gap: float = 12.0,
        segment_duration: float = 15.0,
        max_retries: int = 3,
    ) -> None:
        self.llm = llm
        self.transcript_path = transcript_path
        self.amplitude_queue = amplitude_queue
        self.segment_gap = segment_gap
        self.segment_duration = segment_duration
        self.max_retries = max_retries
        self._stop_all = threading.Event()
        self._scheduler: threading.Thread | None = None
        self._active: List[RecordingSegment] = []
        self._lock = threading.Lock()
        self._paused = False
        self._pending_queue: queue.PriorityQueue[tuple[float, Optional[Path]]] = queue.PriorityQueue()
        self._results: List[tuple[float, str]] = []
        self._results_lock = threading.Lock()
        self._transcriber_thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._scheduler is not None and self._scheduler.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._paused = False
        self._stop_all = threading.Event()
        # Clear old transcript and results on new recording
        self.clear_transcript()
        with self._results_lock:
            self._results.clear()
        # Clear pending queue
        while not self._pending_queue.empty():
            try:
                self._pending_queue.get_nowait()
            except queue.Empty:
                break
        # Start transcriber thread
        self._transcriber_thread = threading.Thread(target=self._transcriber_loop, daemon=True)
        self._transcriber_thread.start()
        # Start scheduler
        self._scheduler = threading.Thread(target=self._schedule, daemon=True)
        self._scheduler.start()

    def resume(self) -> None:
        if self.running:
            return
        if not self._paused:
            return
        self._paused = False
        self._stop_all = threading.Event()
        # Restart transcriber if needed
        if self._transcriber_thread is None or not self._transcriber_thread.is_alive():
            self._transcriber_thread = threading.Thread(target=self._transcriber_loop, daemon=True)
            self._transcriber_thread.start()
        self._scheduler = threading.Thread(target=self._schedule, daemon=True)
        self._scheduler.start()

    def _schedule(self) -> None:
        """Spawn overlapping recording segments during recording."""
        while not self._stop_all.is_set():
            stop_evt = threading.Event()
            segment = RecordingSegment(
                amplitude_queue=self.amplitude_queue,
                stop_event=stop_evt,
                max_duration=self.segment_duration,
            )
            with self._lock:
                self._active.append(segment)
            segment.start()
            # Start a watcher to queue segment for transcription when it finishes
            watcher = threading.Thread(
                target=self._watch_segment,
                args=(segment,),
                daemon=True,
            )
            watcher.start()
            # Wait for gap or stop
            if self._stop_all.wait(self.segment_gap):
                break
        # When stop is requested, stop any ongoing segments
        self._stop_active_segments()

    def _watch_segment(self, segment: RecordingSegment) -> None:
        """Queue segment for transcription when it finishes naturally."""
        segment.join()
        with self._lock:
            if segment in self._active:
                self._active.remove(segment)
                if segment.file_path and segment.file_path.exists():
                    self._pending_queue.put((segment._started_at, segment.file_path))

    def _transcriber_loop(self) -> None:
        """Process transcription queue as segments arrive."""
        while True:
            try:
                start_ts, path = self._pending_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            
            if path is None:
                break

            text = self._transcribe_single(path)
            if text:
                with self._results_lock:
                    self._results.append((start_ts, text.strip()))
                self._write_transcript()
            path.unlink(missing_ok=True)

    def _write_transcript(self) -> None:
        """Write all results to transcript file, sorted by start time."""
        with self._results_lock:
            sorted_results = sorted(self._results, key=lambda x: x[0])
            texts = [text for _, text in sorted_results]
        if texts:
            self.transcript_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.transcript_path, "w", encoding="utf-8") as fh:
                fh.write(" ".join(texts))

    def _stop_active_segments(self) -> None:
        """Stop active segments and queue their audio for transcription."""
        with self._lock:
            active, self._active = list(self._active), []
        for seg in active:
            seg.stop_event.set()
            seg.join(timeout=3)
            if seg.file_path and seg.file_path.exists():
                self._pending_queue.put((seg._started_at, seg.file_path))

    def _shutdown(self, paused: bool = False) -> None:
        """Internal: stop threads and wait for transcription."""
        self._paused = paused
        self._stop_all.set()
        if self._scheduler:
            self._scheduler.join(timeout=2)
        self._stop_active_segments()
        
        # Signal transcriber to stop
        self._pending_queue.put((float('inf'), None))
        
        if self._transcriber_thread:
            self._transcriber_thread.join(timeout=30)
            self._transcriber_thread = None

    def pause(self) -> None:
        if self.running:
            self._shutdown(paused=True)

    def stop(self) -> None:
        """Stop recording and wait for transcriptions."""
        self._shutdown(paused=False)

    def cancel(self) -> None:
        """Cancel recording and discard all pending transcriptions."""
        self._stop_all.set()
        if self._scheduler:
            self._scheduler.join(timeout=2)
        # Stop segments and delete their files
        with self._lock:
            active, self._active = list(self._active), []
        for seg in active:
            seg.stop_event.set()
            seg.join(timeout=2)
            if seg.file_path and seg.file_path.exists():
                seg.file_path.unlink(missing_ok=True)
        # Clear pending queue
        while not self._pending_queue.empty():
            try:
                _, path = self._pending_queue.get_nowait()
                if path:
                    path.unlink(missing_ok=True)
            except queue.Empty:
                break
        
        # Signal transcriber to stop
        self._pending_queue.put((float('inf'), None))
        
        # Stop transcriber
        if self._transcriber_thread:
            self._transcriber_thread.join(timeout=5)
            self._transcriber_thread = None
        with self._results_lock:
            self._results.clear()
        self.clear_transcript()
        self._paused = False

    def _transcribe_single(self, path: Path) -> str:
        """Transcribe audio file with retries."""
        for attempt in range(self.max_retries + 1):
            try:
                return self.llm.transcribe(str(path)) or ""
            except GroqRateLimitError:
                if attempt == self.max_retries:
                    return ""
                time.sleep(5)
            except Exception:
                if attempt == self.max_retries:
                    return ""
                time.sleep(1)
        return ""

    def read_transcript(self) -> str:
        if not self.transcript_path.exists():
            return ""
        return self.transcript_path.read_text(encoding="utf-8")

    def clear_transcript(self) -> None:
        if self.transcript_path.exists():
            self.transcript_path.unlink(missing_ok=True)
