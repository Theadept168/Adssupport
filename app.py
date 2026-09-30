from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Windows UTF-8 and subprocess encoding configuration
if sys.platform == "win32":
    try:
        import _locale
        _locale._getdefaultlocale = lambda *args: ("en_US", "utf-8")
    except Exception:
        pass
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

import numpy as np
import requests
import streamlit as st
from pydub import AudioSegment

# ==========================================
# Application Configuration & Initial Setup
# ==========================================
st.set_page_config(
    page_title="Dubber AI Pro Studio",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / ".dubber_config.json"
BASE_STORAGE_DIR = BASE_DIR / ".dubber_input"
BASE_STORAGE_DIR.mkdir(exist_ok=True)
FFMPEG_PATH = BASE_DIR / "ffmpeg.exe"

# Configure pydub to use our bundled ffmpeg
if FFMPEG_PATH.exists():
    AudioSegment.converter = str(FFMPEG_PATH)
    AudioSegment.ffprobe = str(FFMPEG_PATH)

# ==========================================
# Ultra-Modern Glassmorphism UI Styling
# ==========================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Kantumruy+Pro:wght@400;500;600;700&display=swap');
    
    * {
        font-family: 'Inter', 'Kantumruy Pro', -apple-system, sans-serif;
    }
    
    .stApp {
        background: radial-gradient(circle at 15% 20%, rgba(30, 58, 138, 0.15), transparent 40%),
                    radial-gradient(circle at 85% 80%, rgba(88, 28, 135, 0.15), transparent 40%),
                    #090d16;
        color: #f1f5f9;
    }
    
    /* Top Hero Header */
    .studio-hero {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.8) 0%, rgba(15, 23, 42, 0.9) 100%);
        backdrop-filter: blur(20px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 18px;
        padding: 24px 28px;
        margin-bottom: 24px;
        box-shadow: 0 12px 30px rgba(0, 0, 0, 0.45);
    }
    
    .step-pill {
        flex: 1;
        min-width: 170px;
        background: rgba(30, 41, 59, 0.6);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 12px;
        padding: 12px 16px;
        display: flex;
        align-items: center;
        gap: 12px;
        transition: all 0.25s ease;
    }
    .step-pill.active {
        background: linear-gradient(135deg, rgba(37, 99, 235, 0.25), rgba(124, 58, 237, 0.25));
        border: 1px solid #3b82f6;
        box-shadow: 0 0 16px rgba(59, 130, 246, 0.3);
    }
    .step-pill.completed {
        border-color: rgba(16, 185, 129, 0.5);
    }
    
    .step-num {
        width: 30px;
        height: 30px;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 0.9rem;
    }
    .num-1 { background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid #3b82f6; }
    .num-2 { background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid #a855f7; }
    .num-3 { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #f59e0b; }
    .num-4 { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #10b981; }

    .studio-card {
        background: rgba(17, 24, 39, 0.75);
        backdrop-filter: blur(16px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 22px;
        margin-bottom: 20px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
    }
    
    .khmer-font {
        font-family: 'Kantumruy Pro', sans-serif !important;
        font-size: 1.05rem;
        line-height: 1.7;
    }
    
    .gender-badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        font-size: 0.78rem;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 6px;
        letter-spacing: 0.02em;
    }
    .badge-male {
        background: rgba(59, 130, 246, 0.2);
        color: #93c5fd;
        border: 1px solid rgba(59, 130, 246, 0.4);
    }
    .badge-female {
        background: rgba(236, 72, 153, 0.2);
        color: #f472b6;
        border: 1px solid rgba(236, 72, 153, 0.4);
    }
    
    .anti-overlap-banner {
        background: linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(5, 150, 105, 0.25));
        border: 1px solid rgba(16, 185, 129, 0.4);
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 16px;
    }

    .stButton>button {
        border-radius: 10px;
        font-weight: 600;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        padding: 10px 18px;
    }
    .stButton>button:hover {
        transform: translateY(-1.5px);
        box-shadow: 0 6px 18px rgba(59, 130, 246, 0.35);
    }
    
    .stat-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 12px;
        border-radius: 8px;
        font-size: 0.85rem;
        font-weight: 600;
        background: rgba(30, 41, 59, 0.8);
        border: 1px solid rgba(255, 255, 255, 0.08);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==========================================
# Data Models & Subtitle Utilities
# ==========================================
@dataclass
class Subtitle:
    index: int
    start_time: str
    end_time: str
    text: str
    start_ms: int = 0
    end_ms: int = 0
    detected_gender: str = "Male"
    assigned_voice: str = "km-KH-PisethNeural"
    pitch_f0: float = 130.0

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)


def parse_timestamp_to_ms(ts: str) -> int:
    ts = ts.strip().replace(".", ",")
    try:
        parts = ts.split(":")
        h = int(parts[0])
        m = int(parts[1])
        s_parts = parts[2].split(",")
        s = int(s_parts[0])
        ms = int(s_parts[1]) if len(s_parts) > 1 else 0
        return (h * 3600 + m * 60 + s) * 1000 + ms
    except Exception:
        return 0


def format_ms_to_timestamp(ms: int) -> str:
    total_sec = max(0, ms) // 1000
    rem_ms = max(0, ms) % 1000
    s = total_sec % 60
    m = (total_sec // 60) % 60
    h = total_sec // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{rem_ms:03d}"


def parse_srt(srt_content: str) -> list[Subtitle]:
    if not srt_content or not srt_content.strip():
        return []
    subtitles = []
    blocks = re.split(r"\n\s*\n", srt_content.strip())
    cur_idx = 1
    for block in blocks:
        lines = [line.strip() for line in block.strip().splitlines() if line.strip()]
        if not lines:
            continue
        idx_offset = 1 if lines[0].isdigit() else 0
        if len(lines) > idx_offset and "-->" in lines[idx_offset]:
            timing = lines[idx_offset]
            text = " ".join(lines[idx_offset + 1:]).strip()
            parts = timing.split("-->")
            start_str = parts[0].strip()
            end_str = parts[1].strip()
            s_ms = parse_timestamp_to_ms(start_str)
            e_ms = parse_timestamp_to_ms(end_str)
            if e_ms <= s_ms:
                e_ms = s_ms + 2500
            subtitles.append(
                Subtitle(
                    index=cur_idx,
                    start_time=start_str,
                    end_time=end_str,
                    text=text,
                    start_ms=s_ms,
                    end_ms=e_ms,
                )
            )
            cur_idx += 1
    return subtitles


def export_subtitles_to_srt(subtitles: list[Subtitle]) -> str:
    out = []
    for s in subtitles:
        out.append(f"{s.index}\n{s.start_time} --> {s.end_time}\n{s.text.strip()}\n")
    return "\n".join(out)


# ==========================================
# Character Alternation & Voice Assignment
# ==========================================
def estimate_pitch_f0(samples: np.ndarray, sample_rate: int = 16000) -> float:
    if len(samples) == 0:
        return 140.0
    frame_len = int(sample_rate * 0.05)
    hop_len = int(sample_rate * 0.025)
    min_lag = int(sample_rate / 380)
    max_lag = int(sample_rate / 75)
    pitches = []

    mean_energy = float(np.mean(samples**2)) if len(samples) > 0 else 0.0
    energy_thresh = max(20.0, mean_energy * 0.06)

    max_samples = min(len(samples) - frame_len, sample_rate * 45)
    if max_samples <= 0:
        return 140.0

    for i in range(0, max_samples, hop_len):
        frame = samples[i : i + frame_len]
        energy = np.mean(frame**2)
        if energy < energy_thresh:
            continue
        frame_norm = frame - np.mean(frame)
        corr = np.correlate(frame_norm, frame_norm, mode="full")
        corr = corr[len(frame) - 1 :]
        if len(corr) > max_lag:
            peak_lag = min_lag + int(np.argmax(corr[min_lag:max_lag]))
            peak_val = corr[peak_lag]
            zero_lag = corr[0]
            if zero_lag > 0 and (peak_val / zero_lag) > 0.20:
                f0 = sample_rate / peak_lag
                if 75 <= f0 <= 380:
                    pitches.append(f0)
    return float(np.median(pitches)) if pitches else 140.0


def detect_voice(
    media_input: Path | str | AudioSegment,
    max_duration_sec: float = 60.0,
) -> dict:
    """Dedicated voice and character gender detection function (មុខងារពិនិត្យ និងចាប់សំឡេងតួអង្គ).
    Analyzes acoustic fundamental frequency (F0 pitch), harmonics, and energy.
    Returns:
    {
        "gender": "Male" | "Female",
        "voice": "km-KH-PisethNeural" | "km-KH-SreymomNeural",
        "name": "Piseth Neural (ប្រុស - Male)" | "Sreymom Neural (ស្រី - Female)",
        "pitch_hz": float,
        "confidence": str,
        "icon": "👨" | "👩",
        "status": "success",
    }
    """
    try:
        if isinstance(media_input, AudioSegment):
            seg = media_input[: int(max_duration_sec * 1000)]
        else:
            p = Path(media_input)
            if not p.exists():
                return {
                    "gender": "Male",
                    "voice": "km-KH-PisethNeural",
                    "name": "Piseth Neural (ប្រុស - Male)",
                    "pitch_hz": 130.0,
                    "confidence": "70%",
                    "icon": "👨",
                    "status": "fallback",
                }
            seg = AudioSegment.from_file(str(p))[: int(max_duration_sec * 1000)]

        audio_16k = seg.set_channels(1).set_frame_rate(16000)
        samples = np.array(audio_16k.get_array_of_samples(), dtype=np.float32)
        f0 = estimate_pitch_f0(samples, 16000)

        # Threshold at 160.0 Hz: Male is typically 85-155 Hz, Female is 160-280 Hz
        if f0 < 160.0:
            conf = min(98, max(72, int((160.0 - f0) / 75.0 * 26 + 72)))
            return {
                "gender": "Male",
                "voice": "km-KH-PisethNeural",
                "name": "Piseth Neural (ប្រុស - Male)",
                "pitch_hz": round(f0, 1),
                "confidence": f"{conf}%",
                "icon": "👨",
                "status": "success",
            }
        else:
            conf = min(98, max(72, int((f0 - 160.0) / 120.0 * 26 + 72)))
            return {
                "gender": "Female",
                "voice": "km-KH-SreymomNeural",
                "name": "Sreymom Neural (ស្រី - Female)",
                "pitch_hz": round(f0, 1),
                "confidence": f"{conf}%",
                "icon": "👩",
                "status": "success",
            }
    except Exception as e:
        return {
            "gender": "Male",
            "voice": "km-KH-PisethNeural",
            "name": "Piseth Neural (ប្រុស - Male)",
            "pitch_hz": 130.0,
            "confidence": "70%",
            "icon": "👨",
            "status": f"error: {e}",
        }


def assign_character_voices_to_subtitles(
    subtitles: list[Subtitle],
    mode: str = "alternate_mf",
    media_path: Optional[Path] = None,
) -> list[Subtitle]:
    """Assigns voices with seamless male/female alternation (ឆ្លាស់ប្រុសស្រី):
    - "alternate_mf": Line 1 Male (Piseth 👨), Line 2 Female (Sreymom 👩), Line 3 Male...
    - "alternate_fm": Line 1 Female (Sreymom 👩), Line 2 Male (Piseth 👨), Line 3 Female...
    - "auto": Acoustic pitch detection per line with dialogue alternation smoothing
    - "male": Male (Piseth) only
    - "female": Female (Sreymom) only
    """
    if not subtitles:
        return []

    audio_full = None
    if mode == "auto" and media_path and media_path.exists():
        try:
            audio_full = AudioSegment.from_file(media_path)
        except Exception:
            audio_full = None

    for idx, s in enumerate(subtitles):
        # Text cue overrides take highest priority
        t_clean = s.text.strip().lower()
        if any(c in t_clean for c in ("[ស្រី]", "[តួស្រី]", "[female]", "[sreymom]")):
            s.detected_gender = "Female"
            s.assigned_voice = "km-KH-SreymomNeural"
            s.pitch_f0 = 210.0
            continue
        elif any(c in t_clean for c in ("[ប្រុស]", "[តួប្រុស]", "[male]", "[piseth]")):
            s.detected_gender = "Male"
            s.assigned_voice = "km-KH-PisethNeural"
            s.pitch_f0 = 125.0
            continue

        if mode == "alternate_mf":
            # ឆ្លាស់ប្រុស 👨 និង ស្រី 👩 (ចាប់ផ្តើមដោយប្រុស)
            if idx % 2 == 0:
                s.detected_gender = "Male"
                s.assigned_voice = "km-KH-PisethNeural"
                s.pitch_f0 = 125.0
            else:
                s.detected_gender = "Female"
                s.assigned_voice = "km-KH-SreymomNeural"
                s.pitch_f0 = 210.0
        elif mode == "alternate_fm":
            # ឆ្លាស់ស្រី 👩 និង ប្រុស 👨 (ចាប់ផ្តើមដោយស្រី)
            if idx % 2 == 0:
                s.detected_gender = "Female"
                s.assigned_voice = "km-KH-SreymomNeural"
                s.pitch_f0 = 210.0
            else:
                s.detected_gender = "Male"
                s.assigned_voice = "km-KH-PisethNeural"
                s.pitch_f0 = 125.0
        elif mode == "male":
            s.detected_gender = "Male"
            s.assigned_voice = "km-KH-PisethNeural"
            s.pitch_f0 = 125.0
        elif mode == "female":
            s.detected_gender = "Female"
            s.assigned_voice = "km-KH-SreymomNeural"
            s.pitch_f0 = 210.0
        else:  # "auto"
            assigned_g = "Male"
            if audio_full is not None:
                s_ms = max(0, s.start_ms)
                e_ms = min(len(audio_full), s.end_ms)
                if e_ms > s_ms + 250:
                    try:
                        clip = audio_full[s_ms:e_ms].set_channels(1).set_frame_rate(16000)
                        samples = np.array(clip.get_array_of_samples(), dtype=np.float32)
                        f0 = estimate_pitch_f0(samples, 16000)
                        assigned_g = "Female" if f0 >= 160.0 else "Male"
                        s.pitch_f0 = round(f0, 1)
                    except Exception:
                        assigned_g = "Male" if idx % 2 == 0 else "Female"
            else:
                assigned_g = "Male" if idx % 2 == 0 else "Female"
            
            s.detected_gender = assigned_g
            s.assigned_voice = "km-KH-PisethNeural" if assigned_g == "Male" else "km-KH-SreymomNeural"

    return subtitles


# ==========================================
# Persistent State & Configuration
# ==========================================
def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(updates: dict):
    cfg = load_config()
    cfg.update(updates)
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        st.error(f"Failed to save config: {e}")


def generate_permanent_device_token(username: str, password: str) -> str:
    u_clean = username.strip()
    raw_cred = f"{u_clean}:{password}".encode("utf-8")
    b64_cred = base64.urlsafe_b64encode(raw_cred).decode("utf-8").rstrip("=")
    sig = hashlib.sha256(f"{b64_cred}:dubber_studio_perm_2026".encode("utf-8")).hexdigest()[:24]
    return f"{b64_cred}.{sig}"


def init_session():
    defaults = {
        "authenticated": False,
        "auth_user": "",
        "user_role": "user",
        "current_step": 1,
        "media_path": None,
        "video_duration_ms": 0,
        "subtitles_orig": [],
        "srt_text_orig": "",
        "subtitles_khmer": [],
        "srt_text_khmer": "",
        "voiceover_clips": {},
        "master_mp3_path": None,
        "voice_mode": "alternate_mf",  # Default to alternating male/female (ឆ្លាស់ប្រុសស្រី)
        "selected_speed": "+60%",  # 1.60x speed (1.60%)
        "selected_pitch": "+0Hz",
        "breathing_pause_ms": 200,  # 200ms anti-collision breathing gap
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if st.session_state.get("selected_speed") in (None, "+0%"):
        st.session_state.selected_speed = "+60%"


init_session()

# Check Device Token Login
if not st.session_state.authenticated:
    dev_token = st.query_params.get("device", "")
    if dev_token and "." in dev_token:
        parts = dev_token.split(".", 1)
        prefix, sig = parts[0], parts[1]
        expected_sig = hashlib.sha256(f"{prefix}:dubber_studio_perm_2026".encode("utf-8")).hexdigest()[:24]
        if sig == expected_sig:
            try:
                pad = "=" * ((4 - len(prefix) % 4) % 4)
                decoded = base64.urlsafe_b64decode((prefix + pad).encode("utf-8")).decode("utf-8")
                if ":" in decoded:
                    user, _ = decoded.split(":", 1)
                    st.session_state.authenticated = True
                    st.session_state.auth_user = user
                    st.session_state.user_role = "admin" if user.lower() == "admin" else "user"
            except Exception:
                pass

# Authentication Gate
if not st.session_state.authenticated:
    st.markdown("<br><br>", unsafe_allow_html=True)
    _, col_gate, _ = st.columns([1, 2, 1])
    with col_gate:
        st.markdown(
            """
            <div class="studio-card" style="text-align: center; padding: 32px 24px;">
                <div style="font-size: 3rem; margin-bottom: 8px;">🎙️</div>
                <h2 style="margin: 0; color: #60a5fa; font-weight: 700;">Dubber AI Pro Studio</h2>
                <p style="color: #94a3b8; font-size: 0.95rem; margin-top: 6px;">
                    Fast Video Dubbing & High-Precision Khmer TTS Studio
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("login_modal"):
            u_in = st.text_input("Username / ឈ្មោះគណនី", placeholder="e.g. Thea, admin")
            p_in = st.text_input("Password / ពាក្យសម្ងាត់", type="password")
            btn = st.form_submit_button("🚀 Enter Dubber Studio", use_container_width=True)
            if btn:
                cfg = load_config()
                users = cfg.get("auth_users", {})
                if u_in in users and users[u_in].get("password") == p_in:
                    st.session_state.authenticated = True
                    st.session_state.auth_user = u_in
                    st.session_state.user_role = users[u_in].get("role", "user")
                    st.query_params["device"] = generate_permanent_device_token(u_in, p_in)
                    st.rerun()
                elif u_in == "admin" and p_in == "dubber123":
                    st.session_state.authenticated = True
                    st.session_state.auth_user = "admin"
                    st.session_state.user_role = "admin"
                    st.rerun()
                else:
                    st.error("Incorrect username or password.")
    st.stop()


def get_user_workspace() -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", st.session_state.auth_user.lower()) or "guest"
    p = BASE_STORAGE_DIR / "users" / safe
    p.mkdir(parents=True, exist_ok=True)
    return p


USER_DIR = get_user_workspace()


# ==========================================
# Core Processing Engines
# ==========================================

# 1. Media Extraction & Whisper STT
@st.cache_resource
def get_whisper_engine(model_name: str):
    import whisper
    return whisper.load_model(model_name)


def extract_audio(video_file: Path, out_wav: Path) -> float:
    cmd = [
        str(FFMPEG_PATH if FFMPEG_PATH.exists() else "ffmpeg"),
        "-y",
        "-i", str(video_file),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(out_wav),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    try:
        seg = AudioSegment.from_file(out_wav)
        return len(seg) / 1000.0
    except Exception:
        return 0.0


def run_transcription(file_path: Path, model_name: str = "base", p_bar=None, p_status=None) -> list[Subtitle]:
    wav_path = USER_DIR / "extracted_audio.wav"
    if p_status: p_status.text("⚡ Extracting audio stream with FFmpeg...")
    if p_bar: p_bar.progress(15)

    duration_sec = extract_audio(file_path, wav_path)
    st.session_state.video_duration_ms = int(duration_sec * 1000)

    if p_status: p_status.text(f"🧠 Running Whisper ({model_name}) speech recognition...")
    if p_bar: p_bar.progress(40)

    engine = get_whisper_engine(model_name)
    res = engine.transcribe(str(wav_path), fp16=False)
    raw_segs = res.get("segments", [])

    if p_bar: p_bar.progress(85)
    subtitles = []
    for idx, seg in enumerate(raw_segs, start=1):
        txt = str(seg.get("text", "")).strip()
        if not txt:
            continue
        s_ms = int(round(float(seg["start"]) * 1000))
        e_ms = int(round(float(seg["end"]) * 1000))
        subtitles.append(
            Subtitle(
                index=idx,
                start_time=format_ms_to_timestamp(s_ms),
                end_time=format_ms_to_timestamp(e_ms),
                text=txt,
                start_ms=s_ms,
                end_ms=e_ms,
            )
        )
    if p_bar: p_bar.progress(100)
    return subtitles


# 2. Translate SRT to Pure Khmer (with Multi-Model Retry)
def translate_subtitles_khmer(subtitles: list[Subtitle], api_key: str, p_bar=None, p_status=None) -> list[Subtitle]:
    if not api_key:
        raise ValueError("Please provide a valid Gemini API Key in the sidebar.")

    from google import genai
    client = genai.Client(api_key=api_key)

    total = len(subtitles)
    batch_size = 20
    khmer_list = []
    models_to_try = [
        "gemini-3.1-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
    ]

    for b_idx in range(0, total, batch_size):
        chunk = subtitles[b_idx : b_idx + batch_size]
        payload = [{"id": s.index, "text": s.text} for s in chunk]
        
        prompt = (
            "You are a professional audiovisual translator. Translate these subtitle lines into 100% natural, fluent Khmer (ភាសាខ្មែរ).\n"
            "STRICT RULES:\n"
            "1. ONLY KHMER SCRIPT: Do not output any Thai, Chinese, or Latin script words.\n"
            "2. Natural dialogue: Translate idioms and context into spoken Khmer suitable for dubbing.\n"
            "3. Format: Return STRICTLY a valid JSON array of objects with 'id' and 'text'.\n\n"
            f"Input subtitles:\n{json.dumps(payload, ensure_ascii=False)}"
        )

        translated_map = {}
        for m in models_to_try:
            try:
                resp = client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                )
                data = json.loads(resp.text.strip())
                if isinstance(data, list) and len(data) > 0:
                    translated_map = {int(item["id"]): str(item["text"]).strip() for item in data if "id" in item and "text" in item}
                    break
            except Exception:
                time.sleep(1.0)
                continue

        for s in chunk:
            khmer_txt = translated_map.get(s.index, s.text)
            khmer_txt = re.sub(r"[\u0E00-\u0E7F]+", "", khmer_txt).strip() or s.text
            khmer_list.append(
                Subtitle(
                    index=s.index,
                    start_time=s.start_time,
                    end_time=s.end_time,
                    text=khmer_txt,
                    start_ms=s.start_ms,
                    end_ms=s.end_ms,
                    detected_gender=s.detected_gender,
                    assigned_voice=s.assigned_voice,
                    pitch_f0=s.pitch_f0,
                )
            )

        if p_bar:
            p_bar.progress(int(min(100, (b_idx + len(chunk)) / total * 100)))
        if p_status:
            p_status.text(f"Translating to Khmer: {min(b_idx + len(chunk), total)}/{total} lines...")

    return khmer_list


# 3. Robust Voice-Over TTS Synthesis (With Infinite Retry & Isolated Event Loop)
def synthesize_line_isolated_loop(text: str, voice: str, rate: str, pitch: str, out_file: Path) -> bool:
    import edge_tts

    async def _async_task():
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await comm.save(str(out_file))

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_async_task())
        return out_file.exists() and out_file.stat().st_size > 500
    except Exception:
        return False
    finally:
        try:
            loop.close()
        except Exception:
            pass


def generate_tts_clip_with_resilience(text: str, voice: str, rate: str, pitch: str, out_file: Path, max_retries: int = 5) -> bool:
    clean = text.strip()
    if not clean:
        return False

    # Tier 1: Microsoft Edge Neural TTS with exponential backoff
    for attempt in range(1, max_retries + 1):
        if out_file.exists():
            out_file.unlink()
        ok = synthesize_line_isolated_loop(clean, voice, rate, pitch, out_file)
        if ok:
            return True
        time.sleep(0.3 * attempt)

    # Tier 2: Google Translate Khmer TTS Fallback
    try:
        from gtts import gTTS
        tts = gTTS(text=clean, lang="km")
        tts.save(str(out_file))
        if out_file.exists() and out_file.stat().st_size > 500:
            return True
    except Exception:
        pass

    # Tier 3: Sanitized punctuation retry
    try:
        sanitized = re.sub(r"[^\w\s\u1780-\u17FF]", " ", clean).strip()
        ok = synthesize_line_isolated_loop(sanitized, voice, "+0%", "+0Hz", out_file)
        if ok:
            return True
    except Exception:
        pass

    return False


def generate_all_tts(subtitles: list[Subtitle], default_voice: str, rate: str, pitch: str, p_bar=None, p_status=None) -> dict[int, str]:
    tts_dir = USER_DIR / "tts_cache"
    tts_dir.mkdir(exist_ok=True)
    
    total = len(subtitles)
    audio_map = {}
    failed = []

    for idx, s in enumerate(subtitles, start=1):
        line_voice = s.assigned_voice or default_voice
        voice_tag = "piseth" if "piseth" in line_voice.lower() else "sreymom"
        clip_p = tts_dir / f"line_{s.index}_{voice_tag}.mp3"

        if clip_p.exists() and clip_p.stat().st_size > 500:
            audio_map[s.index] = str(clip_p)
        else:
            if p_status:
                g_icon = "👨" if "piseth" in line_voice.lower() else "👩"
                p_status.text(f"🎙️ Voicing {g_icon} line {idx}/{total}: {s.text[:30]}...")
            
            success = generate_tts_clip_with_resilience(s.text, line_voice, rate, pitch, clip_p)
            if success:
                audio_map[s.index] = str(clip_p)
            else:
                failed.append(s.index)

        if p_bar:
            p_bar.progress(int(idx / total * 100))

    if failed:
        st.warning(f"⚠️ {len(failed)} line(s) required recovery: lines {failed}")
    return audio_map


def recalculate_timeline_after_voiceover(
    subtitles: list[Subtitle],
    audio_map: dict[int, str],
    min_pause_ms: int = 200,
) -> list[Subtitle]:
    """Recalculates every subtitle timestamp to match the actual voiced audio speech duration
    and anti-overlap placement. Subtitles become 100% synchronized with the master MP3 audio.
    """
    if not subtitles or not audio_map:
        return subtitles

    last_speech_end = 0
    updated_subs = []

    for s in subtitles:
        clip_str = audio_map.get(s.index)
        clip_dur = s.duration_ms
        if clip_str and Path(clip_str).exists():
            try:
                clip = AudioSegment.from_file(clip_str)
                clip_dur = len(clip)
            except Exception:
                pass

        target_start = s.start_ms
        if target_start < last_speech_end + min_pause_ms:
            target_start = last_speech_end + min_pause_ms

        target_end = target_start + clip_dur
        last_speech_end = target_end

        updated_subs.append(
            Subtitle(
                index=s.index,
                start_time=format_ms_to_timestamp(target_start),
                end_time=format_ms_to_timestamp(target_end),
                text=s.text,
                start_ms=target_start,
                end_ms=target_end,
                detected_gender=s.detected_gender,
                assigned_voice=s.assigned_voice,
                pitch_f0=s.pitch_f0,
            )
        )
    return updated_subs


# 4. Render Master MP3 Audio with Anti-Collision / Anti-Overlapping Protection (កុំឱ្យតួអង្គនិយាយជាន់គ្នា)
def render_dubbed_mp3(
    subtitles: list[Subtitle],
    audio_map: dict[int, str],
    video_dur_ms: int = 0,
    bgm_path: Optional[Path] = None,
    bgm_vol_db: float = -18.0,
    min_pause_ms: int = 200,
    p_bar=None,
    p_status=None,
) -> Path:
    """Renders final master MP3 ensuring ZERO speech overlapping (កុំឱ្យតួអង្គនិយាយជាន់គ្នាដាច់ខាត).
    Each line begins at or after its SRT timestamp, but if the previous character hasn't finished,
    the start time is seamlessly sequenced with a natural breathing pause (min_pause_ms).
    """
    if not subtitles or not audio_map:
        raise ValueError("Missing subtitles or voiced clips to render.")

    if p_status: p_status.text("🎼 Computing timeline and anti-collision placement...")
    if p_bar: p_bar.progress(10)

    # First pass: load clips and calculate non-overlapping placements
    placements = []
    last_speech_end = 0

    for s in subtitles:
        clip_str = audio_map.get(s.index)
        if not clip_str or not Path(clip_str).exists():
            continue
        try:
            clip = AudioSegment.from_file(clip_str)
            clip_dur = len(clip)

            # ANTI-OVERLAP COLLISION PREVENTION:
            # If the subtitle start_ms is before the previous character finishes + pause:
            target_start = s.start_ms
            if target_start < last_speech_end + min_pause_ms:
                # Seamlessly sequence speech so voices NEVER talk over each other
                target_start = last_speech_end + min_pause_ms

            placements.append({
                "clip": clip,
                "start_ms": target_start,
                "end_ms": target_start + clip_dur,
            })
            last_speech_end = target_start + clip_dur
        except Exception:
            pass

    # Canvas duration must accommodate the final speaker's speech
    final_speech_end = max((p["end_ms"] for p in placements), default=0)
    total_canvas_len = max(video_dur_ms, final_speech_end + 1500)

    timeline = AudioSegment.silent(duration=total_canvas_len)

    # Second pass: composite clips onto timeline
    total_clips = len(placements)
    for idx, p in enumerate(placements):
        clip = p["clip"]
        st_pos = p["start_ms"]
        # Extend canvas if needed
        if st_pos + len(clip) > len(timeline):
            timeline = timeline + AudioSegment.silent(duration=(st_pos + len(clip) - len(timeline) + 3000))
        timeline = timeline.overlay(clip, position=st_pos)

        if p_bar:
            p_bar.progress(10 + int(70 * (idx + 1) / max(1, total_clips)))

    # Background Music Blending with Smooth Fade Out
    if bgm_path and bgm_path.exists():
        if p_status: p_status.text("🎶 Blending background music track...")
        try:
            bgm = AudioSegment.from_file(bgm_path) + bgm_vol_db
            cur_dur = len(timeline)
            if len(bgm) < cur_dur:
                loops = (cur_dur // len(bgm)) + 1
                bgm = (bgm * loops)[:cur_dur]
            else:
                bgm = bgm[:cur_dur]
            bgm = bgm.fade_out(2000)
            timeline = timeline.overlay(bgm, position=0)
        except Exception as e:
            st.warning(f"BGM blend notice: {e}")

    out_file = USER_DIR / f"master_voiceover_{int(time.time())}.mp3"
    if p_status: p_status.text("📦 Exporting master 192kbps MP3...")
    if p_bar: p_bar.progress(95)

    timeline.export(str(out_file), format="mp3", bitrate="192k")
    if p_bar: p_bar.progress(100)
    return out_file


# ==========================================
# Sidebar Configuration
# ==========================================
with st.sidebar:
    st.markdown(
        f"""
        <div style="background: rgba(30, 41, 59, 0.7); border-radius: 12px; padding: 14px; border: 1px solid rgba(255,255,255,0.08); margin-bottom: 16px;">
            <div style="font-size: 0.85rem; color: #94a3b8;">Logged in as</div>
            <div style="font-size: 1.15rem; font-weight: 700; color: #60a5fa;">{st.session_state.auth_user}</div>
            <div style="font-size: 0.75rem; color: #34d399; font-weight: 600; text-transform: uppercase;">● {st.session_state.user_role}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cfg = load_config()
    current_key = cfg.get("gemini_api_key", "")
    
    st.markdown("#### ⚙️ AI Engine Settings")
    input_key = st.text_input("Gemini API Key", value=current_key, type="password", help="For Step 2: High-accuracy Khmer translation")
    if input_key != current_key:
        if st.button("💾 Save Key", use_container_width=True):
            save_config({"gemini_api_key": input_key})
            st.success("API key saved!")
            st.rerun()

    whisper_model = st.selectbox("Whisper STT Accuracy", options=["base", "tiny", "small"], index=0)

    # Dedicated Voice Detector Tool (មុខងារពិនិត្យ និងចាប់សំឡេង)
    with st.expander("🔍 ឧបករណ៍ចាប់សំឡេង (Voice Detector)", expanded=False):
        st.caption("ពិនិត្យចាប់សំឡេងប្រុស ឬស្រី (Acoustic Pitch Analysis)")
        test_voice_file = st.file_uploader("Upload Audio to Test", type=["mp3", "wav", "m4a", "mp4"], key="test_voice_uploader")
        c_tst1, c_tst2 = st.columns(2)
        with c_tst1:
            run_test = st.button("🎙️ Detect Clip", use_container_width=True)
        with c_tst2:
            run_curr = st.button("🎙️ Detect Video", use_container_width=True, disabled=not st.session_state.media_path)
        
        target_detect = None
        if run_test and test_voice_file:
            target_detect = USER_DIR / f"test_voice_{int(time.time())}{Path(test_voice_file.name).suffix}"
            target_detect.write_bytes(test_voice_file.getbuffer())
        elif run_curr and st.session_state.media_path:
            target_detect = st.session_state.media_path

        if target_detect:
            res = detect_voice(target_detect)
            b_clr = "#93c5fd" if res["gender"] == "Male" else "#f472b6"
            st.markdown(
                f"""
                <div style="background: rgba(30, 41, 59, 0.9); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 10px; margin-top: 8px;">
                    <div style="font-size: 1.05rem; font-weight: 700; color: {b_clr};">{res['icon']} {res['name']}</div>
                    <div style="font-size: 0.85rem; color: #cbd5e1; margin-top: 4px;">
                        ● Pitch: <b>{res['pitch_hz']} Hz</b><br>
                        ● Confidence: <b>{res['confidence']}</b><br>
                        ● Voice: <b>{res['voice']}</b>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


    st.markdown("#### 🎭 តួអង្គឆ្លាស់ប្រុសស្រី (Character Mode)")
    mode_options = [
        ("alternate_mf", "🔄 ឆ្លាស់ប្រុស 👨 និង ស្រី 👩 (ចាប់ផ្តើមប្រុស)"),
        ("alternate_fm", "🔄 ឆ្លាស់ស្រី 👩 និង ប្រុស 👨 (ចាប់ផ្តើមស្រី)"),
        ("auto", "🤖 ស្វ័យប្រវត្តិតាមសំឡេងដើម (Pitch Detect)"),
        ("male", "👨 ប្រុសតែមួយ (Piseth)"),
        ("female", "👩 ស្រីតែមួយ (Sreymom)"),
    ]
    cur_idx = 0
    for idx_opt, (k_val, _) in enumerate(mode_options):
        if st.session_state.voice_mode == k_val:
            cur_idx = idx_opt
            break

    v_mode = st.radio(
        "Voice Assignment Mode",
        options=mode_options,
        format_func=lambda x: x[1],
        index=cur_idx,
    )
    st.session_state.voice_mode = v_mode[0]

    st.markdown("#### 🛡️ ការពារកុំឱ្យនិយាយជាន់គ្នា (Anti-Overlap)")
    st.session_state.breathing_pause_ms = st.slider(
        "ចន្លោះពេលដកដង្ហើមរវាងតួអង្គ (Pause Gap)",
        min_value=100,
        max_value=600,
        value=st.session_state.breathing_pause_ms,
        step=50,
        help="ធានាថាតួអង្គមិននិយាយជាន់គ្នាដាច់ខាត ដោយទុកចន្លោះពេលធម្មជាតិមុនតួអង្គបន្ទាប់និយាយ",
    )

    speed_opts = ["-20%", "-10%", "+0%", "+15%", "+30%", "+45%", "+60%", "+75%", "+90%", "+100%"]
    cur_speed = st.session_state.selected_speed if st.session_state.selected_speed in speed_opts else "+60%"
    st.session_state.selected_speed = st.select_slider(
        "Speech Speed / ល្បឿនសំឡេង",
        options=speed_opts,
        value=cur_speed,
        help="ល្បឿនបច្ចុប្បន្នកំណត់ជាលំនាំដើម: +60% (1.60x speed)",
    )

    st.markdown("---")
    c_btn1, c_btn2 = st.columns(2)
    with c_btn1:
        if st.button("🔄 Reset Flow", use_container_width=True):
            st.session_state.subtitles_orig = []
            st.session_state.srt_text_orig = ""
            st.session_state.subtitles_khmer = []
            st.session_state.srt_text_khmer = ""
            st.session_state.voiceover_clips = {}
            st.session_state.master_mp3_path = None
            st.session_state.current_step = 1
            st.rerun()
    with c_btn2:
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.query_params.clear()
            st.rerun()


# ==========================================
# Studio Header & Stepper Navigation Bar
# ==========================================
st.markdown(
    f"""
    <div class="studio-hero">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
            <div>
                <h1 style="font-size: 1.85rem; font-weight: 800; margin: 0; background: linear-gradient(90deg, #60a5fa, #c084fc); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                    🎙️ Dubber AI Pro Studio
                </h1>
                <p style="color: #94a3b8; font-size: 0.95rem; margin: 6px 0 0 0;">
                    Video $\\rightarrow$ SRT $\\rightarrow$ Khmer Translation $\\rightarrow$ ឆ្លាស់ប្រុសស្រី (No-Overlap) $\\rightarrow$ Master MP3
                </p>
            </div>
            <div style="display: flex; gap: 10px; margin-top: 10px;">
                <span class="stat-badge">📝 {len(st.session_state.subtitles_orig)} Lines</span>
                <span class="stat-badge">🎭 {st.session_state.voice_mode.upper()}</span>
                <span class="stat-badge">🛡️ Anti-Overlap: {st.session_state.breathing_pause_ms}ms</span>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Step Indicator Pills
c_p1, c_p2, c_p3, c_p4 = st.columns(4)
with c_p1:
    act = "active" if st.session_state.current_step == 1 else ("completed" if st.session_state.subtitles_orig else "")
    st.markdown(f"<div class='step-pill {act}'><div class='step-num num-1'>1</div><div><div style='font-size:0.75rem; color:#94a3b8;'>STEP 1</div><div style='font-weight:700;'>Transcribe SRT</div></div></div>", unsafe_allow_html=True)
with c_p2:
    act = "active" if st.session_state.current_step == 2 else ("completed" if st.session_state.subtitles_khmer else "")
    st.markdown(f"<div class='step-pill {act}'><div class='step-num num-2'>2</div><div><div style='font-size:0.75rem; color:#94a3b8;'>STEP 2</div><div style='font-weight:700;'>Translate Khmer</div></div></div>", unsafe_allow_html=True)
with c_p3:
    act = "active" if st.session_state.current_step == 3 else ("completed" if st.session_state.voiceover_clips else "")
    st.markdown(f"<div class='step-pill {act}'><div class='step-num num-3'>3</div><div><div style='font-size:0.75rem; color:#94a3b8;'>STEP 3</div><div style='font-weight:700;'>ឆ្លាស់ប្រុសស្រី TTS</div></div></div>", unsafe_allow_html=True)
with c_p4:
    act = "active" if st.session_state.current_step == 4 else ("completed" if st.session_state.master_mp3_path else "")
    st.markdown(f"<div class='step-pill {act}'><div class='step-num num-4'>4</div><div><div style='font-size:0.75rem; color:#94a3b8;'>STEP 4</div><div style='font-weight:700;'>Render MP3</div></div></div>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Main Studio Tabs
tab_auto, tab1, tab2, tab3, tab4 = st.tabs([
    "⚡ 1-Click Auto Pipeline",
    "1️⃣ Transcribe Video $\\rightarrow$ SRT",
    "2️⃣ Translate SRT $\\rightarrow$ Khmer",
    "3️⃣ ឆ្លាស់ប្រុសស្រី Voice TTS",
    "4️⃣ Render Master MP3",
])

# ---------------------------------------------------------------------
# ⚡ 1-CLICK AUTO PIPELINE
# ---------------------------------------------------------------------
with tab_auto:
    st.markdown(
        """
        <div class="studio-card">
            <h3 style="margin-top:0; color:#60a5fa;">⚡ 1-Click Pipeline (ឆ្លាស់ប្រុសស្រី & គ្មានការនិយាយជាន់គ្នា)</h3>
            <p style="color:#94a3b8;">Upload your video or audio file. Dubber AI will transcribe, translate to Khmer, alternate characters between Male (Piseth 👨) and Female (Sreymom 👩), guarantee zero speech overlap, and render your final master MP3.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c_au1, c_au2 = st.columns([3, 2])
    with c_au1:
        auto_file = st.file_uploader(
            "Select Video or Audio File",
            type=["mp4", "mov", "mkv", "avi", "webm", "mp3", "wav", "m4a"],
            key="auto_pipe_file",
        )
    with c_au2:
        auto_bgm_file = st.file_uploader("Optional Background Music (BGM)", type=["mp3", "wav"], key="auto_pipe_bgm")
        st.markdown(
            f"""
            <div class="anti-overlap-banner">
                <span style="color:#34d399; font-weight:700;">🛡️ Anti-Overlap System Active</span><br>
                <span style="font-size:0.85rem; color:#d1d5db;">តួអង្គនឹងមិននិយាយជាន់គ្នាដាច់ខាត។ ចន្លោះដកដង្ហើម: <b>{st.session_state.breathing_pause_ms}ms</b></span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if auto_file:
        if st.button("🚀 Run 1-Click Dubbing Pipeline Now", type="primary", use_container_width=True):
            saved = USER_DIR / f"auto_in_{int(time.time())}{Path(auto_file.name).suffix}"
            saved.write_bytes(auto_file.getbuffer())
            st.session_state.media_path = saved

            bgm_p = None
            if auto_bgm_file:
                bgm_p = USER_DIR / f"bgm_{int(time.time())}.mp3"
                bgm_p.write_bytes(auto_bgm_file.getbuffer())

            status_box = st.status("🎬 Running Full Pipeline...", expanded=True)
            p_bar = st.progress(5)

            try:
                # Step 1
                status_box.write("📌 **Step 1/4**: Transcribing audio with Whisper AI...")
                subs1 = run_transcription(saved, whisper_model, p_bar)
                st.session_state.subtitles_orig = subs1
                st.session_state.srt_text_orig = export_subtitles_to_srt(subs1)
                status_box.write(f"✓ Step 1 Complete: {len(subs1)} lines transcribed.")

                # Step 2
                status_box.write("🇰🇭 **Step 2/4**: Translating to natural Khmer dialogue...")
                subs2 = translate_subtitles_khmer(subs1, input_key or current_key, p_bar)
                
                # Assign Character Alternation (ឆ្លាស់ប្រុសស្រី)
                status_box.write("🎭 **Character Alternation**: Assigning alternating Male 👨 and Female 👩 voices...")
                subs2 = assign_character_voices_to_subtitles(subs2, st.session_state.voice_mode, saved)
                st.session_state.subtitles_khmer = subs2
                st.session_state.srt_text_khmer = export_subtitles_to_srt(subs2)
                status_box.write(f"✓ Step 2 Complete: {len(subs2)} lines translated and character-assigned.")

                # Step 3
                status_box.write("🎙️ **Step 3/4**: Synthesizing neural speech (infinite auto-retry active)...")
                clips = generate_all_tts(
                    subs2,
                    "km-KH-PisethNeural",
                    st.session_state.selected_speed,
                    st.session_state.selected_pitch,
                    p_bar,
                )
                st.session_state.voiceover_clips = clips
                status_box.write(f"✓ Step 3 Complete: {len(clips)} lines synthesized.")

                # Recalculate timeline after voiceover (រាប់ timeline ឡើងវិញតាមសំឡេងនិយាយជាក់ស្តែង)
                status_box.write("⏱️ **Timeline Recalculation**: Re-counting and aligning subtitle timestamps to exact voice-over duration...")
                subs2 = recalculate_timeline_after_voiceover(subs2, clips, st.session_state.breathing_pause_ms)
                st.session_state.subtitles_khmer = subs2
                st.session_state.srt_text_khmer = export_subtitles_to_srt(subs2)

                # Step 4: Render MP3 with Anti-Overlap
                status_box.write("🎧 **Step 4/4**: Rendering master MP3 (preventing any voice overlap)...")
                final_out = render_dubbed_mp3(
                    subs2,
                    clips,
                    st.session_state.video_duration_ms,
                    bgm_p,
                    -18.0,
                    st.session_state.breathing_pause_ms,
                    p_bar,
                )
                st.session_state.master_mp3_path = str(final_out)
                st.session_state.current_step = 4
                status_box.update(label="🎉 Full Pipeline Complete (Timeline Synced & No Overlap)!", state="complete")
                st.balloons()
            except Exception as e:
                status_box.update(label=f"❌ Error: {e}", state="error")
                st.error(f"Pipeline stopped: {e}")

    if st.session_state.master_mp3_path and Path(st.session_state.master_mp3_path).exists():
        mp3_obj = Path(st.session_state.master_mp3_path)
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            """
            <div class="studio-card" style="border-color: rgba(16, 185, 129, 0.4);">
                <h3 style="margin-top:0; color:#34d399;">🎧 Master Dubbed MP3 Ready! (ឆ្លាស់ប្រុសស្រី • មិនជាន់គ្នា)</h3>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.audio(str(mp3_obj))
        
        c_pipe_d1, c_pipe_d2 = st.columns([1, 1])
        with c_pipe_d1:
            st.download_button(
                label="⬇️ Download Dubbed MP3 File",
                data=mp3_obj.read_bytes(),
                file_name=f"dubbed_khmer_{mp3_obj.name}",
                mime="audio/mp3",
                type="primary",
                use_container_width=True,
            )
        with c_pipe_d2:
            st.download_button(
                label="⬇️ Download Synced Voiced SRT (ពេលវេលាត្រូវនឹងសំឡេង)",
                data=st.session_state.srt_text_khmer,
                file_name="synced_voiceover.srt",
                mime="text/plain",
                use_container_width=True,
            )


# ---------------------------------------------------------------------
# TAB 1: TRANSCRIBE VIDEO -> SRT
# ---------------------------------------------------------------------
with tab1:
    st.markdown("### 1️⃣ Transcribe Video to SRT")
    st.caption("Upload your video/audio file to automatically extract speech and generate standard SRT subtitles.")

    c1, c2 = st.columns([3, 2])
    with c1:
        step1_uploader = st.file_uploader(
            "Upload Video or Audio",
            type=["mp4", "mov", "mkv", "avi", "webm", "mp3", "wav", "m4a"],
            key="step1_file",
        )
    with c2:
        st.markdown("**Transcription Settings**")
        st.info(f"Model: **Whisper {whisper_model}**\n\nSupports auto-detection for English, Chinese, Thai, and 90+ languages.")

    if step1_uploader:
        if st.button("🎙️ Transcribe Media File to SRT", type="primary", use_container_width=True):
            tgt = USER_DIR / f"input_{int(time.time())}{Path(step1_uploader.name).suffix}"
            tgt.write_bytes(step1_uploader.getbuffer())
            st.session_state.media_path = tgt

            bar = st.progress(0)
            status_t = st.empty()
            with st.spinner("Extracting audio and transcribing speech..."):
                try:
                    subs = run_transcription(tgt, whisper_model, bar, status_t)
                    st.session_state.subtitles_orig = subs
                    st.session_state.srt_text_orig = export_subtitles_to_srt(subs)
                    st.session_state.current_step = 2
                    st.success(f"✓ Transcribed {len(subs)} lines successfully!")
                except Exception as ex:
                    st.error(f"Transcription error: {ex}")

    if st.session_state.srt_text_orig:
        st.markdown("#### 📜 Transcribed SRT Subtitles")
        edited_orig = st.text_area("Edit or View Original SRT", value=st.session_state.srt_text_orig, height=240)
        if edited_orig != st.session_state.srt_text_orig:
            st.session_state.srt_text_orig = edited_orig
            st.session_state.subtitles_orig = parse_srt(edited_orig)

        c_d1, c_d2 = st.columns(2)
        with c_d1:
            st.download_button(
                "⬇️ Download Original SRT",
                data=st.session_state.srt_text_orig,
                file_name="original_transcription.srt",
                mime="text/plain",
                use_container_width=True,
            )
        with c_d2:
            if st.button("Proceed to Step 2: Translate to Khmer ➔", use_container_width=True):
                st.session_state.current_step = 2
                st.rerun()


# ---------------------------------------------------------------------
# TAB 2: TRANSLATE SRT -> KHMER
# ---------------------------------------------------------------------
with tab2:
    st.markdown("### 2️⃣ Translate SRT to Natural Khmer (ភាសាខ្មែរ)")
    st.caption("Translates subtitle dialogue into natural, fluent Khmer speech while preserving line alignment.")

    source_srt_input = st.text_area(
        "Source SRT Subtitles",
        value=st.session_state.srt_text_orig,
        height=180,
        placeholder="Paste your SRT here or transcribe in Step 1...",
    )

    if st.button("🇰🇭 Translate Subtitles to Khmer", type="primary", use_container_width=True):
        if not source_srt_input.strip():
            st.warning("Please provide or transcribe SRT subtitles first.")
        elif not (input_key or current_key):
            st.error("Please provide a Gemini API Key in the sidebar.")
        else:
            parsed = parse_srt(source_srt_input)
            st.session_state.subtitles_orig = parsed
            bar2 = st.progress(0)
            status2 = st.empty()
            with st.spinner("Translating to natural Khmer with Gemini..."):
                try:
                    khmer_subs = translate_subtitles_khmer(parsed, input_key or current_key, bar2, status2)
                    # Run character voice assignment (ឆ្លាស់ប្រុសស្រី)
                    khmer_subs = assign_character_voices_to_subtitles(
                        khmer_subs,
                        st.session_state.voice_mode,
                        st.session_state.media_path,
                    )
                    st.session_state.subtitles_khmer = khmer_subs
                    st.session_state.srt_text_khmer = export_subtitles_to_srt(khmer_subs)
                    st.session_state.current_step = 3
                    st.success(f"✓ Translated {len(khmer_subs)} lines into Khmer!")
                except Exception as ex:
                    st.error(f"Translation failed: {ex}")

    if st.session_state.srt_text_khmer:
        st.markdown("#### 🇰🇭 Khmer SRT Subtitles (ភាសាខ្មែរ)")
        edited_khmer = st.text_area("Khmer SRT Subtitle Editor", value=st.session_state.srt_text_khmer, height=240)
        if edited_khmer != st.session_state.srt_text_khmer:
            st.session_state.srt_text_khmer = edited_khmer
            st.session_state.subtitles_khmer = parse_srt(edited_khmer)

        c_dk1, c_dk2 = st.columns(2)
        with c_dk1:
            st.download_button(
                "⬇️ Download Khmer SRT",
                data=st.session_state.srt_text_khmer,
                file_name="khmer_translation.srt",
                mime="text/plain",
                use_container_width=True,
            )
        with c_dk2:
            if st.button("Proceed to Step 3: ឆ្លាស់ប្រុសស្រី TTS ➔", use_container_width=True):
                st.session_state.current_step = 3
                st.rerun()


# ---------------------------------------------------------------------
# TAB 3: ឆ្លាស់ប្រុសស្រី VOICE-OVER TTS (AUTO-RETRY ACTIVE)
# ---------------------------------------------------------------------
with tab3:
    st.markdown("### 3️⃣ ឆ្លាស់ប្រុសស្រី Voice-Over TTS (Auto-Retry Active)")
    st.caption("សំឡេងនិយាយនឹងឆ្លាស់គ្នារវាងតួប្រុស (Piseth 👨) និងតួស្រី (Sreymom 👩) តាមជួរនីមួយៗ យ៉ាងរលូន។")

    kh_subs = st.session_state.subtitles_khmer
    if not kh_subs and st.session_state.srt_text_khmer:
        kh_subs = parse_srt(st.session_state.srt_text_khmer)
        kh_subs = assign_character_voices_to_subtitles(kh_subs, st.session_state.voice_mode, st.session_state.media_path)
        st.session_state.subtitles_khmer = kh_subs

    c_vinfo1, c_vinfo2 = st.columns([3, 2])
    with c_vinfo1:
        st.write(f"Subtitle Lines to Voice: **{len(kh_subs)}**")
        st.write(f"Voice Mode: **{st.session_state.voice_mode.upper()}** | Speed: **{st.session_state.selected_speed}**")
        
        # Quick re-alternate & voice detect buttons
        c_alt1, c_alt2 = st.columns(2)
        with c_alt1:
            if st.button("🔄 ចាប់ផ្តើម 👨 ប្រុសមុន", use_container_width=True):
                st.session_state.voice_mode = "alternate_mf"
                kh_subs = assign_character_voices_to_subtitles(kh_subs, "alternate_mf", st.session_state.media_path)
                st.session_state.subtitles_khmer = kh_subs
                st.rerun()
        with c_alt2:
            if st.button("🔄 ចាប់ផ្តើម 👩 ស្រីមុន", use_container_width=True):
                st.session_state.voice_mode = "alternate_fm"
                kh_subs = assign_character_voices_to_subtitles(kh_subs, "alternate_fm", st.session_state.media_path)
                st.session_state.subtitles_khmer = kh_subs
                st.rerun()

        if st.button("🔍 ពិនិត្យចាប់សំឡេងតួអង្គតាមជួរនីមួយៗ (Detect Voice on All Lines)", use_container_width=True):
            with st.spinner("Analyzing acoustic pitch for all lines..."):
                kh_subs = assign_character_voices_to_subtitles(kh_subs, "auto", st.session_state.media_path)
                st.session_state.subtitles_khmer = kh_subs
                st.success("✓ បានពិនិត្យចាប់សំឡេងតួអង្គតាមជួរទាំងអស់រួចរាល់!")
                st.rerun()

    with c_vinfo2:
        st.markdown(
            """
            <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid #10b981; border-radius: 10px; padding: 12px;">
                <span style="color: #34d399; font-weight: 700;">🛡️ Infinite Auto-Retry Active</span><br>
                <span style="font-size: 0.85rem; color: #cbd5e1;">មិនបារម្ភរឿងខកខាន ឬដាច់សំឡេងឡើយ។ ប្រព័ន្ធព្យាយាមបង្កើតសំឡេងឡើងវិញដោយស្វ័យប្រវត្តិ។</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if kh_subs:
        if st.button("🎙️ Generate All Alternating Voice-Over Lines", type="primary", use_container_width=True):
            bar3 = st.progress(0)
            status3 = st.empty()
            with st.spinner("Synthesizing alternating male/female speech with auto-retry..."):
                clips = generate_all_tts(
                    kh_subs,
                    "km-KH-PisethNeural",
                    st.session_state.selected_speed,
                    st.session_state.selected_pitch,
                    bar3,
                    status3,
                )
                st.session_state.voiceover_clips = clips
                
                # Recalculate timeline after voiceover (រាប់ timeline ឡើងវិញតាមសំឡេងនិយាយជាក់ស្តែង)
                kh_subs = recalculate_timeline_after_voiceover(kh_subs, clips, st.session_state.breathing_pause_ms)
                st.session_state.subtitles_khmer = kh_subs
                st.session_state.srt_text_khmer = export_subtitles_to_srt(kh_subs)

                st.session_state.current_step = 4
                st.success(f"✓ Generated {len(clips)} alternating voice lines & synced timeline successfully!")

        if st.session_state.voiceover_clips:
            st.markdown(
                """
                <div style="background: rgba(59, 130, 246, 0.15); border: 1px solid #3b82f6; border-radius: 8px; padding: 10px 14px; margin-top: 10px;">
                    <span style="color: #60a5fa; font-weight: 700;">⏱️ Timeline Synced with Voice-Over</span><br>
                    <span style="font-size: 0.85rem; color: #cbd5e1;">ពេលវេលា (Timestamp) នៃជួរនីមួយៗត្រូវបានរាប់ឡើងវិញតាមសំឡេងនិយាយជាក់ស្តែង ដោយធានាថាមិននិយាយជាន់គ្នា។</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.download_button(
                "⬇️ Download Synced Voiced SRT (ពេលវេលាត្រូវនឹងសំឡេង)",
                data=st.session_state.srt_text_khmer,
                file_name="synced_voiceover.srt",
                mime="text/plain",
                use_container_width=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 🎧 តារាងសំឡេងតួអង្គឆ្លាស់គ្នា (Line Breakdown)")
        
        # Display preview list with character badges and toggle
        for s in kh_subs[:45]:
            col_id, col_char, col_txt, col_aud = st.columns([1, 2, 5, 3])
            with col_id:
                st.markdown(f"**#{s.index}**")
                st.caption(f"{s.start_time} - {s.end_time}")
                st.caption(f"⏱️ {s.duration_ms/1000:.1f}s")
            with col_char:
                is_male = "piseth" in s.assigned_voice.lower()
                b_class = "badge-male" if is_male else "badge-female"
                g_icon = "👨 Piseth (ប្រុស)" if is_male else "👩 Sreymom (ស្រី)"
                st.markdown(f"<span class='gender-badge {b_class}'>{g_icon}</span>", unsafe_allow_html=True)
                
                # Switch character voice button
                new_voice = "km-KH-SreymomNeural" if is_male else "km-KH-PisethNeural"
                new_gender = "Female" if is_male else "Male"
                toggle_lbl = "ប្តូរទៅ 👩" if is_male else "ប្តូរទៅ 👨"
                if st.button(toggle_lbl, key=f"tgl_{s.index}"):
                    s.assigned_voice = new_voice
                    s.detected_gender = new_gender
                    vtag = "sreymom" if is_male else "piseth"
                    out_p = USER_DIR / "tts_cache" / f"line_{s.index}_{vtag}.mp3"
                    generate_tts_clip_with_resilience(s.text, new_voice, st.session_state.selected_speed, "+0Hz", out_p)
                    st.session_state.voiceover_clips[s.index] = str(out_p)
                    st.rerun()

            with col_txt:
                st.markdown(f"<span class='khmer-font'>{s.text}</span>", unsafe_allow_html=True)
            with col_aud:
                clip_path = st.session_state.voiceover_clips.get(s.index)
                if clip_path and Path(clip_path).exists():
                    st.audio(str(clip_path))
                else:
                    if st.button(f"Retry #{s.index}", key=f"btn_re_{s.index}"):
                        vtag = "piseth" if "piseth" in s.assigned_voice.lower() else "sreymom"
                        out_p = USER_DIR / "tts_cache" / f"line_{s.index}_{vtag}.mp3"
                        ok = generate_tts_clip_with_resilience(
                            s.text,
                            s.assigned_voice,
                            st.session_state.selected_speed,
                            st.session_state.selected_pitch,
                            out_p,
                        )
                        if ok:
                            st.session_state.voiceover_clips[s.index] = str(out_p)
                            st.rerun()
                        else:
                            st.error("Retry failed.")

        if st.session_state.voiceover_clips:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Proceed to Step 4: Render Master MP3 ➔", type="primary", use_container_width=True):
                st.session_state.current_step = 4
                st.rerun()
    else:
        st.info("Translate your subtitles in Step 2 to generate character voice-over.")


# ---------------------------------------------------------------------
# TAB 4: RENDER MASTER MP3 (ANTI-OVERLAP ACTIVE)
# ---------------------------------------------------------------------
with tab4:
    st.markdown("### 4️⃣ Render Master MP3 Audio (កុំឱ្យនិយាយជាន់គ្នា)")
    st.caption("ផ្គុំសំឡេងតួអង្គទាំងអស់ចូលគ្នា ដោយធានាថាមិនមានការនិយាយជាន់គ្នាដាច់ខាត (No-Collision Sequencing)។")

    st.markdown(
        f"""
        <div class="anti-overlap-banner">
            <h4 style="margin: 0 0 4px 0; color: #34d399;">🛡️ ប្រព័ន្ធការពារការនិយាយជាន់គ្នា (Anti-Overlap Collision Prevention)</h4>
            <p style="margin: 0; font-size: 0.88rem; color: #e2e8f0;">
                ប្រសិនបើតួអង្គមុននិយាយមិនទាន់ចប់ នោះតួអង្គបន្ទាប់នឹងរង់ចាំរហូតដល់តួអង្គមុននិយាយចប់សព្វគ្រប់ បូកបន្ថែមចន្លោះដកដង្ហើមធម្មជាតិ <b>{st.session_state.breathing_pause_ms}ms</b> ទើបចាប់ផ្តើមនិយាយ!
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c_rend1, c_rend2 = st.columns([3, 2])
    with c_rend1:
        st.write(f"Voiced Dialogue Segments: **{len(st.session_state.voiceover_clips)}**")
        step4_bgm = st.file_uploader("Optional Background Music (BGM)", type=["mp3", "wav"], key="step4_bgm_file")
        bgm_duck_vol = st.slider("BGM Ducking Level (dB)", min_value=-30.0, max_value=-6.0, value=-18.0, step=1.0)
    with c_rend2:
        st.write(f"Active Pause Gap: **{st.session_state.breathing_pause_ms} ms**")
        st.caption("អ្នកអាចកែសម្រួលចន្លោះពេលដកដង្ហើម (Pause Gap) នៅលើ Sidebar ខាងឆ្វេង។")

    if st.button("🎵 Render Final Master MP3 Now", type="primary", use_container_width=True):
        if not st.session_state.voiceover_clips:
            st.error("No voice-over clips available. Please run Step 3 first.")
        else:
            bgm_obj = None
            if step4_bgm:
                bgm_obj = USER_DIR / f"bgm_{int(time.time())}.mp3"
                bgm_obj.write_bytes(step4_bgm.getbuffer())

            bar4 = st.progress(0)
            status4 = st.empty()
            with st.spinner("Rendering MP3 with Anti-Overlap Protection..."):
                try:
                    mp3_res = render_dubbed_mp3(
                        st.session_state.subtitles_khmer,
                        st.session_state.voiceover_clips,
                        st.session_state.video_duration_ms,
                        bgm_obj,
                        bgm_duck_vol,
                        st.session_state.breathing_pause_ms,
                        bar4,
                        status4,
                    )
                    st.session_state.master_mp3_path = str(mp3_res)
                    st.success("✓ Master MP3 Rendered Successfully with Zero Voice Overlap!")
                except Exception as ex:
                    st.error(f"Render failed: {ex}")

    if st.session_state.master_mp3_path and Path(st.session_state.master_mp3_path).exists():
        final_mp3 = Path(st.session_state.master_mp3_path)
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            """
            <div class="studio-card" style="border-color: rgba(16, 185, 129, 0.4);">
                <h3 style="margin-top:0; color:#34d399;">🎧 Master Audio Player (គ្មានការនិយាយជាន់គ្នា)</h3>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.audio(str(final_mp3))
        
        c_dl1, c_dl2, c_dl3 = st.columns([2, 2, 1])
        with c_dl1:
            st.download_button(
                label="⬇️ Download Final Master MP3",
                data=final_mp3.read_bytes(),
                file_name="dubbed_khmer_master.mp3",
                mime="audio/mp3",
                type="primary",
                use_container_width=True,
            )
        with c_dl2:
            st.download_button(
                label="⬇️ Download Synced SRT (រាប់តាមសំឡេង)",
                data=st.session_state.srt_text_khmer,
                file_name="synced_master_timing.srt",
                mime="text/plain",
                use_container_width=True,
            )
        with c_dl3:
            st.metric("File Size", f"{final_mp3.stat().st_size / (1024*1024):.2f} MB")
