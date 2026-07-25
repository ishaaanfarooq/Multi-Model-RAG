import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)


class WorkspaceAgent:
    """
    A file agent confined to a single workspace directory.

    This is the highest-privilege capability in Praxis — it writes real files — so it is
    deliberately boxed in:
      - Every path is resolved and checked to stay INSIDE the workspace dir. A model that
        emits "../../etc/passwd" or "/home/user/.ssh/id_rsa" is rejected; it can only ever
        touch praxis-workspace/.
      - There is no shell. It can create/edit/read/list files and open them in VS Code —
        nothing else. It cannot run commands, delete outside the box, or reach the system.
      - Like the messaging actions, it only ever DRAFTS. The orchestrator produces a draft;
        a human approves before anything is written to disk.

    Files land on the host (the workspace is a bind-mounted / real folder), so "make this
    file" produces something you can actually open and use.
    """

    def __init__(self, workspace_dir: str = None):
        if workspace_dir is None:
            workspace_dir = os.getenv("WORKSPACE_DIR", "praxis-workspace")
        self.workspace_dir = os.path.realpath(workspace_dir)
        self._init_error = None
        try:
            os.makedirs(self.workspace_dir, exist_ok=True)
            logger.info(f"Workspace agent ready at {self.workspace_dir}")
        except Exception as e:
            self._init_error = f"Workspace dir not writable: {e}"
            logger.error(self._init_error)

    @property
    def available(self) -> bool:
        return self._init_error is None

    # ── path safety ───────────────────────────────────────────────────────────
    def _safe_path(self, rel_path: str) -> str:
        """
        Resolve `rel_path` under the workspace and refuse anything that escapes it.
        Raises ValueError on traversal / absolute paths pointing outside.
        """
        if not rel_path or not rel_path.strip():
            raise ValueError("No filename given.")
        raw = rel_path.strip()
        # Reject absolute / home paths outright — a model emitting /etc/passwd or
        # ~/.ssh/id_rsa clearly intends to escape, so refuse rather than silently
        # rewriting it into the workspace.
        if os.path.isabs(raw) or raw[0] in ("/", "\\", "~"):
            raise ValueError(
                f"'{rel_path}' must be a relative path inside praxis-workspace/."
            )
        base = self.workspace_dir
        target = os.path.realpath(os.path.join(base, raw))
        # Final backstop: catches ../ traversal after resolution.
        if target != base and not target.startswith(base + os.sep):
            raise ValueError(
                f"'{rel_path}' points outside the workspace. Files can only be written "
                "inside praxis-workspace/."
            )
        return target

    def rel(self, abs_path: str) -> str:
        """workspace-relative display path"""
        return os.path.relpath(abs_path, self.workspace_dir)

    # ── operations ─────────────────────────────────────────────────────────────
    def write_file(self, rel_path: str, content: str) -> dict:
        if not self.available:
            raise RuntimeError(self._init_error)
        target = self._safe_path(rel_path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        existed = os.path.exists(target)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Wrote {'(overwrote) ' if existed else ''}{self.rel(target)} ({len(content)} chars)")
        return {"path": self.rel(target), "abs_path": target, "overwrote": existed, "bytes": len(content)}

    def read_file(self, rel_path: str) -> str:
        if not self.available:
            raise RuntimeError(self._init_error)
        target = self._safe_path(rel_path)
        if not os.path.isfile(target):
            raise FileNotFoundError(f"{rel_path} does not exist in the workspace.")
        with open(target, encoding="utf-8", errors="replace") as f:
            return f.read()

    def list_files(self) -> list[str]:
        if not self.available:
            return []
        out = []
        for root, _dirs, files in os.walk(self.workspace_dir):
            for name in files:
                out.append(self.rel(os.path.join(root, name)))
        return sorted(out)

    def open_in_editor(self, rel_path: str) -> str:
        """
        Open a workspace file in VS Code via the `code` CLI. Only works when the backend
        runs natively (with `code` on PATH) — inside Docker there's no host GUI, so this
        no-ops with a note. The file is still written either way.
        """
        target = self._safe_path(rel_path)
        code_bin = shutil.which("code")
        if not code_bin:
            return "VS Code CLI ('code') not available here — run the backend natively to auto-open."
        try:
            subprocess.Popen([code_bin, target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Opened {self.rel(target)} in VS Code."
        except Exception as e:
            return f"Could not launch VS Code: {e}"
