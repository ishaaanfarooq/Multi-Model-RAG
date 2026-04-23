import os
import datetime

class NotebookMemory:
    """
    Manages a persistent 'Notebook' of AI discoveries and session history.
    """
    def __init__(self, notebook_path: str = "analytical_notebook.md"):
        self.notebook_path = notebook_path
        
    def save_entry(self, query: str, answer: str, sources: list[str] = None):
        """
        Appends a new analytical entry to the notebook.
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"## [{timestamp}] Analysis: {query}\n\n"
        entry += f"### Synthesis\n{answer}\n\n"
        
        if sources:
            entry += "### Sources\n"
            for src in sources:
                entry += f"- {src}\n"
            entry += "\n"
            
        entry += "---\n\n"
        
        with open(self.notebook_path, "a") as f:
            f.write(entry)
            
    def get_notebook_content(self) -> str:
        """
        Returns the full content of the notebook.
        """
        if not os.path.exists(self.notebook_path):
            return "Notebook is empty."
        with open(self.notebook_path, "r") as f:
            return f.read()
