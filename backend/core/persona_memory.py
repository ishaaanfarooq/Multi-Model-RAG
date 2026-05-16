import os
import json
import logging

logger = logging.getLogger(__name__)

class AgentPersonaMemory:
    """
    Manages persistent, role-based memory for agents.
    Allows agents to learn and evolve based on user preferences.
    """
    def __init__(self, memory_file: str = "agent_personas.json"):
        self.memory_file = memory_file
        self.personas = self._load_memory()

    def _load_memory(self) -> dict:
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load persona memory: {e}")
        return {"Visualizer": [], "Generator": []}

    def _save_memory(self):
        try:
            with open(self.memory_file, "w") as f:
                json.dump(self.personas, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save persona memory: {e}")

    def add_preference(self, role: str, preference: str):
        """
        Adds a new preference to a specific agent's persona.
        """
        if role not in self.personas:
            self.personas[role] = []
        
        # Avoid exact duplicates
        if preference not in self.personas[role]:
            self.personas[role].append(preference)
            self._save_memory()
            logger.info(f"Added new preference to {role} persona: {preference}")

    def get_persona_context(self, role: str) -> str:
        """
        Returns the formatted persona context for a given agent.
        """
        preferences = self.personas.get(role, [])
        if not preferences:
            return ""
        
        context = f"USER PREFERENCES FOR {role.upper()}:\n"
        for i, pref in enumerate(preferences, 1):
            context += f"{i}. {pref}\n"
        return context
