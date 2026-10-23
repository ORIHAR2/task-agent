"""Streamlit web interface for the task-automation agent."""
import os
import time

import streamlit as st

from agent import APP_VERSION, logger, run_workflow

st.set_page_config(page_title="Task Automation Agent", page_icon="🤖")
st.title("🤖 Task-Automation Agent")
st.caption(f"Search the web \u2192 summarize into a 3-point brief  |  Gemini + DuckDuckGo  |  v{APP_VERSION}")

if not os.getenv("GOOGLE_API_KEY"):
    st.error("Server is missing GOOGLE_API_KEY. Add it as an environment variable / platform secret.")
    st.stop()

topic = st.text_input("Topic", placeholder="e.g. recent developments in agentic AI")
temperature = st.slider("Temperature (creativity)", 0.0, 1.0, 0.3, 0.1)

if st.button("Generate brief", type="primary"):
    if not topic.strip():
        st.warning("Please enter a topic first.")
    else:
        start = time.perf_counter()
        with st.status("Running workflow...", expanded=True) as status:
            try:
                brief = run_workflow(topic, temperature, progress=st.write)
                status.update(label="Done", state="complete")
            except Exception as exc:
                logger.error("UI error: %s", exc)
                status.update(label="Failed", state="error")
                st.error(f"Something went wrong: {exc}")
                st.stop()
        st.subheader("Research brief")
        st.markdown(brief)
        st.caption(f"Completed in {time.perf_counter() - start:.1f} s")
