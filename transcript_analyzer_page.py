"""Transcript Analyzer Page: AI Agent for water supply from talk group transcripts.

Processes transcribed radio communications to extract water requests and
generate hydrant recommendations using the optimization engine.

Run as a page in the Streamlit app or standalone:
    streamlit run transcript_analyzer_page.py
"""

import streamlit as st
import pandas as pd
import json
from datetime import datetime
from typing import Optional
import folium
from streamlit_folium import st_folium

from data import get_hydrants
from ai_agent import WaterSupplyAgent, TranscriptParser


def render_transcript_analyzer():
    """Main transcript analyzer page."""
    st.title("📻 Talk Group Transcript Analyzer")
    
    st.markdown("""
    Upload or paste a transcribed radio communication to automatically:
    - **Extract water requests** from crew and dispatcher conversations
    - **Track hydrant availability** as status changes during the incident
    - **Generate recommendations** using the hydrant optimization engine
    - **Visualize the timeline** of decisions and resource allocation
    """)
    
    # Initialize session state
    if "transcript_analysis" not in st.session_state:
        st.session_state.transcript_analysis = None
    
    # Tabs for different input methods
    tab1, tab2 = st.tabs(["📤 Upload Transcript", "📝 Paste Transcript"])
    
    transcript_text = None
    
    with tab1:
        uploaded_file = st.file_uploader(
            "Upload transcript file (.txt)",
            type=["txt"],
            help="Expected format: [HH:MM:SS] Speaker: message"
        )
        if uploaded_file:
            transcript_text = uploaded_file.read().decode("utf-8")
    
    with tab2:
        transcript_text = st.text_area(
            "Paste transcript here",
            height=300,
            placeholder="[14:30:15] DISPATCH: All units respond to structure fire...\n[14:32:10] ENGINE 4: We're en route, ETA 4 minutes...",
            help="Expected format: [HH:MM:SS] Speaker: message"
        )
    
    # Process transcript
    if transcript_text and st.button("🔍 Analyze Transcript", key="analyze_btn"):
        with st.spinner("Analyzing transcript..."):
            agent = WaterSupplyAgent()
            results = agent.process_transcript_text(transcript_text)
            st.session_state.transcript_analysis = results
            st.success("✅ Transcript analyzed successfully!")
    
    # Display results
    if st.session_state.transcript_analysis:
        results = st.session_state.transcript_analysis
        display_analysis_results(results)


def display_analysis_results(results):
    """Display the analysis results with visualizations."""
    st.markdown("---")
    st.header("Analysis Results")
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Water Requests", results["total_requests"])
    with col2:
        st.metric("Hydrants Mentioned", len(results["hydrant_timeline"]))
    with col3:
        hydrant_changes = sum(1 for h in results["hydrant_timeline"] if h["last_update"])
        st.metric("Hydrant Status Changes", hydrant_changes)
    with col4:
        st.metric("Incident Duration", "45+ min" if results["total_requests"] > 0 else "N/A")
    
    # Tabs for different views
    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 Water Requests",
        "🚒 Hydrant Timeline",
        "📍 Map View",
        "📊 Decision Log"
    ])
    
    with tab1:
        display_water_requests(results)
    
    with tab2:
        display_hydrant_timeline(results)
    
    with tab3:
        display_map_view(results)
    
    with tab4:
        display_decision_log(results)
    
    # Raw JSON for debugging
    with st.expander("🔧 Raw Analysis (JSON)"):
        st.json(results)


