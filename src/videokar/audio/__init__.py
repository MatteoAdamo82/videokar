"""Audio: decoding, vocal separation, and where the singing is."""

from .io import AudioInfo, decode_to_wav, probe, read_wav
from .separate import Separation, separate_vocals
from .vad import Region, detect_vocal_regions

__all__ = [
    "AudioInfo",
    "Region",
    "Separation",
    "decode_to_wav",
    "detect_vocal_regions",
    "probe",
    "read_wav",
    "separate_vocals",
]
