import os
from datetime import date

import streamlit as st
from dotenv import load_dotenv

# Load environment variables before importing modules that read env at import time
load_dotenv()

from typing import List

from calendar_client import get_calendar_service, list_upcoming_events
from app_agents.calendar_agent import run_calendar_agent
from app_agents.document_agent import run_document_agent
from app_agents.planner_agent import run_planner_agent
from models import SemesterWindow, ScheduleEvent


st.set_page_config(page_title="Managed Calendar", layout="wide")
st.title("Managed Calendar")

calendar_id = os.getenv("MANAGED_CALENDAR_ID")

if "extracted_events" not in st.session_state:
    st.session_state.extracted_events: List[ScheduleEvent] = []

if not calendar_id:
    st.error("Missing MANAGED_CALENDAR_ID in .env")
else:
    tab_events, tab_chat, tab_upload = st.tabs(["Upcoming events", "Chat", "Upload schedule"])

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

    with tab_upload:
        st.markdown("---")
        st.header("Phase 4 — Upload your class schedule")

        uploaded_file = st.file_uploader(
            "Upload a PDF or image (screenshot) of your class schedule",
            type=["pdf", "png", "jpg", "jpeg"],
        )

        extracted_events: List[dict] = []

        if uploaded_file is not None:
            st.write(f"File uploaded: **{uploaded_file.name}**")

            if st.button("Extract schedule from file"):
                file_bytes = uploaded_file.read()
                mime_type = uploaded_file.type  # e.g. 'application/pdf' or 'image/png'

                with st.spinner("Asking the document agent to extract your schedule..."):
                    events = run_document_agent(file_bytes, mime_type)
                    extracted_events = events
                    st.session_state.extracted_events = events

                if not events:
                    st.warning("No events were extracted. You might need a clearer screenshot or PDF.")
                else:
                    st.success(f"Extracted {len(events)} schedule entries.")

                    data = [
                        {
                            "title": getattr(e, "title", None),
                            "day_of_week": getattr(e, "day_of_week", None),
                            "start_time": getattr(e, "start_time", None),
                            "end_time": getattr(e, "end_time", None),
                            "location": getattr(e, "location", None),
                            "recurrence": getattr(e, "recurrence", None),
                        }
                        for e in events
                    ]
                    st.table(data)

            if st.session_state.extracted_events:
                st.markdown("---")
                st.subheader("Plan semester events")
                semester_start = st.date_input("Semester start date", value=date.today())
                semester_end = st.date_input("Semester end date", value=date.today())
                timezone = st.text_input("Timezone (IANA)", value="Europe/Brussels")

                if st.button("Generate plan"):
                    if semester_end < semester_start:
                        st.error("Semester end must be after start.")
                    else:
                        sem = SemesterWindow(
                            semester_start=semester_start.isoformat(),
                            semester_end=semester_end.isoformat(),
                            timezone=timezone,
                        )
                        with st.spinner("Planning recurring events..."):
                            plan = run_planner_agent(st.session_state.extracted_events, sem)
                        st.success("Plan generated.")
                        st.subheader("Preview")
                        st.write(plan.preview)
                        st.subheader("Raw plan")
                        st.json(plan.model_dump())
