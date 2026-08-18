"""AI Agent for water supply recommendation from talk group transcript.

The agent:
1. Parses transcribed talk group messages
2. Extracts water requests (flow in L/min, incident location, hydrant mentions)
3. Tracks hydrant availability and status changes
4. Invokes the optimization engine
5. Returns a summary of recommendations and decisions

Run:
    python ai_agent.py --transcript path/to/transcript.txt --hydrants hydrant_database.csv
"""

import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import json


@dataclass
class WaterRequest:
    """Extracted water request from transcript."""
    timestamp: str
    speaker: str
    message: str
    required_flow_l_min: Optional[float] = None  # None if not specified
    location: Optional[str] = None
    hydrant_mentions: List[str] = field(default_factory=list)  # e.g., ["H-101", "H-102"]
    request_type: str = "initial"  # "initial", "update", "alternative", "fallback"
    raw_match: Optional[str] = None


@dataclass
class HydrantStatus:
    """Tracks hydrant status over time."""
    hydrant_id: str
    capacity_l_min: float
    location: Optional[str] = None
    status: str = "available"  # "available", "blocked", "failed", "deployed"
    blocked_reason: Optional[str] = None
    first_mention_time: Optional[str] = None
    last_update_time: Optional[str] = None


class TranscriptParser:
    """Parses transcribed talk group and extracts water requests and hydrant info."""
    
    # Regex patterns for flow extraction
    FLOW_PATTERNS = [
        r"(\d+)\s*(?:liters?|L|l)\s*(?:per\s*minute|/min|pm)",  # "500 L/min"
        r"need[s]?\s+(?:at\s+)?(?:least\s+)?(\d+)",  # "need 500" or "need at least 500"
        r"require[s]?\s+(?:at\s+)?(?:least\s+)?(\d+)",  # "require 500"
        r"flow\s+(?:of\s+)?(\d+)",  # "flow of 500"
        r"(\d+)\s*(?:gallons?|GPM|gpm)",  # "500 GPM"
    ]
    
    # Hydrant pattern: H-### or Hydrant ###
    HYDRANT_PATTERN = r"([H|Hydrant]\-?\d{3}|hydrant\s+\w+)"
    
    # Location patterns
    LOCATION_PATTERNS = [
        r"(?:at|location|address)[\s:]*([A-Za-z0-9\s\-.,#]+?)(?:\.|,|cross|$)",
        r"(\d+\s+[A-Za-z\s]+(?:Street|St|Road|Rd|Avenue|Ave|Gade|Vej))",
        r"coordinates?[\s:]*(\d+\.\d+),?\s*(\d+\.\d+)",  # GPS coordinates
    ]
    
    WATER_REQUEST_KEYWORDS = [
        "water", "hydrant", "supply", "flow", "pressure", "pump",
        "outlet", "intake", "L/min", "GPM", "gallons", "need", "require"
    ]
    
    IRRELEVANT_KEYWORDS = [
        "smørrebrød", "food", "lunch", "herring", "instagram", "photo",
        "nyhavn", "bike", "bicycle", "coffee", "cold tuborg", "get"
    ]
    
    def __init__(self):
        self.requests: List[WaterRequest] = []
        self.hydrant_status: Dict[str, HydrantStatus] = {}
    
    def is_water_request(self, message: str) -> bool:
        """Check if message is likely about water supply (not just casual chat)."""
        message_lower = message.lower()
        
        # Filter out pure casual chat
        if any(keyword in message_lower for keyword in self.IRRELEVANT_KEYWORDS):
            if not any(kw in message_lower for kw in self.WATER_REQUEST_KEYWORDS):
                return False
        
        return any(keyword in message_lower for keyword in self.WATER_REQUEST_KEYWORDS)
    
    def extract_flow(self, message: str) -> Optional[float]:
        """Extract required flow in L/min from message."""
        for pattern in self.FLOW_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                try:
                    flow_value = float(match.group(1))
                    # Convert GPM to L/min if needed (1 GPM ≈ 3.785 L/min)
                    if "GPM" in match.group(0).upper() or "gpm" in match.group(0):
                        flow_value *= 3.785
                    return flow_value
                except (ValueError, IndexError):
                    continue
        return None
    
    def extract_hydrants(self, message: str) -> List[str]:
        """Extract hydrant IDs mentioned in message."""
        matches = re.findall(self.HYDRANT_PATTERN, message, re.IGNORECASE)
        return [m.upper().replace("HYDRANT ", "H-") for m in matches]
    
    def extract_location(self, message: str) -> Optional[str]:
        """Extract location from message."""
        for pattern in self.LOCATION_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                if len(match.groups()) == 2 and match.group(1).replace(".", "").isdigit():
                    # GPS coordinates
                    return f"GPS: {match.group(1)}, {match.group(2)}"
                return match.group(1).strip()
        return None
    
    def detect_hydrant_status_change(self, message: str) -> Dict[str, str]:
        """Detect if message contains hydrant status updates."""
        changes = {}
        hydrants = self.extract_hydrants(message)
        
        message_lower = message.lower()
        
        if "blocked" in message_lower or "vehicle" in message_lower:
            for h in hydrants:
                changes[h] = "blocked"
        elif "clear" in message_lower or "towed" in message_lower:
            for h in hydrants:
                changes[h] = "available"
        elif "clogged" in message_lower or "failing" in message_lower or "failed" in message_lower:
            for h in hydrants:
                changes[h] = "failed"
        elif "deployed" in message_lower or "use" in message_lower:
            for h in hydrants:
                changes[h] = "deployed"
        
        return changes
    
    def parse_transcript(self, transcript_text: str) -> tuple:
        """Parse full transcript and extract all water requests + hydrant status.
        
        Expected format:
        [HH:MM:SS] Speaker: message text
        [HH:MM:SS] Speaker2: another message
        """
        lines = transcript_text.strip().split("\n")
        
        for line in lines:
            # Parse timestamp and message
            # Format: [HH:MM:SS] Speaker: message
            match = re.match(r"\[(\d{2}:\d{2}:\d{2})\]\s+([^:]+):\s*(.+)", line)
            if not match:
                continue
            
            timestamp, speaker, message = match.groups()
            
            # Track hydrant status changes
            status_changes = self.detect_hydrant_status_change(message)
            for hydrant_id, status in status_changes.items():
                if hydrant_id not in self.hydrant_status:
                    self.hydrant_status[hydrant_id] = HydrantStatus(
                        hydrant_id=hydrant_id,
                        capacity_l_min=0,  # Will be filled from database
                        first_mention_time=timestamp
                    )
                self.hydrant_status[hydrant_id].status = status
                self.hydrant_status[hydrant_id].last_update_time = timestamp
            
            # Check if this is a water-related request
            if not self.is_water_request(message):
                continue
            
            # Extract flow and location
            flow = self.extract_flow(message)
            location = self.extract_location(message)
            hydrants = self.extract_hydrants(message)
            
            # Determine request type
            request_type = "initial"
            if "update" in message.lower() or "change" in message.lower():
                request_type = "update"
            elif "alternative" in message.lower() or "instead" in message.lower():
                request_type = "alternative"
            elif "fallback" in message.lower() or "backup" in message.lower():
                request_type = "fallback"
            
            # Create request object
            request = WaterRequest(
                timestamp=timestamp,
                speaker=speaker,
                message=message,
                required_flow_l_min=flow,
                location=location,
                hydrant_mentions=hydrants,
                request_type=request_type,
                raw_match=message
            )
            
            self.requests.append(request)
        
        return self.requests, self.hydrant_status


