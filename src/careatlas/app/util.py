import subprocess
import socket
import time
import logging
import atexit
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional
import httpx
import asyncio
from dataclasses import replace
import psutil, os, signal
import os
from typing import Optional

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
    
    def __repr__(self):
        return f'session: {self.session_id} -->{self.base_url}:{self.port} from {self.notebook_path}'



class MarimoProcessWrapper:
    
    """Wraps psutil.Process to look like a subprocess.Popen object."""
    def __init__(self, pid: int):
        self._proc = psutil.Process(pid)
        self.returncode = None

    def poll(self) -> Optional[int]:
        try:
            # Reaping: Treat zombies or dead processes as terminated
            if not self._proc.is_running() or self._proc.status() == psutil.STATUS_ZOMBIE:
                self.returncode = 0
                return 0
            return None
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self.returncode = 0
            return 0

    def terminate(self):
        """Finds all children (the kernels) and kills them first."""
        try:
            # Get all descendants (recursive=True handles nested forks)
            descendants = self._proc.children(recursive=True)
            print('DESCDDDDDD')
            
            for child in descendants:
                child.terminate()
            
            # Now kill the main marimo process
            self._proc.terminate()
            
            # Wait a split second for them to exit the OS table
            _, alive = psutil.wait_procs(descendants + [self._proc], timeout=3)
            for p in alive:
                p.kill() # Force kill if they are stubborn
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    def kill(self):
        """Force kill everything if terminate fails."""
        try:
            children = self._proc.children(recursive=True)
            for child in children:
                try: child.kill()
                except: pass
            self._proc.kill()
        except:
            pass

    def wait(self, timeout: Optional[float] = None) -> int:
        """Wait for the process to terminate. Matches subprocess.Popen.wait."""
        try:
            # psutil.wait returns the exit code
            self.returncode = self._proc.wait(timeout=timeout)
            return self.returncode
        except Exception:
            # If it times out or is already gone, return 0 to stop the manager from hanging
            return 0


        
