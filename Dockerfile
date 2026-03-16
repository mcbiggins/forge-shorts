FROM nvidia/cuda:12.6.3-runtime-ubuntu24.04

# Python 3.12 + fontconfig for subtitle fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    unzip \
    fontconfig \
    fonts-liberation \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

# BtbN static FFmpeg with NVENC support (matching auto-editor pattern)
RUN curl -L -o /tmp/ffmpeg.tar.xz \
        https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n7.1-latest-linux64-gpl-7.1.tar.xz \
    && cd /tmp && tar xf ffmpeg.tar.xz \
    && cp ffmpeg-n7.1-latest-linux64-gpl-7.1/bin/ffmpeg /usr/local/bin/ \
    && cp ffmpeg-n7.1-latest-linux64-gpl-7.1/bin/ffprobe /usr/local/bin/ \
    && rm -rf /tmp/ffmpeg*

# Install Montserrat font from Google Fonts GitHub repo
RUN mkdir -p /usr/share/fonts/truetype/montserrat \
    && for weight in Bold ExtraBold SemiBold Medium Regular Black; do \
        curl -sSL -o /usr/share/fonts/truetype/montserrat/Montserrat-${weight}.ttf \
        "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf" \
        && break; \
    done \
    && curl -sSL -o /usr/share/fonts/truetype/montserrat/Montserrat-Bold.ttf \
        "https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf/Montserrat-Bold.ttf" \
    && curl -sSL -o /usr/share/fonts/truetype/montserrat/Montserrat-ExtraBold.ttf \
        "https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf/Montserrat-ExtraBold.ttf" \
    && curl -sSL -o /usr/share/fonts/truetype/montserrat/Montserrat-Black.ttf \
        "https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf/Montserrat-Black.ttf" \
    && curl -sSL -o /usr/share/fonts/truetype/montserrat/Montserrat-SemiBold.ttf \
        "https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf/Montserrat-SemiBold.ttf" \
    && fc-cache -fv

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY *.py ./

EXPOSE 5682

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=10s \
    CMD curl -f http://localhost:5682/health || exit 1

CMD ["python3", "shorts_api.py"]
