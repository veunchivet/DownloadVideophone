FROM python:3.12-slim

# ffmpeg: merge HD video + audio, convert MP3
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# deno: JavaScript runtime that yt-dlp needs for YouTube
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

WORKDIR /app
RUN pip install --no-cache-dir -U --pre "yt-dlp[default]"

COPY index.html server.py ./

ENV VG_CLOUD=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8800
EXPOSE 8800

# update yt-dlp on every start so sites that change keep working
CMD ["sh", "-c", "pip install -q --no-cache-dir -U --pre 'yt-dlp[default]' || true; python server.py"]
