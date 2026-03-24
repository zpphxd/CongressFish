"""Load Congress member personas from JSON files."""

import json
from pathlib import Path
from typing import Dict, List, Optional


class PersonaLoader:
    """Load and cache Congress member persona profiles."""

    def __init__(self):
        """Initialize persona loader."""
        self.personas: Dict[str, Dict] = {}
        self.personas_dir = Path(__file__).parent.parent / "agents" / "personas" / "congress"
        self._load_all_personas()

    def _load_all_personas(self):
        """Load all persona JSON files from house and senate directories."""
        for chamber_dir in ["house", "senate"]:
            chamber_path = self.personas_dir / chamber_dir
            if chamber_path.exists():
                for json_file in chamber_path.glob("*.json"):
                    bioguide_id = json_file.stem
                    try:
                        with open(json_file, "r") as f:
                            self.personas[bioguide_id] = json.load(f)
                    except Exception as e:
                        print(f"Warning: Failed to load {json_file}: {e}")

    def get_persona(self, bioguide_id: str) -> Optional[Dict]:
        """Get a persona by bioguide ID."""
        return self.personas.get(bioguide_id)

    def get_personas_by_chamber(self, chamber: str) -> List[Dict]:
        """Get all personas for a chamber (House or Senate)."""
        result = []
        # Normalize chamber name to lowercase
        chamber_lower = chamber.lower()
        for bioguide_id, persona in self.personas.items():
            if persona.get("chamber", "").lower() == chamber_lower:
                result.append(persona)
        return result

    def get_personas_by_party(self, party: str) -> List[Dict]:
        """Get personas by party (D/R/I)."""
        result = []
        for persona in self.personas.values():
            if persona.get("party") == party:
                result.append(persona)
        return result

    @property
    def total_personas(self) -> int:
        """Total number of loaded personas."""
        return len(self.personas)
