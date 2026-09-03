# Render (and most PaaS Python buildpacks) don't include a C++ compiler.
# This app needs g++ to compile student submissions, so it's deployed as a
# container instead of the plain Python buildpack.

FROM python:3.11-slim

# g++ for compiling submitted C++ code; build-essential pulls in the rest
# of the toolchain (make, libc headers) g++ expects to be present.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render sets $PORT at runtime; default it for local `docker run` testing.
ENV PORT=8000
EXPOSE 8000

CMD gunicorn app:app --bind 0.0.0.0:$PORT
