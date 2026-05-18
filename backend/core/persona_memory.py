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

    def add_preference(self, role: str, preference: str, llm=None):
        """
        Adds a new preference to a specific agent's persona.
        If an LLM instance is provided, it intelligently consolidates and de-conflicts preferences.
        """
        if role not in self.personas:
            self.personas[role] = []
        
        # Simple exact duplicate check
        if preference in self.personas[role]:
            return
            
        # Intelligent consolidation
        if llm and self.personas[role]:
            existing_prefs = "\n".join(f"- {p}" for p in self.personas[role])
            prompt = f"""You are an Agent Memory Consolidator for the {role} agent.
Your goal is to merge a new user instruction/preference into the existing set of instructions, resolving any conflicts.

RULES:
1. The NEW preference is absolute. If it contradicts any existing preference, the NEW preference wins and the old preference MUST be completely replaced or deleted.
2. Remove any duplicate, redundant, or obsolete instructions.
3. Keep the output extremely clear, concise, and direct.
4. Output ONLY the consolidated list of instructions as bullet points (starting with '-'). Do NOT include any introductory or concluding text.

Existing preferences:
{existing_prefs}

New preference to add:
- {preference}

Consolidated preferences:"""
            try:
                logger.info(f"Consolidating {role} persona preferences with LLM...")
                response = llm.invoke(prompt).strip()
                # Parse lines starting with '-' or '*'
                new_prefs = []
                for line in response.split("\n"):
                    line = line.strip()
                    if line.startswith("-"):
                        pref_text = line[1:].strip()
                        if pref_text:
                            new_prefs.append(pref_text)
                    elif line.startswith("*"):
                        pref_text = line[1:].strip()
                        if pref_text:
                            new_prefs.append(pref_text)
                
                if new_prefs:
                    self.personas[role] = new_prefs
                    logger.info(f"Successfully consolidated {role} persona. Current rules: {new_prefs}")
                else:
                    # Fallback if parsing failed
                    self.personas[role].append(preference)
            except Exception as e:
                logger.error(f"Failed to consolidate preferences via LLM: {e}")
                self.personas[role].append(preference)
        else:
            self.personas[role].append(preference)
            
        self._save_memory()
        logger.info(f"Saved {role} preference: '{preference}'")

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