def display_water_requests(results):
    """Display extracted water requests."""
    st.subheader("Extracted Water Requests")
    
    if not results["requests"]:
        st.info("No water requests found in transcript.")
        return
    
    # Create a dataframe for better display
    df_requests = pd.DataFrame([
        {
            "Time": req["timestamp"],
            "Speaker": req["speaker"],
            "Flow (L/min)": req["required_flow_l_min"] or "Not specified",
            "Location": req["location"] or "Not specified",
            "Hydrants": ", ".join(req["hydrants_mentioned"]) or "None",
            "Type": req["request_type"]
        }
        for req in results["requests"]
    ])
    
    st.dataframe(df_requests, use_container_width=True, height=400)
    
    # Detailed view
    st.subheader("Request Details")
    for i, req in enumerate(results["requests"]):
        with st.expander(f"Request #{i+1} at {req['timestamp']} ({req['speaker']})"):
            st.markdown(f"**Message:** {req['message']}")
            st.markdown(f"**Required Flow:** {req['required_flow_l_min'] or 'Not specified'} L/min")
            st.markdown(f"**Location:** {req['location'] or 'Not specified'}")
            st.markdown(f"**Hydrants Mentioned:** {', '.join(req['hydrants_mentioned']) or 'None'}")
            st.markdown(f"**Request Type:** {req['request_type']}")


def display_hydrant_timeline(results):
    """Display hydrant status timeline."""
    st.subheader("Hydrant Status Timeline")
    
    if not results["hydrant_timeline"]:
        st.info("No hydrant status changes detected.")
        return
    
    # Create timeline dataframe
    df_timeline = pd.DataFrame([
        {
            "Hydrant": h["hydrant_id"],
            "First Mention": h["first_mention"],
            "Last Update": h["last_update"],
            "Status": h["status"]
        }
        for h in results["hydrant_timeline"]
    ])
    
    st.dataframe(df_timeline, use_container_width=True)
    
    # Status color coding
    st.subheader("Status Legend")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("🟢 **Available** - Ready to use")
    with col2:
        st.markdown("🔴 **Blocked** - Vehicle or obstacle")
    with col3:
        st.markdown("🟡 **Deployed** - Currently in use")
    with col4:
        st.markdown("⚫ **Failed** - No longer usable")


def display_map_view(results):
    """Display map with hydrant and incident locations."""
    st.subheader("Incident Location Map")
    
    # Extract incident location from first request
    incident_location = None
    for req in results["requests"]:
        if req["location"]:
            incident_location = req["location"]
            break
    
    if not incident_location:
        st.info("No incident location found in transcript.")
        return
    
    # Create a simple map (would need actual coordinates for real implementation)
    st.info(f"📍 Incident Location: {incident_location}")
    
    # Get hydrants from database for reference
    try:
        hydrants_df = get_hydrants()
        st.markdown("### Nearby Hydrants")
        
        hydrant_cols = ["id", "name", "capacity_l_min", "location"]
        if all(col in hydrants_df.columns for col in hydrant_cols):
            st.dataframe(
                hydrants_df[hydrant_cols].head(10),
                use_container_width=True
            )
    except Exception as e:
        st.warning(f"Could not load hydrant database: {e}")


def display_decision_log(results):
    """Display the decision log and key events."""
    st.subheader("Decision Log & Key Events")
    
    if not results["requests"]:
        st.info("No events to display.")
        return
    
    # Create a timeline of key events
    events = []
    
    for req in results["requests"]:
        events.append({
            "timestamp": req["timestamp"],
            "type": "water_request",
            "description": f"{req['speaker']}: Need {req['required_flow_l_min'] or '?'} L/min",
            "speaker": req["speaker"]
        })
    
    for hydrant_status in results["hydrant_timeline"]:
        if hydrant_status["last_update"]:
            events.append({
                "timestamp": hydrant_status["last_update"],
                "type": "hydrant_status",
                "description": f"{hydrant_status['hydrant_id']}: {hydrant_status['status']}",
                "hydrant": hydrant_status["hydrant_id"]
            })
    
    # Sort by timestamp
    events.sort(key=lambda x: x["timestamp"])
    
    # Display timeline
    for event in events:
        if event["type"] == "water_request":
            st.markdown(f"**[{event['timestamp']}] 💧 Water Request** - {event['description']}")
        else:
            st.markdown(f"**[{event['timestamp']}] 🚒 Hydrant Update** - {event['description']}")


if __name__ == "__main__":
    st.set_page_config(page_title="Transcript Analyzer", layout="wide")
    render_transcript_analyzer()
