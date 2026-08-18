"""AI Agent for water supply recommendation from talk group transcript.

The agent:
1. Parses transcribed talk group messages
2. Extracts water requests (flow in L/min, incident location)
3. Invokes the optimization engine
4. Returns a summary of recommendations

Run:
    python ai_agent.py --transcript path/to/transcript.txt
"""

import re
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import json


@dataclass
class WaterRequest:
    """Extracted water request from transcript."""
    timestamp: str
    speaker: str
    message: str
    required_flow_l_min: Optional[float]  # None if not specified
    location: Optional[str]
    raw_match: Optional[str]  # The matched text


class TranscriptParser:
    """Parses transcribed talk group and extracts water requests."""
    
    # Regex patterns to detect water requests
    FLOW_PATTERNS = [
        r"(\d+)\s*(?:liters?|L|l)\s*(?:per\s*minute|/min|pm)",  # "500 L/min"
        r"(?:need|require|request|supply)\s*(\d+)\s*(?:L|liters?)",  # "need 500 L"
        r"(\d+)\s*(?:gallons?|GPM|gpm)",  # "500 GPM"
    ]
    
    LOCATION_PATTERNS = [
        r"(?:at|near|location|address|coordinates?)[\s:]*([A-Za-z0-9\s\-.,#]+)",
        r"(?:fire\s+)?(?:at|location)[\s:]*([A-Za-z0-9\s\-.,#]+?)(?:\.|,|$)",
    ]
    
    WATER_REQUEST_KEYWORDS = [
        "water", "hydrant", "supply", "flow", "pressure", "pump",
        "outlet", "intake", "L/min", "GPM", "gallons"
    ]
    
    def __init__(self):
        self.requests: List[WaterRequest] = []
    
    def is_water_request(self, message: str) -> bool:
        """Check if message is likely about water supply."""
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in self.WATER_REQUEST_KEYWORDS)
    
    def extract_flow(self, message: str) -> Optional[float]:
        """Extract required flow in L/min from message."""
        for pattern in self.FLOW_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                flow_value = float(match.group(1))
                # Convert GPM to L/min if needed (1 GPM ≈ 3.785 L/min)
                if "GPM" in match.group(0).upper() or "gpm" in match.group(0):
                    flow_value *= 3.785
                return flow_value
        return None
    
    def extract_location(self, message: str) -> Optional[str]:
        """Extract location from message."""
        for pattern in self.LOCATION_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None
    
    def parse_transcript(self, transcript_text: str) -> List[WaterRequest]:
        """Parse full transcript and extract all water requests.
        
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
            
            # Check if this is a water-related request
            if not self.is_water_request(message):
                continue
            
            # Extract flow and location
            flow = self.extract_flow(message)
            location = self.extract_location(message)
            
            # Create request object
            request = WaterRequest(
                timestamp=timestamp,
                speaker=speaker,
                message=message,
                required_flow_l_min=flow,
                location=location,
                raw_match=message
            )
            
            self.requests.append(request)
        
        return self.requests


class WaterSupplyAgent:
    """AI Agent for water supply recommendations."""
    
    def __init__(self):
        self.parser = TranscriptParser()
        self.recommendations: Dict[int, Any] = {}
    
    def process_transcript(self, transcript_path: str) -> Dict[str, Any]:
        """Process transcript and generate recommendations.
        
        Returns a dict with:
        - requests: extracted water requests
        - recommendations: optimization results for each request
        - summary: high-level overview
        """
        with open(transcript_path, 'r') as f:
            transcript_text = f.read()
        
        # Parse transcript
        requests = self.parser.parse_transcript(transcript_text)
        
        print(f"\n=== Water Supply Agent ===")
        print(f"Transcript: {transcript_path}")
        print(f"Extracted {len(requests)} water request(s)\n")
        
        results = {
            "transcript_file": transcript_path,
            "total_requests": len(requests),
            "requests": [],
            "recommendations": []
        }
        
        # TODO: For each request, invoke the optimization engine
        for i, request in enumerate(requests):
            print(f"Request #{i+1}:")
            print(f"  Time: {request.timestamp}")
            print(f"  Speaker: {request.speaker}")
            print(f"  Message: {request.message}")
            print(f"  Required flow: {request.required_flow_l_min or 'Not specified'} L/min")
            print(f"  Location: {request.location or 'Not specified'}")
            print()
            
            results["requests"].append({
                "id": i,
                "timestamp": request.timestamp,
                "speaker": request.speaker,
                "message": request.message,
                "required_flow_l_min": request.required_flow_l_min,
                "location": request.location
            })
            
            # TODO: Call optimization engine here
            # recommendation = self.get_recommendation(request)
            # results["recommendations"].append(recommendation)
        
        return results


def main():
    """Main entry point."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python ai_agent.py --transcript <path/to/transcript.txt>")
        print("\nExample transcript format:")
        print("[00:00:15] Dispatcher: We have a structure fire at 123 Main St")
        print("[00:00:22] Crew A: Need 500 L/min water supply")
        print("[00:00:30] Dispatcher: Checking nearest hydrants...")
        sys.exit(1)
    
    if sys.argv[1] == "--transcript" and len(sys.argv) > 2:
        transcript_path = sys.argv[2]
        agent = WaterSupplyAgent()
        results = agent.process_transcript(transcript_path)
        
        # Output results as JSON
        print("\n=== Results (JSON) ===")
        print(json.dumps(results, indent=2))
    else:
        print("Invalid arguments")
        sys.exit(1)


if __name__ == "__main__":
    main()
