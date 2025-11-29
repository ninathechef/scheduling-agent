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

