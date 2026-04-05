FROM ubuntu:22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-dev python3-pip python3-venv python3-tk libpython3.10 binutils \
    libgtk-3-0 libtk8.6 libtcl8.6 libx11-6 libxft2 libfontconfig1 libxss1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv /venv \
    && /venv/bin/pip install --no-cache-dir -r requirements.txt pyinstaller

COPY . .
CMD /venv/bin/python3 build.py && bash build-deb.sh
