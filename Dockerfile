# Optional: deploy with Docker instead of the native Python runtime.
# On Render: set the service's "Runtime" to Docker (or add this Dockerfile
# and choose "Docker" when creating the service). Guarantees the exact same
# image locally and in production.
#
# Cookies ship with the repo in ./cookies/*.txt (see .gitignore) so they are
# present in the image. Rebuild + redeploy when you update them.
FROM python:3.12-slim

# ffmpeg: required for merging video+audio streams and MP3 conversion.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 10000

# start.sh reads $PORT, falling back to 8000.
CMD ["./start.sh"]