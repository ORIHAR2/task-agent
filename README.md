---
title: Task Automation Agent
emoji: 🤖
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8501
pinned: false
---

# Task-Automation Agent
Search the web (DuckDuckGo) and summarize into a three-bullet brief with Gemini.

Run locally with Docker:

    docker build -t task-agent .
    docker run -p 8501:8501 -e GOOGLE_API_KEY=<your key> task-agent
