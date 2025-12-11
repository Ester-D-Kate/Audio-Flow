import queue
import sys
import time
import logging
from pathlib import Path

import keyboard
from dotenv import load_dotenv

if __package__ in (None, ""):
    # Allow running as `python terminal_app/main.py` without -m
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from terminal_app.audio import OverlapAudioManager
    from terminal_app.config import load_config
    from terminal_app.inserter import safe_insert
    from terminal_app.llm_client import GroqLLM, GroqRateLimitError
    from terminal_app.ui import WaveformWindow
else:
    from .audio import OverlapAudioManager
    from .config import load_config
    from .inserter import safe_insert
    from .llm_client import GroqLLM, GroqRateLimitError
    from .ui import WaveformWindow


def setup_logging():
    if getattr(sys, 'frozen', False):
        base_path = Path(sys.executable).parent
    else:
        base_path = Path(__file__).resolve().parent.parent
    
    log_path = base_path / "audio_flow.log"
    
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        encoding='utf-8'
    )
    
    # Also log to stdout for development
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logging.getLogger('').addHandler(console)

def ensure_env_loaded() -> None:
    # Determine where to look for .env
    if getattr(sys, 'frozen', False):
        # If running as compiled exe, look in the same folder as the exe
        base_path = Path(sys.executable).parent
    else:
        # If running as script, look in project root
        base_path = Path(__file__).resolve().parent.parent

    env_path = base_path / ".env"
    
    if env_path.exists():
        load_dotenv(env_path)
    else:
        # Fallback to system env vars or bundled .env (if any)
        load_dotenv()


def main() -> None:
    setup_logging()
    logging.info("Application starting...")

    try:
        ensure_env_loaded()

        cfg = load_config()
        hk_start = cfg.get("hotkeys", {}).get("start", "ctrl+shift+l")
        hk_stop = cfg.get("hotkeys", {}).get("stop", "ctrl+alt+s")
        hk_pause = cfg.get("hotkeys", {}).get("pause", "ctrl+shift+space")
        hk_cancel = cfg.get("hotkeys", {}).get("cancel", "ctrl+shift+esc")
        hk_prompt = cfg.get("hotkeys", {}).get("prompt", "ctrl+shift+alt+p")
        max_retries = 3

        amplitude_queue: queue.Queue[float] = queue.Queue()
        transcript_path = Path(__file__).parent / "transcripts.log"
        formatted_log_path = Path(__file__).parent / "formatted.log"

        try:
            llm = GroqLLM()
        except Exception as exc:
            logging.error(f"Groq init failed: {exc}")
            sys.exit(1)

        recorder = OverlapAudioManager(
            llm=llm,
            transcript_path=transcript_path,
            amplitude_queue=amplitude_queue,
            max_retries=max_retries,
        )
        visual = WaveformWindow(
            amplitude_queue,
        )

        status = {"recording": False, "paused": False, "last_formatted": "", "mode": "transcribe"}

        def start_recording(mode: str = "transcribe") -> None:
            if status["recording"] and status["paused"]:
                recorder.resume()
                status["paused"] = False
                visual.update_status("recording" + (" prompt" if status["mode"] == "prompt" else ""))
                logging.info("Resumed recording")
                return
            if status["recording"]:
                logging.info(f"Already recording ({status['mode']})")
                return
            status["mode"] = mode
            # start() clears old files and transcript automatically
            label = "recording" if mode == "transcribe" else "recording prompt"
            visual.update_status(label)
            recorder.start()
            status["recording"] = True
            status["paused"] = False
            logging.info(f"[hotkey] Recording started in {mode} mode ({hk_stop} to stop)")

        def pause_recording() -> None:
            if not status["recording"]:
                logging.info("Not recording; cannot pause")
                return
            if status["paused"]:
                logging.info("Already paused")
                return
            recorder.pause()
            status["paused"] = True
            visual.update_status("paused")
            logging.info("Recording paused")

        def stop_and_process() -> None:
            if not status["recording"]:
                logging.info("Not recording; ignoring stop")
                return
            logging.info("Stopping and processing...")
            visual.update_status("processing")
            # stop() transcribes all audio sequentially, then returns
            recorder.stop()
            status["recording"] = False
            status["paused"] = False
            mode = status.get("mode", "transcribe")
            raw_text = recorder.read_transcript().strip()
            if not raw_text:
                logging.info("No transcript captured")
                visual.update_status("idle")
                status["mode"] = "transcribe"
                return
            try:
                if mode == "prompt":
                    formatted = llm.generate_prompt(raw_text)
                else:
                    formatted = llm.format_text(raw_text)
                status["last_formatted"] = formatted
                with open(formatted_log_path, "a", encoding="utf-8") as fh:
                    fh.write(formatted + "\n\n")
            except GroqRateLimitError:
                logging.warning("All Groq keys are cooling down (rate limited). Please wait ~5 minutes and try again.")
                visual.update_status("idle")
                status["mode"] = "transcribe"
                return
            except Exception as exc:
                msg = str(exc)
                if "network" in msg.lower():
                    logging.error("Network error: please check your connection and try again.")
                else:
                    logging.error(f"LLM formatting failed: {exc}")
                visual.update_status("idle")
                status["mode"] = "transcribe"
                return
            error = safe_insert(formatted)
            if error:
                logging.error(f"Insert failed: {error}")
            else:
                logging.info("Formatted text inserted at cursor")
            visual.update_status("idle")
            status["mode"] = "transcribe"

        def cancel_all() -> None:
            if not status["recording"] and not status["paused"]:
                logging.info("Nothing to cancel")
                return
            recorder.cancel()
            status["recording"] = False
            status["paused"] = False
            status["mode"] = "transcribe"
            visual.update_status("idle")
            logging.info("Recording and pending transcriptions cancelled; transcript cleared.")

        keyboard.add_hotkey(hk_start, start_recording)
        keyboard.add_hotkey(hk_stop, stop_and_process)
        keyboard.add_hotkey(hk_pause, pause_recording)
        keyboard.add_hotkey(hk_cancel, cancel_all)
        keyboard.add_hotkey(hk_prompt, lambda: start_recording("prompt"))

        visual.callbacks.update(
            {
                "start": start_recording,
                "pause": pause_recording,
                "resume": start_recording,
                "stop": stop_and_process,
                "cancel": cancel_all,
                "prompt": lambda: start_recording("prompt"),
            }
        )

        logging.info(
            f"Ready. {hk_start} start/resume (transcription), {hk_prompt} start/resume (prompt mode), {hk_pause} pause, {hk_stop} stop & send, {hk_cancel} cancel."
        )
        
        visual.run()
    except KeyboardInterrupt:
        logging.info("Exiting (KeyboardInterrupt)...")
    except Exception as e:
        logging.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logging.info("Stopping recorder...")
        try:
            recorder.stop()
        except UnboundLocalError:
            pass


if __name__ == "__main__":
    main()