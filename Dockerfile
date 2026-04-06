FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-dev python3-pip python3-venv python3-tk libpython3.10 binutils \
    libgtk-3-0 libtk8.6 libtcl8.6 libx11-6 libxft2 libfontconfig1 libxss1 \
    libgirepository1.0-dev libcairo2-dev pkg-config \
    gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 \
    libayatana-appindicator3-1 xvfb \
    && rm -rf /var/lib/apt/lists/*

ENV DISPLAY=:99

WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv /venv \
    && /venv/bin/pip install --no-cache-dir -r requirements.txt pyinstaller pyinstaller-hooks-contrib "PyGObject==3.42.2"

COPY . .
CMD Xvfb :99 -screen 0 1x1x8 &>/dev/null & /venv/bin/python3 build.py && bash build-deb.sh
