#!/usr/bin/env python3
"""Chạy API: uvicorn api_server:app --host 0.0.0.0 --port 8000"""
from app.api import app

__all__ = ["app"]
