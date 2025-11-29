from calendar_client import get_calendar_service, list_upcoming_events, create_event
from datetime import datetime, time, timedelta
import os
import streamlit as st
from dotenv import load_dotenv

from calendar_client import get_calendar_service, list_upcoming_events

load_dotenv()

st.title("Managed Calendar")

calendar_id = os.getenv("MANAGED_CALENDAR_ID")

if not calendar_id:
    st.error("Missing MANAGED_CALENDAR_ID in .env")
else:
    try:
        service = get_calendar_service()
        events = list_upcoming_events(service, calendar_id=calendar_id, max_results=10)
    except Exception as exc:  # pragma: no cover - UI side effect
        st.exception(exc)
        events = []

    if events:
        for event in events:
            st.subheader(event.get("summary", "(no title)"))
            st.write(f"Start: {event.get('start')}")
            st.write(f"End: {event.get('end')}")
            if event.get("location"):
                st.write(f"Location: {event['location']}")
            if event.get("htmlLink"):
                st.write(f"[Open in Google Calendar]({event['htmlLink']})")
            st.markdown("---")

    else:
        st.info("No upcoming events found.")

st.subheader("Create a test event")

default_title = "Test class"
title = st.text_input("Event title", value=default_title)

col1, col2 = st.columns(2)
with col1:
    event_date = st.date_input("Date")
with col2:
    event_time = st.time_input("Start time", value=time(9, 0))

duration_minutes = st.number_input("Duration (minutes)", min_value=15, max_value=240, value=60, step=15)

if st.button("Create test event in managed calendar"):
    try:
        service = get_calendar_service()

        start_dt = datetime.combine(event_date, event_time)
        end_dt = start_dt + timedelta(minutes=int(duration_minutes))

        created = create_event(service, calendar_id, title, start_dt, end_dt)

        st.success(f"Created event: {created.get('summary')} at {created['start'].get('dateTime')}")
        st.json(created)  # optional: show the full event object
    except Exception as ex:
        st.exception(ex)

#Connect agent to UI
from agents.calendar_agent import run_calendar_agent
import streamlit as st

st.header("Azure Calendar Agent (Agents SDK)")

user_query = st.text_input(
    "Ask the calendar agent something:",
    value="What are my next 5 events?",
)

if st.button("Ask Azure-based agent"):
    with st.spinner("Thinking with Azure OpenAI + tools..."):
        reply = run_calendar_agent(user_query)
    st.write(reply)



