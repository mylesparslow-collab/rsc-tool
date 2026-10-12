"""Speech to text, on this computer. Nothing is sent to the internet after the one-time model download.

Uses faster-whisper (installed by the installer as the "voice" extra). The browser records, posts the clip to
/voice, and the words come back to go into whatever box the person was talking to.
"""
import importlib.util
import tempfile
import threading
from pathlib import Path

PROMPT = ("Kitchen remodel, bathroom, addition, deck, sheetrock, framing, joists, rough-in, quartz countertops, "
          "cabinets, Home Depot, Lowe's, Saratoga Springs, Wilton, Ballston Spa, change order, estimate.")

_lock = threading.Lock()
_loaded: dict[str, object] = {}


class VoiceUnavailable(RuntimeError):
    pass


def available() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


def is_downloaded(model_name: str, cache_dir: Path) -> bool:
    return any(cache_dir.glob(f"models--*faster-whisper-{model_name}/snapshots/*/model.bin"))


def load(model_name: str, cache_dir: Path):
    """Load (downloading the first time) and keep the model in memory."""
    if not available():
        raise VoiceUnavailable("Voice typing isn't installed. Run ./deploy/install.sh again, or: pip install faster-whisper")
    with _lock:
        if model_name not in _loaded:
            from faster_whisper import WhisperModel
            cache_dir.mkdir(parents=True, exist_ok=True)
            _loaded[model_name] = WhisperModel(model_name, device="cpu", compute_type="int8", download_root=str(cache_dir))
        return _loaded[model_name]


def transcribe(audio: bytes, model_name: str, cache_dir: Path, suffix: str = ".webm") -> str:
    model = load(model_name, cache_dir)
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(audio)
        tmp.flush()
        segments, _info = model.transcribe(tmp.name, language="en", beam_size=1, initial_prompt=PROMPT,
                                           condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segments).strip()
