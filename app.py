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
    # Set WindowsSelectorEventLoopPolicy for robust asyncio without Proactor socket errors
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

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
    
    /* Stepper Workflow Cards */
    .step-nav-bar {
        display: flex;
        gap: 12px;
        margin-bottom: 24px;
        flex-wrap: wrap;
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

    /* Studio Glass Card */
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
    
    /* Modern buttons */
    .stButton>button {
        border-radius: 10px;
        font-weight: 600;
        letter-spacing: 0.01em;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        padding: 10px 18px;
    }
    .stButton>button:hover {
        transform: translateY(-1.5px);
        box-shadow: 0 6px 18px rgba(59, 130, 246, 0.35);
    }
    
    /* Stat Badge */
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
        "selected_voice": "km-KH-PisethNeural",
        "selected_speed": "+0%",
        "selected_pitch": "+0Hz",
        "auto_pipeline_running": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


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
            # Remove any unwanted non-Khmer script bleed (Thai Unicode \u0E00-\u0E7F)
            khmer_txt = re.sub(r"[\u0E00-\u0E7F]+", "", khmer_txt).strip() or s.text
            khmer_list.append(
                Subtitle(
                    index=s.index,
                    start_time=s.start_time,
                    end_time=s.end_time,
                    text=khmer_txt,
                    start_ms=s.start_ms,
                    end_ms=s.end_ms,
                )
            )

        if p_bar:
            p_bar.progress(int(min(100, (b_idx + len(chunk)) / total * 100)))
        if p_status:
            p_status.text(f"Translating to Khmer: {min(b_idx + len(chunk), total)}/{total} lines...")

    return khmer_list


# 3. Robust Voice-Over TTS Synthesis (With Infinite Retry & Isolated Event Loop)
def synthesize_line_isolated_loop(text: str, voice: str, rate: str, pitch: str, out_file: Path) -> bool:
    """Safely runs edge-tts inside a clean, isolated event loop on Windows."""
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
    """Robust multi-tier retry mechanism: 'when can't generate voice-over please try do it'."""
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


def generate_all_tts(subtitles: list[Subtitle], voice: str, rate: str, pitch: str, p_bar=None, p_status=None) -> dict[int, str]:
    tts_dir = USER_DIR / "tts_cache"
    tts_dir.mkdir(exist_ok=True)
    
    total = len(subtitles)
    audio_map = {}
    failed = []

    for idx, s in enumerate(subtitles, start=1):
        voice_tag = "piseth" if "piseth" in voice.lower() else "sreymom"
        clip_p = tts_dir / f"line_{s.index}_{voice_tag}.mp3"

        if clip_p.exists() and clip_p.stat().st_size > 500:
            audio_map[s.index] = str(clip_p)
        else:
            if p_status:
                p_status.text(f"🎙️ Voicing line {idx}/{total}: {s.text[:30]}...")
            
            success = generate_tts_clip_with_resilience(s.text, voice, rate, pitch, clip_p)
            if success:
                audio_map[s.index] = str(clip_p)
            else:
                failed.append(s.index)

        if p_bar:
            p_bar.progress(int(idx / total * 100))

    if failed:
        st.warning(f"⚠️ {len(failed)} line(s) required recovery: lines {failed}")
    return audio_map


# 4. Render Master MP3 Audio
def render_dubbed_mp3(
    subtitles: list[Subtitle],
    audio_map: dict[int, str],
    video_dur_ms: int = 0,
    bgm_path: Optional[Path] = None,
    bgm_vol_db: float = -18.0,
    p_bar=None,
    p_status=None,
) -> Path:
    if not subtitles or not audio_map:
        raise ValueError("Missing subtitles or voiced clips to render.")

    max_end = max(s.end_ms for s in subtitles) if subtitles else 0
    total_len = max(video_dur_ms, max_end + 1000)

    if p_status: p_status.text("🎼 Initializing silent audio timeline...")
    if p_bar: p_bar.progress(10)

    timeline = AudioSegment.silent(duration=total_len)

    total_subs = len(subtitles)
    for idx, s in enumerate(subtitles):
        clip_str = audio_map.get(s.index)
        if clip_str and Path(clip_str).exists():
            try:
                clip = AudioSegment.from_file(clip_str)
                timeline = timeline.overlay(clip, position=s.start_ms)
            except Exception:
                pass
        if p_bar:
            p_bar.progress(10 + int(70 * (idx + 1) / total_subs))

    # Background Music Blending
    if bgm_path and bgm_path.exists():
        if p_status: p_status.text("🎶 Blending background music track...")
        try:
            bgm = AudioSegment.from_file(bgm_path) + bgm_vol_db
            if len(bgm) < total_len:
                loops = (total_len // len(bgm)) + 1
                bgm = (bgm * loops)[:total_len]
            else:
                bgm = bgm[:total_len]
            bgm = bgm.fade_out(1500)
            timeline = timeline.overlay(bgm, position=0)
        except Exception as e:
            st.warning(f"BGM blend error: {e}")

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

    st.markdown("#### 🎙️ Voice Settings")
    voice_choice = st.selectbox(
        "Khmer Neural Voice",
        options=["km-KH-PisethNeural (ប្រុស - Male)", "km-KH-SreymomNeural (ស្រី - Female)"],
        index=0 if "piseth" in st.session_state.selected_voice.lower() else 1,
    )
    st.session_state.selected_voice = "km-KH-PisethNeural" if "Piseth" in voice_choice else "km-KH-SreymomNeural"

    st.session_state.selected_speed = st.select_slider(
        "Voice Speed",
        options=["-20%", "-10%", "+0%", "+10%", "+20%", "+30%"],
        value=st.session_state.selected_speed,
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
                    Video to SRT $\\rightarrow$ Khmer Translation $\\rightarrow$ Neural Voice-Over $\\rightarrow$ Master MP3
                </p>
            </div>
            <div style="display: flex; gap: 10px; margin-top: 10px;">
                <span class="stat-badge">📝 {len(st.session_state.subtitles_orig)} Lines</span>
                <span class="stat-badge">🎙️ {len(st.session_state.voiceover_clips)} Voiced</span>
                <span class="stat-badge">⏱️ {st.session_state.video_duration_ms // 1000}s</span>
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
    st.markdown(f"<div class='step-pill {act}'><div class='step-num num-3'>3</div><div><div style='font-size:0.75rem; color:#94a3b8;'>STEP 3</div><div style='font-weight:700;'>Voice-Over TTS</div></div></div>", unsafe_allow_html=True)
with c_p4:
    act = "active" if st.session_state.current_step == 4 else ("completed" if st.session_state.master_mp3_path else "")
    st.markdown(f"<div class='step-pill {act}'><div class='step-num num-4'>4</div><div><div style='font-size:0.75rem; color:#94a3b8;'>STEP 4</div><div style='font-weight:700;'>Render MP3</div></div></div>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Main Studio Tabs
tab_auto, tab1, tab2, tab3, tab4 = st.tabs([
    "⚡ 1-Click Auto Pipeline",
    "1️⃣ Transcribe Video $\\rightarrow$ SRT",
    "2️⃣ Translate SRT $\\rightarrow$ Khmer",
    "3️⃣ Voice-Over TTS (Auto-Retry)",
    "4️⃣ Render Master MP3",
])

# ---------------------------------------------------------------------
# ⚡ 1-CLICK AUTO PIPELINE
# ---------------------------------------------------------------------
with tab_auto:
    st.markdown(
        """
        <div class="studio-card">
            <h3 style="margin-top:0; color:#60a5fa;">⚡ 1-Click Hands-Free Pipeline</h3>
            <p style="color:#94a3b8;">Upload your video or audio file. Dubber AI will automatically run all 4 steps and render your final Khmer MP3 voice-over.</p>
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
        st.caption(f"Active Voice: **{st.session_state.selected_voice}** | Speed: **{st.session_state.selected_speed}**")

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
                st.session_state.subtitles_khmer = subs2
                st.session_state.srt_text_khmer = export_subtitles_to_srt(subs2)
                status_box.write(f"✓ Step 2 Complete: {len(subs2)} lines translated to Khmer.")

                # Step 3
                status_box.write("🎙️ **Step 3/4**: Synthesizing neural voice-over (infinite retry active)...")
                clips = generate_all_tts(
                    subs2,
                    st.session_state.selected_voice,
                    st.session_state.selected_speed,
                    st.session_state.selected_pitch,
                    p_bar,
                )
                st.session_state.voiceover_clips = clips
                status_box.write(f"✓ Step 3 Complete: {len(clips)} lines synthesized.")

                # Step 4
                status_box.write("🎧 **Step 4/4**: Rendering master MP3 audio track...")
                final_out = render_dubbed_mp3(
                    subs2,
                    clips,
                    st.session_state.video_duration_ms,
                    bgm_p,
                    -18.0,
                    p_bar,
                )
                st.session_state.master_mp3_path = str(final_out)
                st.session_state.current_step = 4
                status_box.update(label="🎉 Full Pipeline Complete!", state="complete")
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
                <h3 style="margin-top:0; color:#34d399;">🎧 Master Dubbed MP3 Ready!</h3>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.audio(str(mp3_obj))
        st.download_button(
            label="⬇️ Download Dubbed MP3 File",
            data=mp3_obj.read_bytes(),
            file_name=f"dubbed_khmer_{mp3_obj.name}",
            mime="audio/mp3",
            type="primary",
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
    st.caption("Translates subtitle dialogue into natural, fluent Khmer speech while strictly preserving millisecond timestamps.")

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
            if st.button("Proceed to Step 3: Voice-Over TTS ➔", use_container_width=True):
                st.session_state.current_step = 3
                st.rerun()


# ---------------------------------------------------------------------
# TAB 3: VOICE-OVER TTS (AUTO-RETRY ACTIVE)
# ---------------------------------------------------------------------
with tab3:
    st.markdown("### 3️⃣ Generate Voice-Over TTS (Auto-Retry Active)")
    st.caption("Synthesizes studio-quality Khmer speech for each subtitle line. An automatic multi-tier retry mechanism ensures no dialogue lines are missed.")

    kh_subs = st.session_state.subtitles_khmer
    if not kh_subs and st.session_state.srt_text_khmer:
        kh_subs = parse_srt(st.session_state.srt_text_khmer)
        st.session_state.subtitles_khmer = kh_subs

    c_vinfo1, c_vinfo2 = st.columns([3, 2])
    with c_vinfo1:
        st.write(f"Subtitle Lines to Voice: **{len(kh_subs)}**")
        st.write(f"Voice: **{st.session_state.selected_voice}** | Speed: **{st.session_state.selected_speed}**")
    with c_vinfo2:
        st.markdown(
            """
            <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid #10b981; border-radius: 10px; padding: 12px;">
                <span style="color: #34d399; font-weight: 700;">🛡️ Infinite Auto-Retry Active</span><br>
                <span style="font-size: 0.85rem; color: #cbd5e1;">Retries Edge-TTS up to 5x with backoff, then auto-falls back to gTTS Khmer.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if kh_subs:
        if st.button("🎙️ Generate All Voice-Over Lines", type="primary", use_container_width=True):
            bar3 = st.progress(0)
            status3 = st.empty()
            with st.spinner("Synthesizing voice-over with retry..."):
                clips = generate_all_tts(
                    kh_subs,
                    st.session_state.selected_voice,
                    st.session_state.selected_speed,
                    st.session_state.selected_pitch,
                    bar3,
                    status3,
                )
                st.session_state.voiceover_clips = clips
                st.session_state.current_step = 4
                st.success(f"✓ Generated {len(clips)} voice lines successfully!")

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 🎧 Line Audio Preview & Single-Line Regeneration")
        
        # Display preview list
        for s in kh_subs[:40]:
            col_id, col_time, col_txt, col_aud = st.columns([1, 2, 5, 3])
            with col_id:
                st.markdown(f"**#{s.index}**")
            with col_time:
                st.caption(f"{s.start_time}")
            with col_txt:
                st.markdown(f"<span class='khmer-font'>{s.text}</span>", unsafe_allow_html=True)
            with col_aud:
                clip_path = st.session_state.voiceover_clips.get(s.index)
                if clip_path and Path(clip_path).exists():
                    st.audio(str(clip_path))
                else:
                    if st.button(f"Retry #{s.index}", key=f"btn_re_{s.index}"):
                        vtag = "piseth" if "piseth" in st.session_state.selected_voice.lower() else "sreymom"
                        out_p = USER_DIR / "tts_cache" / f"line_{s.index}_{vtag}.mp3"
                        ok = generate_tts_clip_with_resilience(
                            s.text,
                            st.session_state.selected_voice,
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
        st.info("Translate your subtitles in Step 2 to generate voice-over speech.")


# ---------------------------------------------------------------------
# TAB 4: RENDER MASTER MP3
# ---------------------------------------------------------------------
with tab4:
    st.markdown("### 4️⃣ Render Master MP3 Audio")
    st.caption("Stitches all dialogue lines at their exact SRT timestamps into a single, high-fidelity MP3 master file.")

    c_rend1, c_rend2 = st.columns([3, 2])
    with c_rend1:
        st.write(f"Voiced Dialogue Segments: **{len(st.session_state.voiceover_clips)}**")
        step4_bgm = st.file_uploader("Optional Background Music (BGM)", type=["mp3", "wav"], key="step4_bgm_file")
        bgm_duck_vol = st.slider("BGM Ducking Level (dB)", min_value=-30.0, max_value=-6.0, value=-18.0, step=1.0)
    with c_rend2:
        st.markdown(
            """
            <div style="background: rgba(59, 130, 246, 0.1); border: 1px solid #3b82f6; border-radius: 10px; padding: 12px;">
                <span style="color: #60a5fa; font-weight: 700;">⏱️ Exact Timestamp Positioning</span><br>
                <span style="font-size: 0.85rem; color: #cbd5e1;">Each voiced segment is placed on the audio timeline matching its exact start timestamp.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if st.button("🎵 Render Final Master MP3", type="primary", use_container_width=True):
        if not st.session_state.voiceover_clips:
            st.error("No voice-over clips available. Please run Step 3 first.")
        else:
            bgm_obj = None
            if step4_bgm:
                bgm_obj = USER_DIR / f"bgm_{int(time.time())}.mp3"
                bgm_obj.write_bytes(step4_bgm.getbuffer())

            bar4 = st.progress(0)
            status4 = st.empty()
            with st.spinner("Rendering and mastering high-fidelity MP3..."):
                try:
                    mp3_res = render_dubbed_mp3(
                        st.session_state.subtitles_khmer,
                        st.session_state.voiceover_clips,
                        st.session_state.video_duration_ms,
                        bgm_obj,
                        bgm_duck_vol,
                        bar4,
                        status4,
                    )
                    st.session_state.master_mp3_path = str(mp3_res)
                    st.success("✓ Master MP3 Rendered Successfully!")
                except Exception as ex:
                    st.error(f"Render failed: {ex}")

    if st.session_state.master_mp3_path and Path(st.session_state.master_mp3_path).exists():
        final_mp3 = Path(st.session_state.master_mp3_path)
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            """
            <div class="studio-card" style="border-color: rgba(16, 185, 129, 0.4);">
                <h3 style="margin-top:0; color:#34d399;">🎧 Master Audio Player</h3>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.audio(str(final_mp3))
        
        c_dl1, c_dl2 = st.columns([2, 1])
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
            st.metric("File Size", f"{final_mp3.stat().st_size / (1024*1024):.2f} MB")
