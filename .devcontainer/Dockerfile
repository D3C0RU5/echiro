FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

RUN python -m pip install --no-cache-dir uv==0.11.21

RUN mkdir -p /home/vscode/.codex \
    && chown -R vscode:vscode /home/vscode/.codex