class MarimoManager:
    def __init__(self):
        self._sessions: Dict[str, MarimoSession] = {}
    
    async def startup(self):
        """
        2. Offload the heavy OS scanning to an async wrapper.
        asyncio.to_thread runs the synchronous psutil loops in a separate 
        worker thread so they do not block the ASGI server boot.
        """
        logger.info("Initializing MarimoManager state...")
        await asyncio.to_thread(self.reap_orphans_and_zombies)
        await asyncio.to_thread(self.discover_running_sessions)

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
        upstream_host: str = "127.0.0.1",
        identity: dict[str, str] = None
    ) -> MarimoSession:
        if session_id in self._sessions:
            logger.warning(f"Session {session_id} already exists. Returning existing.")
            return self._sessions[session_id]
        
        nb_path = Path(notebook).resolve()
        if not nb_path.exists():
            raise FileNotFoundError(f"Notebook not found at {nb_path}")
        if identity:
            env = os.environ.copy()
            # These variables will be picked up by Git inside the Marimo terminal/notebook
            env["GIT_AUTHOR_NAME"] = identity["user"]
            env["GIT_AUTHOR_EMAIL"] = identity["email"]
            env["GIT_COMMITTER_NAME"] = identity["user"]
            env["GIT_COMMITTER_EMAIL"] = identity["email"]

        port = self._get_free_port()
        base_url = f"{base_prefix}/{session_id}"
        logger.info(f'Creating marimo svc at {base_url}')
        # Command construction
        cmd = [
            "marimo", "edit", str(nb_path),
            "--host", "0.0.0.0",
            "--port", str(port),
            "--base-url", base_url,
            "--proxy", "localhost:8080",
            "--headless",
            "--no-token",
            # Automatically terminate the kernel after 2 hours of inactivity
            "--timeout", "7200"
            
        ]

        logger.debug(f"Starting Marimo session '{session_id}' on port {port}...")
        
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL, # Keep logs clean, or redirect to file
            stderr=subprocess.PIPE,
            text=True,
            env=env
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

    # def stop_session(self, session_id: str, proc_override: Optional[subprocess.Popen] = None) -> None:
    #     """Gracefully stops a session and cleans up resources."""
    #     session = self._sessions.pop(session_id, None)
    #     proc = proc_override or (session.proc if session else None)

    #     if not proc:
    #         return

    #     try:
    #         proc.terminate()
    #         proc.wait(timeout=5)
    #     except subprocess.TimeoutExpired:
    #         logger.info(f"Session {session_id} refused to terminate. Killing...")
    #         proc.kill()
    #     except Exception as e:
    #         logger.error(f"Error closing session {session_id}: {e}")
    
    def stop_session(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if not session or not session.proc:
            return

        # 1. Safely extract PID whether it's Popen or MarimoProcessWrapper
        pid = getattr(session.proc, 'pid', None) 
        if not pid and hasattr(session.proc, '_proc'):
            pid = session.proc._proc.pid

        if pid:
            try:
                parent = psutil.Process(pid)
                # Get ALL descendants (the kernels)
                children = parent.children(recursive=True)
                
                # 2. Terminate gracefully first (SIGTERM)
                for child in children:
                    child.terminate()
                parent.terminate()
                
                # 3. Wait up to 3 seconds for them to clean up and exit
                _, alive = psutil.wait_procs(children + [parent], timeout=3)
                
                # 4. Force kill (SIGKILL) any stubborn survivors
                for p in alive:
                    p.kill()
                    
            except psutil.NoSuchProcess:
                pass # Process is already gone
            except Exception as e:
                logger.error(f"Cleanup error for {session_id}: {e}")

        # 5. THE ZOMBIE REAPER: You MUST call .wait() to release the PID
        try:
            if hasattr(session.proc, 'wait'):
                # This reads the exit code and removes the defunct entry from the OS
                session.proc.wait(timeout=2)
        except Exception:
            pass

    def shutdown_all(self) -> None:
        """Stops all managed sessions. Useful for cleanup."""
        if not self._sessions:
            return
        logger.info(f"Shutting down {len(self._sessions)} active sessions...")
        for sid in list(self._sessions.keys()):
            self.stop_session(sid)
        self.reap_orphans_and_zombies()
            
    def touch(self, session_id: str):
        """Update activity time to prevent reaping."""
        if session := self._sessions.get(session_id):
            session.last_activity = time.time()

    async def cleanup_loop(self, max_idle_seconds: int = 3600*12):
        """
        The 'Reaper' task. Runs periodically to:
        1. Kill sessions that haven't seen traffic.
        2. Remove sessions where the process crashed (Zombies).
        """
        while True:
            await asyncio.sleep(60) 
            
            # --- PHASE 0: OS REAPING ---
            # Clear any zombies that might exist, even those not in self._sessions
            try:
                # -1 reaps any child. WNOHANG prevents blocking.
                while True:
                    pid, status = os.waitpid(-1, os.WNOHANG)
                    if pid == 0: break # No more zombies to reap right now
                    logger.info(f"OS Maintenance: Reaped zombie process {pid}")
            except ChildProcessError:
                # No child processes exist at all, perfectly fine
                pass

            logger.debug(f'Active Managed Sessions: {len(self._sessions)}')
            
            # --- PHASE 1: SESSION MANAGEMENT ---
            for sid in list(self._sessions.keys()):
                session = self._sessions.get(sid)
                if not session:
                    continue

                # Reason 1: Process died or became a zombie
                # Our Wrapper's .poll() now identifies zombies as 'dead'
                if not session.is_alive:
                    logger.info(f"Session {sid} is no longer alive. Cleaning up.")
                    self.stop_session(sid)
                    continue

                # Reason 2: User hasn't interacted in a while
                # We use the method from your MarimoSession class
                if (time.time() - session.last_activity) > max_idle_seconds:
                    logger.info(f"Reaping idle session {sid} after {max_idle_seconds}s.")
                    self.stop_session(sid)
                    
    def reap_orphans_and_zombies(self):
        """
        Finds any process named 'marimo' that is a zombie 
        or belongs to this process group and cleans it up.
        """
        logger.info("Maintenance: Reaping zombie processes...")
        for p in psutil.process_iter(['pid', 'status', 'name']):
            try:
                # Check for Zombies specifically
                if p.info['status'] == psutil.STATUS_ZOMBIE:
                    # 'waitpid' with -1 reaps any child. WNOHANG makes it non-blocking.
                    os.waitpid(p.info['pid'], os.WNOHANG)
                    logger.info(f"Successfully reaped zombie PID {p.info['pid']}")
            except (psutil.NoSuchProcess, ChildProcessError):
                continue
                    
    def discover_running_sessions(self) -> None:
        """Scan OS processes to reconstruct the manager state on startup."""
        import psutil
        logger.info("Scanning for orphaned Marimo sessions...")
        
        # We request 'pid' and 'cmdline' to efficiently grab the launch arguments
        for p in psutil.process_iter(['pid', 'cmdline']):
            try:
                # Add this check right after grabbing the process status
                if p.status() == psutil.STATUS_ZOMBIE:
                    continue
                
                cmdline = p.info.get('cmdline') or []
                
                # Match the exact process signature from your docker output
                if len(cmdline) < 4 or 'marimo' not in cmdline[1]:
                    continue
                if cmdline[2] != 'edit':
                    continue
                
                # Grab the notebook path (Index 3 based on your ps aux)
                notebook_path = cmdline[3]
                try:
                    port = int(cmdline[cmdline.index('--port') + 1])
                    base_url = cmdline[cmdline.index('--base-url') + 1]
                    session_id = base_url.split('/')[-1]
                except (ValueError, IndexError):
                    logger.warning(f"Found marimo process PID {p.info['pid']} but couldn't parse args. Skipping.")
                    continue

                # The 'not in' check automatically handles the duplicate parent/child processes
                if session_id not in self._sessions:
                    session = MarimoSession(
                        session_id=session_id,
                        port=port,
                        # Adopt the existing OS process using its PID
                        proc=MarimoProcessWrapper(p.info['pid']),
                        base_url=base_url,
                        notebook_path=notebook_path
                    )
                    self._sessions[session_id] = session
                    logger.info(f"Recovered session {session_id} on port {port} (PID {p.info['pid']})")
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # Safely ignore processes we don't have permission to read or that just died
                continue
                    
# Example Usage:
if __name__ == "__main__":
    manager = MarimoManager()
    try:
        session = manager.start_session("research-01", "analysis.py")
        print(f"Session live at: {session.base_url} (Port {session.port})")
    except Exception as e:
        print(f"Failed: {e}")