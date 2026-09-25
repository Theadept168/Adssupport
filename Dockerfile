FROM python:3.12-slim

# Install system dependencies including ffmpeg and socat for multi-port forwarding
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    socat \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Expose both 8501 and 8080
EXPOSE 8501
EXPOSE 8080

# Run Streamlit on 8501 and forward 8080 (and dynamic $PORT if different) to 8501 so Railway domain works regardless of target port
CMD ["sh", "-c", "socat TCP-LISTEN:8080,fork,reuseaddr TCP:127.0.0.1:8501 & if [ -n \"$PORT\" ] && [ \"$PORT\" != \"8501\" ] && [ \"$PORT\" != \"8080\" ]; then socat TCP-LISTEN:$PORT,fork,reuseaddr TCP:127.0.0.1:8501 & fi; exec streamlit run app.py --server.port=8501 --server.address=0.0.0.0 --server.maxUploadSize=2048 --server.headless=true"]


