import subprocess
import socket
import time
import logging
import atexit
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Optional
import httpx
import asyncio
from dataclasses import replace

logger = logging.getLogger("marimo-manager")

@dataclass()
class MarimoSession:
    session_id: str
    port: int
    proc: subprocess.Popen
    base_url: str
    notebook_path: str
    # State - mutable for performance
    last_activity: float = field(default_factory=time.time)
    started_at: float = field(default_factory=time.time)

    def is_expired(self, threshold_seconds: int) -> bool:
        """Helper to keep the manager logic clean."""
        return (time.time() - self.last_activity) > threshold_seconds
    @property
    def is_alive(self) -> bool:
        """Check if the underlying process is actually running."""
        return self.proc.poll() is None
    
    
    
    
class MarimoManager:
    def __init__(self):
        self._sessions: Dict[str, MarimoSession] = {}
        # Ensure cleanup on script exit
        atexit.register(self.shutdown_all)

    def _get_free_port(self) -> int:
        """Standard trick to get an ephemeral port from the OS."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def _is_server_ready(self, url: str) -> bool:
        """Internal health check helper."""
        try:
            with httpx.Client(timeout=1) as client:
                # Marimo returns 200/302 for the root path
                response = client.get(url)
                return response.status_code < 500
        except httpx.RequestError:
            return False

    def start_session(
        self,
        session_id: str,
        notebook: str,
        base_prefix: str = "/",
        timeout: float = 10.0,
        upstream_host: str = "127.0.0.1"
    ) -> MarimoSession:
        if session_id in self._sessions:
            logger.warning(f"Session {session_id} already exists. Returning existing.")
            return self._sessions[session_id]

        nb_path = Path(notebook).resolve()
        if not nb_path.exists():
            raise FileNotFoundError(f"Notebook not found at {nb_path}")

        port = self._get_free_port()
        base_url = f"{base_prefix}/{session_id}"
        
        # Command construction
        cmd = [
            "marimo", "edit", str(nb_path),
            "--host", str(upstream_host),
            "--port", str(port),
            "--headless",
            "--no-token",
            "--base-url", base_url
        ]

        logger.info(f"Starting Marimo session '{session_id}' on port {port}...")
        
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL, # Keep logs clean, or redirect to file
            stderr=subprocess.PIPE,
            text=True
        )

        # Polling for readiness
        start_time = time.time()
        health_url = f"http://{upstream_host}:{port}{base_url}"
        
        while time.time() - start_time < timeout:
            if proc.poll() is not None:
                _, err = proc.communicate()
                raise RuntimeError(f"Process exited immediately: {err}")
            
            if self._is_server_ready(health_url):
                session = MarimoSession(
                    session_id=session_id,
                    port=port,
                    proc=proc,
                    base_url=base_url,
                    notebook_path=str(nb_path)
                )
                self._sessions[session_id] = session
                return session
            
            time.sleep(0.2)

        self.stop_session(session_id, proc_override=proc)
        raise TimeoutError(f"Marimo failed to start within {timeout}s")

    def stop_session(self, session_id: str, proc_override: Optional[subprocess.Popen] = None) -> None:
        """Gracefully stops a session and cleans up resources."""
        session = self._sessions.pop(session_id, None)
        proc = proc_override or (session.proc if session else None)

        if not proc:
            return

        try:
            proc.terminate()
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.info(f"Session {session_id} refused to terminate. Killing...")
            proc.kill()
        except Exception as e:
            logger.error(f"Error closing session {session_id}: {e}")

    def shutdown_all(self) -> None:
        """Stops all managed sessions. Useful for cleanup."""
        if not self._sessions:
            return
        logger.info(f"Shutting down {len(self._sessions)} active sessions...")
        for sid in list(self._sessions.keys()):
            self.stop_session(sid)
            
    def touch(self, session_id: str):
        """Update activity time to prevent reaping."""
        if session := self._sessions.get(session_id):
            session.last_activity = time.time()

    async def cleanup_loop(self, max_idle_seconds: int = 1800):
        """
        The 'Reaper' task. Runs periodically to:
        1. Kill sessions that haven't seen traffic.
        2. Remove sessions where the process crashed (Zombies).
        """
        while True:
            await asyncio.sleep(60) # Check every 30 seconds
            logger.info(f'Available sessions: {len(self._sessions) }')
            
            # Use a list to avoid 'dictionary changed size during iteration' errors
            session_ids = list(self._sessions.keys())
            
            for sid in session_ids:
                session = self._sessions.get(sid)
                if not session:
                    continue

                # Reason 1: Process died on its own
                if not session.is_alive:
                    exit_code = session.proc.returncode
                    logger.info(f"Session {sid} died unexpectedly (code {exit_code}). Cleaning up.")
                    self.stop_session(sid)
                    continue

                # Reason 2: User hasn't interacted in a while
                if session.seconds_since_activity() > max_idle_seconds:
                    logger.info(f"Reaping idle session {sid} after {max_idle_seconds}s of inactivity.")
                    self.stop_session(sid)
                    
# Example Usage:
if __name__ == "__main__":
    manager = MarimoManager()
    try:
        session = manager.start_session("research-01", "analysis.py")
        print(f"Session live at: {session.base_url} (Port {session.port})")
    except Exception as e:
        print(f"Failed: {e}")