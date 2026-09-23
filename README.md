# 🎙️ Dubber AI Pro Studio (Mobile & Web)

An AI-powered video and audio dubbing studio built with Streamlit.

## ✨ Features
- **Speech-to-Text Transcription**: Whisper speech recognition.
- **Khmer Translation**: High-precision translation powered by Gemini 3.6 Flash.
- **Neural Voice-Over**: Studio-grade Microsoft Edge Neural TTS with native Khmer voices (`km-KH-PisethNeural` & `km-KH-SreymomNeural`).
- **Video Studio**: Automatic dubbing, background music blending, and optional hardsub subtitle burning.
- **1-Click Auto Pipeline**: Hands-free transcription $\rightarrow$ translation $\rightarrow$ TTS $\rightarrow$ video dubbing.

## 🚀 Cloud Deployment (Streamlit Community Cloud)

1. Fork or push this repository to your GitHub account.
2. Sign in to [Streamlit Community Cloud](https://share.streamlit.io).
3. Click **New app** and select:
   - **Repository**: `your-username/your-repo`
   - **Branch**: `main`
   - **Main file path**: `app.py`
4. In **Advanced settings** $\rightarrow$ **Secrets**, optionally add your Gemini API key:
   ```toml
   GEMINI_API_KEY = "your_gemini_api_key_here"
   ```
5. Click **Deploy**!

## 💻 Local / Mobile Wi-Fi Run

```bash
pip install -r requirements.txt
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```
Or double-click `start_phone_web.bat` on Windows.
