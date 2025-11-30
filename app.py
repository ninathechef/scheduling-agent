import os

import streamlit as st
from dotenv import load_dotenv

# Load environment variables before importing modules that read env at import time
load_dotenv()

from calendar_client import get_calendar_service, list_upcoming_events
from app_agents.calendar_agent import run_calendar_agent


st.set_page_config(page_title="Managed Calendar", layout="wide")
st.title("Managed Calendar")

calendar_id = os.getenv("MANAGED_CALENDAR_ID")

if not calendar_id:
    st.error("Missing MANAGED_CALENDAR_ID in .env")
else:
    tab_events, tab_chat = st.tabs(["Upcoming events", "Chat"])

    with tab_events:
        st.subheader("Upcoming events")
        try:
            service = get_calendar_service()
            events = list_upcoming_events(service, calendar_id=calendar_id, max_results=10)
        except Exception as exc:  # pragma: no cover - UI side effect
            st.exception(exc)
            events = []

        if events:
            for event in events:
                st.markdown(f"**{event.get('summary', '(no title)')}**")
                st.write(f"Start: {event.get('start')}")
                st.write(f"End: {event.get('end')}")
                if event.get("location"):
                    st.write(f"Location: {event['location']}")
                if event.get("htmlLink"):
                    st.write(f"[Open in Google Calendar]({event['htmlLink']})")
                st.markdown("---")
        else:
            st.info("No upcoming events found.")

    with tab_chat:
        st.subheader("Chat with your calendar agent")

        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = [
                {"role": "assistant", "content": "Hi! Ask me about your calendar and I'll use tools to help."}
            ]

        history_box = st.container(height=420, border=True)
        with history_box:
            for msg in st.session_state.chat_messages:
                st.chat_message(msg["role"]).write(msg["content"])

        user_input = st.chat_input("Ask something about your calendar...")

        if user_input:
            history = st.session_state.chat_messages.copy()
            st.session_state.chat_messages.append({"role": "user", "content": user_input})

            with history_box:
                for msg in st.session_state.chat_messages:
                    st.chat_message(msg["role"]).write(msg["content"])
                with st.chat_message("assistant"):
                    with st.spinner("Thinking with Azure OpenAI + tools..."):
                        reply = run_calendar_agent(user_input, history=history)
                        st.write(reply)
            st.session_state.chat_messages.append({"role": "assistant", "content": reply})
            st.rerun()