class WaterSupplyAgent:
    """AI Agent for water supply recommendations."""
    
    def __init__(self, hydrant_database_path: Optional[str] = None):
        self.parser = TranscriptParser()
        self.recommendations: Dict[int, Any] = {}
        self.hydrant_database = {}
        
        if hydrant_database_path:
            self.load_hydrant_database(hydrant_database_path)
    
    def load_hydrant_database(self, csv_path: str):
        """Load hydrant database from CSV."""
        try:
            import pandas as pd
            df = pd.read_csv(csv_path)
            # Assuming columns: Hydrant, Capacity_L_min, Latitude, Longitude
            for _, row in df.iterrows():
                hydrant_id = row.get("Hydrant", row.get("ID", ""))
                capacity = float(row.get("Capacity_L_min", 0))
                lat = row.get("Latitude", None)
                lon = row.get("Longitude", None)
                
                self.hydrant_database[hydrant_id] = {
                    "capacity": capacity,
                    "latitude": lat,
                    "longitude": lon
                }
        except Exception as e:
            print(f"Warning: Could not load hydrant database: {e}")
    
    def process_transcript_text(self, transcript_text: str) -> Dict[str, Any]:
        """Process transcript text and generate recommendations.
        
        This is the main method used by the Streamlit app.
        
        Returns a dict with:
        - requests: extracted water requests
        - hydrant_timeline: how hydrants changed during incident
        - recommendations: optimization results for each request
        - summary: high-level overview
        """
        # Parse transcript
        requests, hydrant_status = self.parser.parse_transcript(transcript_text)
        
        results = {
            "transcript_file": "User input",
            "total_requests": len(requests),
            "requests": [],
            "hydrant_timeline": [],
            "recommendations": [],
            "decision_log": []
        }
        
        # Process each request
        for i, request in enumerate(requests):
            results["requests"].append({
                "id": i,
                "timestamp": request.timestamp,
                "speaker": request.speaker,
                "message": request.message,
                "required_flow_l_min": request.required_flow_l_min,
                "location": request.location,
                "hydrants_mentioned": request.hydrant_mentions,
                "request_type": request.request_type
            })
            
            # TODO: Call optimization engine here
            # recommendation = self.get_recommendation(request, hydrant_status)
            # results["recommendations"].append(recommendation)
        
        # Hydrant timeline
        for hydrant_id, status in sorted(hydrant_status.items()):
            results["hydrant_timeline"].append({
                "hydrant_id": hydrant_id,
                "status": status.status,
                "first_mention": status.first_mention_time,
                "last_update": status.last_update_time
            })
        
        return results
    
    def process_transcript(self, transcript_path: str) -> Dict[str, Any]:
        """Process transcript file and generate recommendations (CLI version)."""
        with open(transcript_path, 'r') as f:
            transcript_text = f.read()
        
        results = self.process_transcript_text(transcript_text)
        results["transcript_file"] = transcript_path
        
        return results
    
    def get_recommendation(self, request: WaterRequest, hydrant_status: Dict[str, HydrantStatus]) -> Dict[str, Any]:
        """Generate recommendation for a water request.
        
        TODO: Integrate with existing optimization engine (build_candidates, solve_model)
        """
        recommendation = {
            "request_id": request.timestamp,
            "required_flow": request.required_flow_l_min,
            "location": request.location,
            "hydrants_available": [h for h, s in hydrant_status.items() if s.status == "available"],
            # TODO: Add optimization results here
        }
        return recommendation


def main():
    """Main entry point."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python ai_agent.py --transcript <path/to/transcript.txt> [--hydrants <path/to/hydrants.csv>]")
        print("\nExample:")
        print("  python ai_agent.py --transcript Transcript.txt --hydrants hydrant_database.csv")
        sys.exit(1)
    
    transcript_path = None
    hydrant_path = None
    
    # Parse command line arguments
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--transcript" and i + 1 < len(sys.argv):
            transcript_path = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--hydrants" and i + 1 < len(sys.argv):
            hydrant_path = sys.argv[i + 1]
            i += 2
        else:
            i += 1
    
    if not transcript_path:
        print("Error: --transcript argument is required")
        sys.exit(1)
    
    agent = WaterSupplyAgent(hydrant_database_path=hydrant_path)
    results = agent.process_transcript(transcript_path)
    
    # Output results as JSON
    print(f"\n{'='*60}")
    print(f"RESULTS (JSON FORMAT)")
    print(f"{'='*60}\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
