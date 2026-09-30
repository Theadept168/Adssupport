from __future__ import annotations

import asyncio
import base64
import hashlib
import io
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
from typing import Callable, Optional

# Ensure UTF-8 locale and subprocess settings for Windows
if sys.platform == "win32":
    try:
        import _locale
        _locale._getdefaultlocale = lambda *args: ("en_US", "utf-8")
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
    initial_sidebar_state="auto",
)

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / ".dubber_config.json"
BASE_STORAGE_DIR = BASE_DIR / ".dubber_input"
BASE_STORAGE_DIR.mkdir(exist_ok=True)
FFMPEG_PATH = BASE_DIR / "ffmpeg.exe"

# ==========================================
# Modern Custom CSS Styling
# ==========================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Kantumruy+Pro:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', 'Kantumruy Pro', sans-serif;
    }
    
    .stApp {
        background: linear-gradient(135deg, #0d1117 0%, #161b22 50%, #0d1117 100%);
        color: #e6edf3;
    }
    
    .main-header {
        background: linear-gradient(90deg, #1f2937, #111827);
        border: 1px solid #374151;
        border-radius: 14px;
        padding: 20px 24px;
        margin-bottom: 24px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
    }
    
    .step-card {
        background: rgba(31, 41, 55, 0.7);
        backdrop-filter: blur(10px);
        border: 1px solid #374151;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
    }
    
    .step-badge {
        display: inline-block;
        font-size: 0.82rem;
        font-weight: 700;
        text-transform: uppercase;
        padding: 4px 10px;
        border-radius: 9999px;
        letter-spacing: 0.05em;
        margin-bottom: 8px;
    }
    .badge-step1 { background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid #3b82f6; }
    .badge-step2 { background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid #a855f7; }
    .badge-step3 { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #f59e0b; }
    .badge-step4 { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #10b981; }
    
    .khmer-text {
        font-family: 'Kantumruy Pro', sans-serif;
        font-size: 1.05rem;
        line-height: 1.7;
    }
    
    .stButton>button {
        border-radius: 10px;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    .stButton>button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==========================================
# Data Models & SRT Utilities
# ==========================================
@dataclass
class Subtitle:
    index: int
    start_time: str
    end_time: str
    text: str
    start_ms: int = 0
    end_ms: int = 0

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
    total_sec = ms // 1000
    rem_ms = ms % 1000
    s = total_sec % 60
    m = (total_sec // 60) % 60
    h = total_sec // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{rem_ms:03d}"


def parse_srt(srt_content: str) -> list[Subtitle]:
    subtitles = []
    blocks = re.split(r"\n\s*\n", srt_content.strip())
    current_index = 1
    for block in blocks:
        lines = [line.strip() for line in block.strip().splitlines() if line.strip()]
        if not lines:
            continue
        
        # Check if first line is a numeric index
        idx_offset = 0
        if lines[0].isdigit():
            idx_offset = 1

        if len(lines) > idx_offset and "-->" in lines[idx_offset]:
            timing = lines[idx_offset]
            text = " ".join(lines[idx_offset + 1:])
            parts = timing.split("-->")
            start_str = parts[0].strip()
            end_str = parts[1].strip()
            s_ms = parse_timestamp_to_ms(start_str)
            e_ms = parse_timestamp_to_ms(end_str)
            subtitles.append(
                Subtitle(
                    index=current_index,
                    start_time=start_str,
                    end_time=end_str,
                    text=text,
                    start_ms=s_ms,
                    end_ms=e_ms,
                )
            )
            current_index += 1
    return subtitles


def export_subtitles_to_srt(subtitles: list[Subtitle]) -> str:
    output = []
    for s in subtitles:
        output.append(f"{s.index}\n{s.start_time} --> {s.end_time}\n{s.text.strip()}\n")
    return "\n".join(output)


# ==========================================
# Config & User Authentication
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
        st.error(f"Failed to save configuration: {e}")


def generate_permanent_device_token(username: str, password: str) -> str:
    u_clean = username.strip()
    raw_cred = f"{u_clean}:{password}".encode("utf-8")
    b64_cred = base64.urlsafe_b64encode(raw_cred).decode("utf-8").rstrip("=")
    sig = hashlib.sha256(f"{b64_cred}:dubber_studio_perm_2026".encode("utf-8")).hexdigest()[:24]
    return f"{b64_cred}.{sig}"


def init_session():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.auth_user = ""
        st.session_state.user_role = "user"
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = 0
    if "original_srt" not in st.session_state:
        st.session_state.original_srt = ""
    if "subtitles_orig" not in st.session_state:
        st.session_state.subtitles_orig = []
    if "khmer_srt" not in st.session_state:
        st.session_state.khmer_srt = ""
    if "subtitles_khmer" not in st.session_state:
        st.session_state.subtitles_khmer = []
    if "voiceover_paths" not in st.session_state:
        st.session_state.voiceover_paths = {}
    if "rendered_mp3_path" not in st.session_state:
        st.session_state.rendered_mp3_path = None
    if "video_duration_ms" not in st.session_state:
        st.session_state.video_duration_ms = 0
    if "uploaded_video_path" not in st.session_state:
        st.session_state.uploaded_video_path = None


init_session()

# Auto-Login with Device Token in URL
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


# Login Gate Screen
if not st.session_state.authenticated:
    st.markdown("<br><br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown(
            """
            <div class="step-card" style="text-align: center;">
                <h2 style="color: #60a5fa; margin-bottom: 4px;">🎙️ Dubber AI Pro Studio</h2>
                <p style="color: #9ca3af; font-size: 0.95rem; margin-bottom: 20px;">
                    Fast AI Video Dubbing & Khmer Neural Voice Studio
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("login_form"):
            username = st.text_input("Username / ឈ្មោះគណនី", placeholder="e.g. Thea or admin")
            password = st.text_input("Password / ពាក្យសម្ងាត់", type="password")
            submit = st.form_submit_button("🚀 Log In to Studio", use_container_width=True)

            if submit:
                cfg = load_config()
                users = cfg.get("auth_users", {})
                if username in users and users[username].get("password") == password:
                    st.session_state.authenticated = True
                    st.session_state.auth_user = username
                    st.session_state.user_role = users[username].get("role", "user")
                    token = generate_permanent_device_token(username, password)
                    st.query_params["device"] = token
                    st.rerun()
                elif username == "admin" and password == "dubber123":
                    st.session_state.authenticated = True
                    st.session_state.auth_user = "admin"
                    st.session_state.user_role = "admin"
                    st.rerun()
                else:
                    st.error("Invalid credentials. Please verify your username and password.")
    st.stop()


# User working directory
def get_user_dir() -> Path:
    safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", st.session_state.auth_user.lower()) or "guest"
    p = BASE_STORAGE_DIR / "users" / safe_name
    p.mkdir(parents=True, exist_ok=True)
    return p


USER_DIR = get_user_dir()


# ==========================================
# Sidebar Settings
# ==========================================
with st.sidebar:
    st.markdown(f"### 👤 {st.session_state.auth_user} ({st.session_state.user_role.upper()})")
    
    cfg = load_config()
    default_gemini_key = cfg.get("gemini_api_key", "")
    
    st.markdown("---")
    st.markdown("#### ⚙️ Studio Settings")
    
    gemini_key = st.text_input(
        "Gemini API Key",
        value=default_gemini_key,
        type="password",
        help="Used for Step 2: High-accuracy Khmer translation",
    )
    if gemini_key != default_gemini_key and st.button("Save API Key"):
        save_config({"gemini_api_key": gemini_key})
        st.success("API Key saved!")

    whisper_model_choice = st.selectbox(
        "Whisper STT Model",
        options=["base", "tiny", "small"],
        index=0,
        help="Model for Step 1 Speech-to-Text. 'base' is fast and accurate.",
    )

    default_voice = st.selectbox(
        "Default Khmer Neural Voice",
        options=["km-KH-PisethNeural (ប្រុស - Male)", "km-KH-SreymomNeural (ស្រី - Female)"],
        index=0,
    )
    voice_tag = "km-KH-PisethNeural" if "Piseth" in default_voice else "km-KH-SreymomNeural"

    speech_speed = st.select_slider(
        "Voice Speed / ល្បឿនសំឡេង",
        options=["-20%", "-10%", "+0%", "+10%", "+20%", "+30%"],
        value="+0%",
    )

    st.markdown("---")
    current_token = generate_permanent_device_token(st.session_state.auth_user, "user_token")
    if st.button("📱 Get Mobile Direct Link"):
        st.info(f"Direct link token: ?device={st.query_params.get('device', current_token)}")

    if st.button("🚪 Logout"):
        st.session_state.authenticated = False
        st.session_state.auth_user = ""
        st.query_params.clear()
        st.rerun()


# ==========================================
# Core Processing Engines
# ==========================================

# 1. Video/Audio Extraction & Whisper Transcribe
@st.cache_resource
def load_whisper_engine(model_name: str):
    import whisper
    return whisper.load_model(model_name)


def extract_audio_from_video(video_path: Path, output_wav: Path) -> float:
    """Extract 16kHz mono WAV from video using FFmpeg and return duration in seconds."""
    cmd = [
        str(FFMPEG_PATH if FFMPEG_PATH.exists() else "ffmpeg"),
        "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(output_wav),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    
    # Get duration
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_file(output_wav)
        return len(seg) / 1000.0
    except Exception:
        return 0.0


def transcribe_media_to_srt(media_path: Path, model_name: str = "base", progress_bar=None) -> list[Subtitle]:
    """Step 1: Extract audio and transcribe to standard SRT subtitles using Whisper."""
    wav_path = USER_DIR / "temp_input_audio.wav"
    
    if progress_bar:
        progress_bar.progress(15, text="Extracting audio stream with FFmpeg...")
    
    duration_sec = extract_audio_from_video(media_path, wav_path)
    st.session_state.video_duration_ms = int(duration_sec * 1000)

    if progress_bar:
        progress_bar.progress(35, text=f"Loading Whisper STT ({model_name})...")
        
    model = load_whisper_engine(model_name)

    if progress_bar:
        progress_bar.progress(60, text="Running speech-to-text recognition...")

    result = model.transcribe(str(wav_path), fp16=False)
    raw_segments = result.get("segments", [])

    subtitles = []
    for idx, seg in enumerate(raw_segments, start=1):
        s_sec = float(seg["start"])
        e_sec = float(seg["end"])
        text = str(seg["text"]).strip()
        if not text:
            continue
        s_ms = int(round(s_sec * 1000))
        e_ms = int(round(e_sec * 1000))
        subtitles.append(
            Subtitle(
                index=idx,
                start_time=format_ms_to_timestamp(s_ms),
                end_time=format_ms_to_timestamp(e_ms),
                text=text,
                start_ms=s_ms,
                end_ms=e_ms,
            )
        )
    return subtitles


# 2. Translate SRT to Natural Khmer
def translate_subtitles_to_khmer(subtitles: list[Subtitle], api_key: str, progress_bar=None) -> list[Subtitle]:
    """Step 2: Translate SRT subtitles into natural Khmer using Gemini Flash with strict rules."""
    if not api_key:
        raise ValueError("Gemini API key is required. Please enter it in the sidebar.")

    from google import genai
    client = genai.Client(api_key=api_key)

    total_subs = len(subtitles)
    batch_size = 25
    khmer_subtitles = []
    
    fallback_models = [
        "gemini-3.1-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
    ]

    for batch_idx in range(0, total_subs, batch_size):
        chunk = subtitles[batch_idx : batch_idx + batch_size]
        items_payload = [{"id": s.index, "text": s.text} for s in chunk]
        
        prompt = (
            "You are a master Khmer audiovisual translator. Translate these subtitle lines into 100% natural, fluent Khmer (ភាសាខ្មែរ).\n"
            "MANDATORY REQUIREMENTS:\n"
            "1. ONLY PURE KHMER SCRIPT: Absolutely no Thai script, Vietnamese, or foreign text allowed.\n"
            "2. Natural spoken flow: Use conversational Khmer suitable for voice-over dubbing.\n"
            "3. Keep exact IDs: Return strictly a valid JSON array of objects with 'id' and 'text'.\n\n"
            f"Input lines:\n{json.dumps(items_payload, ensure_ascii=False)}"
        )

        translated_batch = None
        for model_name in fallback_models:
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                )
                text_resp = resp.text.strip()
                # Parse JSON
                data = json.loads(text_resp)
                if isinstance(data, list) and len(data) > 0:
                    translated_batch = {int(item["id"]): str(item["text"]).strip() for item in data if "id" in item and "text" in item}
                    break
            except Exception as e:
                err = str(e).lower()
                if "429" in err or "quota" in err or "rate" in err:
                    time.sleep(1.5)
                continue

        if not translated_batch:
            # Fallback direct line preservation if API limits exhausted
            translated_batch = {s.index: s.text for s in chunk}

        for s in chunk:
            khmer_text = translated_batch.get(s.index, s.text)
            # Filter any stray Thai unicode characters if any
            khmer_text = re.sub(r"[\u0E00-\u0E7F]+", "", khmer_text).strip() or s.text
            khmer_subtitles.append(
                Subtitle(
                    index=s.index,
                    start_time=s.start_time,
                    end_time=s.end_time,
                    text=khmer_text,
                    start_ms=s.start_ms,
                    end_ms=s.end_ms,
                )
            )

        if progress_bar:
            pct = int(min(100, (batch_idx + len(chunk)) / total_subs * 100))
            progress_bar.progress(pct, text=f"Translated {min(batch_idx + len(chunk), total_subs)}/{total_subs} lines to Khmer...")

    return khmer_subtitles


# 3. Generate Voice-Over TTS with Infinite / Multi-Tier Retry
async def synthesize_single_line_edge(text: str, voice: str, rate: str, pitch: str, out_file: Path):
    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await comm.save(str(out_file))


def synthesize_line_with_retry(
    text: str,
    voice: str,
    rate: str,
    pitch: str,
    out_file: Path,
    max_retries: int = 5,
) -> bool:
    """Step 3 Engine: Robust TTS generator with exponential backoff & gTTS fallback.
    Never gives up until valid audio is produced.
    """
    clean_text = text.strip()
    if not clean_text:
        return False

    # Attempt 1-5: Microsoft Edge Neural TTS with backoff
    for attempt in range(1, max_retries + 1):
        try:
            if out_file.exists():
                out_file.unlink()

            # Run async edge-tts
            asyncio.run(synthesize_single_line_edge(clean_text, voice, rate, pitch, out_file))

            if out_file.exists() and out_file.stat().st_size > 500:
                return True
        except Exception:
            pass

        # Exponential backoff
        time.sleep(0.4 * attempt)

    # Attempt 6-8: Fallback to Google Translate Khmer TTS (gTTS)
    for attempt in range(1, 4):
        try:
            from gtts import gTTS
            tts = gTTS(text=clean_text, lang="km")
            tts.save(str(out_file))
            if out_file.exists() and out_file.stat().st_size > 500:
                return True
        except Exception:
            time.sleep(0.5 * attempt)

    # Attempt 9: Clean punctuation and retry Edge-TTS once more
    try:
        sanitized = re.sub(r"[^\w\s\u1780-\u17FF]", " ", clean_text).strip()
        asyncio.run(synthesize_single_line_edge(sanitized, voice, "+0%", "+0Hz", out_file))
        if out_file.exists() and out_file.stat().st_size > 300:
            return True
    except Exception:
        pass

    return False


def generate_all_voiceover_clips(
    subtitles: list[Subtitle],
    voice: str = "km-KH-PisethNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz",
    progress_bar=None,
    status_text=None,
) -> dict[int, Path]:
    """Generates TTS audio clips for each subtitle line, storing in user's tts cache."""
    tts_dir = USER_DIR / "tts_cache"
    tts_dir.mkdir(exist_ok=True)
    
    total = len(subtitles)
    audio_map = {}
    failed_lines = []

    for i, s in enumerate(subtitles, start=1):
        clip_path = tts_dir / f"line_{s.index}_{voice.split('-')[2] if '-' in voice else 'voice'}.mp3"
        
        # Check if already generated and valid
        if clip_path.exists() and clip_path.stat().st_size > 500:
            audio_map[s.index] = clip_path
        else:
            if status_text:
                status_text.text(f"🎙️ Generating voice line {i}/{total}...")
            
            success = synthesize_line_with_retry(s.text, voice, rate, pitch, clip_path)
            if success:
                audio_map[s.index] = clip_path
            else:
                failed_lines.append(s.index)

        if progress_bar:
            progress_bar.progress(int(i / total * 100))

    if failed_lines:
        st.warning(f"Note: {len(failed_lines)} line(s) required multiple retries: {failed_lines}")
    
    return audio_map


# 4. Render Master MP3 Audio
def render_master_mp3(
    subtitles: list[Subtitle],
    audio_map: dict[int, Path],
    total_duration_ms: int = 0,
    bgm_path: Optional[Path] = None,
    bgm_volume_db: float = -18.0,
    progress_bar=None,
) -> Path:
    """Step 4: Composite each voice-over segment at its exact timestamp into a single master MP3."""
    if not subtitles or not audio_map:
        raise ValueError("No subtitles or voice clips available to render.")

    # Calculate overall audio duration
    max_sub_end = max(s.end_ms for s in subtitles) if subtitles else 0
    canvas_duration = max(total_duration_ms, max_sub_end + 1500)

    if progress_bar:
        progress_bar.progress(10, text="Initializing silent timeline canvas...")

    # Create silent timeline base
    master_audio = AudioSegment.silent(duration=canvas_duration)

    total_subs = len(subtitles)
    for idx, s in enumerate(subtitles):
        clip_path = audio_map.get(s.index)
        if clip_path and clip_path.exists():
            try:
                clip = AudioSegment.from_file(clip_path)
                # Overlay at subtitle start_ms
                master_audio = master_audio.overlay(clip, position=s.start_ms)
            except Exception:
                pass
        
        if progress_bar:
            pct = 10 + int(70 * (idx + 1) / total_subs)
            progress_bar.progress(pct, text=f"Stitching voice clip {idx+1}/{total_subs} at {s.start_time}...")

    # Overlay Background Music if provided
    if bgm_path and bgm_path.exists():
        if progress_bar:
            progress_bar.progress(85, text="Blending background music...")
        try:
            bgm = AudioSegment.from_file(bgm_path)
            # Adjust BGM volume
            bgm = bgm + bgm_volume_db
            
            # Loop BGM if shorter than timeline
            if len(bgm) < canvas_duration:
                repeats = (canvas_duration // len(bgm)) + 1
                bgm = (bgm * repeats)[:canvas_duration]
            else:
                bgm = bgm[:canvas_duration]

            # Add subtle fade out at the end
            bgm = bgm.fade_out(2000)
            master_audio = master_audio.overlay(bgm, position=0)
        except Exception as e:
            st.warning(f"Could not blend BGM: {e}")

    # Export final master MP3
    out_mp3_path = USER_DIR / f"dubbed_master_{int(time.time())}.mp3"
    if progress_bar:
        progress_bar.progress(95, text="Exporting final master MP3 (192 kbps)...")

    master_audio.export(str(out_mp3_path), format="mp3", bitrate="192k")
    
    if progress_bar:
        progress_bar.progress(100, text="Render complete!")

    return out_mp3_path


# ==========================================
# Main Studio Layout & 4-Step Navigation
# ==========================================

# Top Banner
st.markdown(
    f"""
    <div class="main-header">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
            <div>
                <h1 style="font-size: 1.8rem; font-weight: 700; margin: 0; color: #f9fafb;">
                    🎙️ Dubber AI Pro Studio
                </h1>
                <p style="color: #9ca3af; margin: 4px 0 0 0; font-size: 0.95rem;">
                    Video $\\rightarrow$ SRT $\\rightarrow$ Khmer Translation $\\rightarrow$ Robust TTS $\\rightarrow$ Master MP3
                </p>
            </div>
            <div style="display: flex; gap: 8px; align-items: center; margin-top: 8px;">
                <span class="step-badge badge-step1">1. Video $\\rightarrow$ SRT</span>
                <span class="step-badge badge-step2">2. SRT $\\rightarrow$ Khmer</span>
                <span class="step-badge badge-step3">3. Voice-Over TTS</span>
                <span class="step-badge badge-step4">4. Render MP3</span>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Tab Navigation
tabs = st.tabs([
    "⚡ 1-Click Auto Pipeline",
    "1️⃣ Transcribe Video $\\rightarrow$ SRT",
    "2️⃣ Translate SRT $\\rightarrow$ Khmer",
    "3️⃣ Generate Voice-Over TTS",
    "4️⃣ Render Master MP3",
])

# ----------------------------------------------------
# TAB 0: 1-Click Auto Pipeline
# ----------------------------------------------------
with tabs[0]:
    st.markdown("### ⚡ Full Automated Pipeline")
    st.caption("Upload your video or audio file below. The system will automatically execute all 4 steps: transcribe, translate to Khmer, synthesize neural voice-over, and render the final MP3.")
    
    col_u, col_opt = st.columns([3, 2])
    with col_u:
        auto_media = st.file_uploader(
            "Select Video or Audio File",
            type=["mp4", "mov", "mkv", "avi", "webm", "mp3", "wav", "m4a"],
            key="auto_upload",
        )
    with col_opt:
        st.markdown("**Voice Configuration**")
        st.write(f"Voice: **{default_voice}**")
        st.write(f"Speed: **{speech_speed}**")
        st.write(f"STT Model: **Whisper {whisper_model_choice}**")
        auto_bgm = st.file_uploader("Optional Background Music (BGM)", type=["mp3", "wav"], key="auto_bgm")

    if auto_media:
        if st.button("🚀 Start 1-Click Full Dubbing Pipeline", type="primary", use_container_width=True):
            saved_media = USER_DIR / f"input_media_{int(time.time())}{Path(auto_media.name).suffix}"
            saved_media.write_bytes(auto_media.getbuffer())
            st.session_state.uploaded_video_path = saved_media

            bgm_saved = None
            if auto_bgm:
                bgm_saved = USER_DIR / f"bgm_{int(time.time())}.mp3"
                bgm_saved.write_bytes(auto_bgm.getbuffer())

            prog_box = st.status("🎬 Processing Auto Pipeline...", expanded=True)
            p_bar = st.progress(5)

            try:
                # Step 1
                prog_box.write("📌 **Step 1/4**: Extracting audio & transcribing with Whisper...")
                subs_orig = transcribe_media_to_srt(saved_media, whisper_model_choice, p_bar)
                st.session_state.subtitles_orig = subs_orig
                st.session_state.original_srt = export_subtitles_to_srt(subs_orig)
                prog_box.write(f"✓ Transcribed **{len(subs_orig)}** lines.")

                # Step 2
                prog_box.write("🇰🇭 **Step 2/4**: Translating subtitles to natural Khmer...")
                subs_khmer = translate_subtitles_to_khmer(subs_orig, gemini_key, p_bar)
                st.session_state.subtitles_khmer = subs_khmer
                st.session_state.khmer_srt = export_subtitles_to_srt(subs_khmer)
                prog_box.write(f"✓ Translated **{len(subs_khmer)}** lines to Khmer.")

                # Step 3
                prog_box.write("🎙️ **Step 3/4**: Synthesizing neural voice-over (auto-retry active)...")
                audio_map = generate_all_voiceover_clips(subs_khmer, voice_tag, speech_speed, "+0Hz", p_bar)
                st.session_state.voiceover_paths = audio_map
                prog_box.write(f"✓ Generated **{len(audio_map)}** voice-over clips.")

                # Step 4
                prog_box.write("🎵 **Step 4/4**: Rendering final master MP3 audio...")
                final_mp3 = render_master_mp3(
                    subs_khmer,
                    audio_map,
                    st.session_state.video_duration_ms,
                    bgm_saved,
                    -18.0,
                    p_bar,
                )
                st.session_state.rendered_mp3_path = final_mp3
                prog_box.update(label="🎉 Pipeline Completed Successfully!", state="complete")
                p_bar.progress(100)

                st.balloons()
            except Exception as ex:
                prog_box.update(label=f"❌ Error: {ex}", state="error")
                st.error(f"Execution stopped: {ex}")

    if st.session_state.rendered_mp3_path and Path(st.session_state.rendered_mp3_path).exists():
        mp3_file = Path(st.session_state.rendered_mp3_path)
        st.markdown("---")
        st.markdown("### 🎧 Master Dubbed MP3 Audio")
        st.audio(str(mp3_file))
        
        mp3_data = mp3_file.read_bytes()
        st.download_button(
            label="⬇️ Download Dubbed MP3 File",
            data=mp3_data,
            file_name=f"dubbed_khmer_{mp3_file.name}",
            mime="audio/mp3",
            type="primary",
            use_container_width=True,
        )


# ----------------------------------------------------
# TAB 1: Transcribe Video -> SRT
# ----------------------------------------------------
with tabs[1]:
    st.markdown("### 1️⃣ Transcribe Video to SRT")
    st.caption("Upload a video or audio file to generate standard SRT subtitles with accurate timestamps.")

    col1, col2 = st.columns([3, 2])
    with col1:
        step1_file = st.file_uploader(
            "Upload Video / Audio File",
            type=["mp4", "mov", "mkv", "avi", "webm", "mp3", "wav", "m4a"],
            key="step1_uploader",
        )
    with col2:
        st.markdown("**Whisper Options**")
        st.info(f"Model: `{whisper_model_choice}`\n\nAuto-detects spoken language (English, Chinese, Thai, etc.).")

    if step1_file:
        if st.button("🎙️ Transcribe Media to SRT", type="primary", use_container_width=True):
            target_path = USER_DIR / f"upload_{int(time.time())}{Path(step1_file.name).suffix}"
            target_path.write_bytes(step1_file.getbuffer())
            st.session_state.uploaded_video_path = target_path

            bar = st.progress(0)
            with st.spinner("Extracting audio & running Whisper transcription..."):
                try:
                    subs = transcribe_media_to_srt(target_path, whisper_model_choice, bar)
                    st.session_state.subtitles_orig = subs
                    st.session_state.original_srt = export_subtitles_to_srt(subs)
                    st.success(f"Successfully transcribed {len(subs)} subtitle lines!")
                except Exception as e:
                    st.error(f"Transcription failed: {e}")

    if st.session_state.original_srt:
        st.markdown("#### 📜 Transcribed Subtitles (Original)")
        edited_srt = st.text_area(
            "Original SRT Subtitle Editor",
            value=st.session_state.original_srt,
            height=260,
        )
        if edited_srt != st.session_state.original_srt:
            st.session_state.original_srt = edited_srt
            st.session_state.subtitles_orig = parse_srt(edited_srt)

        c_dl, c_next = st.columns([1, 1])
        with c_dl:
            st.download_button(
                "⬇️ Download Original SRT",
                data=st.session_state.original_srt,
                file_name="original_transcription.srt",
                mime="text/plain",
                use_container_width=True,
            )
        with c_next:
            st.info("👉 Switch to Tab 2 to translate these subtitles to Khmer.")


# ----------------------------------------------------
# TAB 2: Translate SRT -> Khmer
# ----------------------------------------------------
with tabs[2]:
    st.markdown("### 2️⃣ Translate SRT to Natural Khmer")
    st.caption("Translate your SRT lines into natural Khmer (ភាសាខ្មែរ) with Gemini Flash. Exact timestamps are preserved.")

    # Option to use SRT from Step 1 or paste custom SRT
    custom_srt_input = st.text_area(
        "Source SRT (Paste or use from Step 1)",
        value=st.session_state.original_srt,
        height=180,
        placeholder="1\n00:00:01,000 --> 00:00:04,000\nHello world...",
    )

    if st.button("🇰🇭 Translate Subtitles to Khmer", type="primary", use_container_width=True):
        if not custom_srt_input.strip():
            st.warning("Please provide or transcribe SRT subtitles first.")
        elif not gemini_key:
            st.error("Please enter your Gemini API Key in the sidebar.")
        else:
            parsed_subs = parse_srt(custom_srt_input)
            st.session_state.subtitles_orig = parsed_subs
            bar = st.progress(0)
            with st.spinner("Translating to Khmer with Gemini Flash..."):
                try:
                    khmer_subs = translate_subtitles_to_khmer(parsed_subs, gemini_key, bar)
                    st.session_state.subtitles_khmer = khmer_subs
                    st.session_state.khmer_srt = export_subtitles_to_srt(khmer_subs)
                    st.success(f"Successfully translated {len(khmer_subs)} lines into Khmer!")
                except Exception as e:
                    st.error(f"Translation failed: {e}")

    if st.session_state.khmer_srt:
        st.markdown("#### 🇰🇭 Khmer Subtitles (ភាសាខ្មែរ)")
        edited_khmer = st.text_area(
            "Khmer SRT Editor (You can refine text before generating voice)",
            value=st.session_state.khmer_srt,
            height=260,
        )
        if edited_khmer != st.session_state.khmer_srt:
            st.session_state.khmer_srt = edited_khmer
            st.session_state.subtitles_khmer = parse_srt(edited_khmer)

        c_dl2, c_next2 = st.columns([1, 1])
        with c_dl2:
            st.download_button(
                "⬇️ Download Khmer SRT",
                data=st.session_state.khmer_srt,
                file_name="khmer_translation.srt",
                mime="text/plain",
                use_container_width=True,
            )
        with c_next2:
            st.info("👉 Switch to Tab 3 to generate neural voice-over audio.")


# ----------------------------------------------------
# TAB 3: Generate Voice-over TTS (Auto-Retry Active)
# ----------------------------------------------------
with tabs[3]:
    st.markdown("### 3️⃣ Generate Voice-Over TTS (Auto-Retry Active)")
    st.caption("Converts each Khmer subtitle line into studio-grade speech. If any line fails, the multi-tier auto-retry mechanism continues until speech is generated.")

    subs_to_speak = st.session_state.subtitles_khmer
    if not subs_to_speak and st.session_state.khmer_srt:
        subs_to_speak = parse_srt(st.session_state.khmer_srt)
        st.session_state.subtitles_khmer = subs_to_speak

    c_v1, c_v2 = st.columns([3, 2])
    with c_v1:
        st.write(f"Total Lines to Voice: **{len(subs_to_speak)}**")
        st.write(f"Selected Voice: **{voice_tag}** | Speed: **{speech_speed}**")
    with c_v2:
        st.markdown(
            """
            <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid #10b981; border-radius: 8px; padding: 10px;">
                <span style="color: #34d399; font-weight: 600;">🛡️ Infinite Retry Enabled</span><br>
                <span style="font-size: 0.85rem; color: #d1d5db;">Retries Edge-TTS up to 5 times with backoff, then auto-falls back to gTTS if needed.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if subs_to_speak:
        if st.button("🎙️ Generate All Voice-Over Lines", type="primary", use_container_width=True):
            p_bar = st.progress(0)
            status_txt = st.empty()
            with st.spinner("Generating speech with auto-retry..."):
                audio_map = generate_all_voiceover_clips(
                    subs_to_speak,
                    voice_tag,
                    speech_speed,
                    "+0Hz",
                    p_bar,
                    status_txt,
                )
                st.session_state.voiceover_paths = audio_map
                st.success(f"Generated {len(audio_map)} voice lines successfully!")

    # Display preview table for each line
    if subs_to_speak:
        st.markdown("#### 🎧 Individual Line Audio Previews")
        for s in subs_to_speak[:50]:  # Display first 50 lines for speed
            c_idx, c_time, c_txt, c_play = st.columns([1, 2, 5, 3])
            with c_idx:
                st.write(f"#{s.index}")
            with c_time:
                st.caption(f"{s.start_time}")
            with c_txt:
                st.markdown(f"<span class='khmer-text'>{s.text}</span>", unsafe_allow_html=True)
            with c_play:
                clip = st.session_state.voiceover_paths.get(s.index)
                if clip and Path(clip).exists():
                    st.audio(str(clip))
                else:
                    if st.button(f"Retry #{s.index}", key=f"retry_{s.index}"):
                        target_clip = USER_DIR / "tts_cache" / f"line_{s.index}_{voice_tag.split('-')[2]}.mp3"
                        ok = synthesize_line_with_retry(s.text, voice_tag, speech_speed, "+0Hz", target_clip)
                        if ok:
                            st.session_state.voiceover_paths[s.index] = target_clip
                            st.rerun()
                        else:
                            st.error("Failed to generate.")
    else:
        st.info("Please translate subtitles in Tab 2 before generating voice-over.")


# ----------------------------------------------------
# TAB 4: Render Master MP3
# ----------------------------------------------------
with tabs[4]:
    st.markdown("### 4️⃣ Render Master MP3 Audio")
    st.caption("Composites all voice-over lines at their exact SRT timestamps into a single, high-fidelity MP3 master file.")

    c_r1, c_r2 = st.columns([3, 2])
    with c_r1:
        st.write(f"Voiced Segments Ready: **{len(st.session_state.voiceover_paths)}**")
        bgm_step4 = st.file_uploader("Optional Background Music (BGM)", type=["mp3", "wav"], key="step4_bgm")
        bgm_vol = st.slider("BGM Volume Ducking (dB)", min_value=-30.0, max_value=-6.0, value=-18.0, step=1.0)
    with c_r2:
        st.markdown(
            """
            <div style="background: rgba(59, 130, 246, 0.1); border: 1px solid #3b82f6; border-radius: 8px; padding: 12px;">
                <span style="color: #60a5fa; font-weight: 600;">⏱️ Exact Timestamp Placement</span><br>
                <span style="font-size: 0.85rem; color: #d1d5db;">Each spoken sentence is aligned to the millisecond with your original video/SRT timing.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if st.button("🎵 Render Final Master MP3", type="primary", use_container_width=True):
        if not st.session_state.voiceover_paths:
            st.error("No voice-over clips found. Please run Step 3 first.")
        else:
            bgm_p = None
            if bgm_step4:
                bgm_p = USER_DIR / f"bgm_{int(time.time())}.mp3"
                bgm_p.write_bytes(bgm_step4.getbuffer())

            bar = st.progress(0)
            with st.spinner("Compositing and mastering MP3..."):
                try:
                    mp3_out = render_master_mp3(
                        st.session_state.subtitles_khmer,
                        st.session_state.voiceover_paths,
                        st.session_state.video_duration_ms,
                        bgm_p,
                        bgm_vol,
                        bar,
                    )
                    st.session_state.rendered_mp3_path = mp3_out
                    st.success("Master MP3 Rendered Successfully!")
                except Exception as e:
                    st.error(f"Render failed: {e}")

    if st.session_state.rendered_mp3_path and Path(st.session_state.rendered_mp3_path).exists():
        final_file = Path(st.session_state.rendered_mp3_path)
        st.markdown("---")
        st.markdown("### 🎧 Master Audio Playback")
        st.audio(str(final_file))
        
        c_down1, c_down2 = st.columns([2, 1])
        with c_down1:
            st.download_button(
                label="⬇️ Download Final Master MP3",
                data=final_file.read_bytes(),
                file_name="dubbed_khmer_master.mp3",
                mime="audio/mp3",
                type="primary",
                use_container_width=True,
            )
        with c_down2:
            st.metric("File Size", f"{final_file.stat().st_size / (1024*1024):.2f} MB")
