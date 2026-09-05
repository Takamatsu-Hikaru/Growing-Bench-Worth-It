FROM python:3.13.7-slim-bookworm

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       git nodejs texlive-latex-base texlive-latex-recommended \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /bridge && touch /bridge/tool.py

LABEL org.growing-bench.agent-runtime="0.2"

WORKDIR /workspace
