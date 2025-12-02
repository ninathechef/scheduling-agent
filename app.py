import os
from datetime import date
from typing import List

import streamlit as st
from dotenv import load_dotenv

# Load environment variables before importing modules that read env at import time
load_dotenv()

from calendar_client import get_calendar_service, list_upcoming_events
from app_agents.calendar_agent import run_calendar_agent
from app_agents.document_agent import run_document_agent
from app_agents.planner_agent import run_planner_agent
from app_agents.conflict_agent import run_conflict_agent
from app_agents.negotiation_agent import run_negotiation_agent
from app_agents.executor_agent import run_executor_agent
from models import ExecutionReport, MutationPlan, SemesterWindow, ScheduleEvent


st.set_page_config(page_title="Managed Calendar", layout="wide")
st.title("Managed Calendar")

calendar_id = os.getenv("MANAGED_CALENDAR_ID")

# Session state
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = [
        {"role": "assistant", "content": "Hi! Ask me about your calendar and I'll use tools to help."}
    ]
if "extracted_events" not in st.session_state:
    st.session_state.extracted_events: List[ScheduleEvent] = []
if "generated_plan" not in st.session_state:
    st.session_state.generated_plan = None
if "semester_window" not in st.session_state:
    st.session_state.semester_window = None
if "conflict_report" not in st.session_state:
    st.session_state.conflict_report = None
if "negotiation_outcome" not in st.session_state:
    st.session_state.negotiation_outcome = None
if "execution_report" not in st.session_state:
    st.session_state.execution_report = None

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
        st.header("Phase 4 - Upload your class schedule")

        uploaded_file = st.file_uploader(
            "Upload a PDF or image (screenshot) of your class schedule",
            type=["pdf", "png", "jpg", "jpeg"],
        )

        if uploaded_file is not None:
            st.write(f"File uploaded: **{uploaded_file.name}**")

            if st.button("Extract schedule from file"):
                file_bytes = uploaded_file.read()
                mime_type = uploaded_file.type  # e.g. 'application/pdf' or 'image/png'

                with st.spinner("Asking the document agent to extract your schedule..."):
                    events = run_document_agent(file_bytes, mime_type)
                    st.session_state.extracted_events = events

                if not events:
                    st.warning("No events were extracted. You might need a clearer screenshot or PDF.")
                else:
                    st.success(f"Extracted {len(events)} schedule entries.")

        if st.session_state.extracted_events:
            data = [
                {
                    "title": getattr(e, "title", None),
                    "day_of_week": getattr(e, "day_of_week", None),
                    "start_time": getattr(e, "start_time", None),
                    "end_time": getattr(e, "end_time", None),
                    "location": getattr(e, "location", None),
                    "recurrence": getattr(e, "recurrence", None),
                }
                for e in st.session_state.extracted_events
            ]
            st.table(data)

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
                    st.session_state.semester_window = sem
                    with st.spinner("Planning recurring events..."):
                        plan = run_planner_agent(st.session_state.extracted_events, sem)
                    st.success("Plan generated.")
                    st.session_state.generated_plan = plan
                    st.session_state.conflict_report = None
                    st.session_state.execution_report = None
                    st.subheader("Preview")
                    st.write(plan.preview)
                    st.subheader("Raw plan")
                    st.json(plan.model_dump())

        if st.session_state.generated_plan:
            st.markdown("---")
            st.subheader("Conflict detection")
            if st.button("Detect conflicts"):
                if not st.session_state.semester_window:
                    st.error("Missing semester window; generate the plan first.")
                elif not calendar_id:
                    st.error("Missing MANAGED_CALENDAR_ID in environment.")
                else:
                    with st.spinner("Checking for conflicts..."):
                        report = run_conflict_agent(
                            st.session_state.generated_plan,
                            st.session_state.semester_window,
                            calendar_id,
                        )
                    st.session_state.conflict_report = report
                    st.success("Conflict check completed.")

            if st.session_state.conflict_report:
                report = st.session_state.conflict_report
                st.write(f"Blocking: {report.blocking}")
                if report.conflicts:
                    for idx, c in enumerate(report.conflicts, start=1):
                        st.markdown(f"**{idx}. {c.type}** - {c.summary}")
                        if c.affected:
                            st.write(f"Affected: {', '.join(c.affected)}")
                        if c.suggestions:
                            st.write("Suggestions:")
                            for s in c.suggestions:
                                st.write(f"- {s}")
                        st.markdown("---")
                else:
                    st.info("No conflicts detected.")
                st.subheader("Resolve conflicts")
                st.text_input("How would you like to resolve these conflicts?", key="conflict_resolution_note")

            st.markdown("---")
            st.subheader("Negotiation & Revision")
            if st.button("Auto-resolve conflicts (NegotiationAgent)"):
                if not st.session_state.generated_plan or not st.session_state.conflict_report:
                    st.error("Run planner and conflict detection first.")
                elif not calendar_id:
                    st.error("Missing MANAGED_CALENDAR_ID in environment.")
                else:
                    with st.spinner("Negotiating resolutions..."):
                        outcome = run_negotiation_agent(
                            st.session_state.generated_plan,
                            st.session_state.conflict_report,
                            calendar_id,
                        )
                    st.session_state.negotiation_outcome = outcome
                    st.session_state.generated_plan = outcome.updated_plan
                    st.session_state.execution_report = None
                    st.success("Negotiation complete. Plan updated.")
                    st.rerun()

            if st.session_state.negotiation_outcome:
                outcome = st.session_state.negotiation_outcome
                st.success("Negotiation complete. Plan updated.")
                if outcome.applied_resolutions:
                    st.write("Applied resolutions:")
                    for res in outcome.applied_resolutions:
                        st.markdown(
                            f"- Operation #{res.operation_index}: "
                            f"{res.suggested_start_iso} - {res.suggested_end_iso}"
                        )
                else:
                    st.info("No resolutions were applied.")
                st.write("Revised plan:")
                st.json(outcome.updated_plan.model_dump(), expanded=False)

            st.markdown("---")
            st.header("Phase 8 - Apply plan to Google Calendar")

            plan: MutationPlan | None = st.session_state.generated_plan

            if not plan:
                st.info("No plan in memory yet. Generate a plan first.")
            else:
                st.text("Current plan preview:")
                st.text(plan.preview)

                if st.button("Apply this plan to my managed calendar"):
                    with st.spinner("ExecutorAgent is applying the plan..."):
                        report: ExecutionReport = run_executor_agent(plan)
                    st.session_state.execution_report = report
                    st.success("Execution finished. See details below.")

            if st.session_state.execution_report:
                report: ExecutionReport = st.session_state.execution_report
                st.markdown("### Execution summary")
                st.write(f"Total ops: {report.total_ops}")
                st.write(f"Executed: {report.executed_ops}")
                st.write(f"Failed: {report.failed_ops}")

                rows = []
                for r in report.results:
                    rows.append(
                        {
                            "index": r.op_index,
                            "type": r.op_type,
                            "status": r.status,
                            "message": r.message,
                            "google_event_id": r.google_event_id or "",
                        }
                    )
                if rows:
                    st.table(rows)
                else:
                    st.info("No individual results recorded.")
