"""MLX Server Process Manager
Handles starting/stopping mlx_lm.server subprocesses for agents.
Each agent gets its own mlx_lm.server instance with its configured model/adapter.
"""

 

import asyncio

import subprocess

import signal

import httpx

from typing import Dict, Optional

from uuid import UUID

from pathlib import Path

 

# TODO: Import Agent model

# from backend.db.models.agent import Agent

 

 

class MLXServerProcess:

    """Represents a running mlx_lm.server instance"""

 

    def __init__(self, agent_id: UUID, process: subprocess.Popen, port: int):

        self.agent_id = agent_id

        self.process = process

        self.port = port

        self.started_at = None  # TODO: Add timestamp

 

    def is_running(self) -> bool:

        """Check if process is still running"""

        return self.process.poll() is None

 

    async def stop(self, timeout: int = 10):

        """Gracefully stop the MLX server

 

        Args:

            timeout: Seconds to wait before force-killing

        """

        if not self.is_running():

            return

 

        # Try graceful shutdown first

        self.process.terminate()

 

        try:

            self.process.wait(timeout=timeout)

        except subprocess.TimeoutExpired:

            # Force kill if graceful shutdown failed

            self.process.kill()

            self.process.wait()

 

    def get_logs(self, lines: int = 50) -> str:

        """Get recent log output from the process"""

        log_file = Path("logs") / f"mlx_server_{self.agent_id}.log"

        if log_file.exists():

            with open(log_file, 'r') as f:

                all_lines = f.readlines()

                return ''.join(all_lines[-lines:])

        return "No log file found"

 

 

class MLXManager:

    """Manages MLX server processes for all agents

 

    Singleton that tracks which agents have running servers.

    Ensures only one server per agent, handles cleanup on shutdown.

    """

 

    def __init__(self):

        self._processes: Dict[UUID, MLXServerProcess] = {}

        self._port_range_start = 8080  # First port to try

        self._port_range_end = 8180    # Last port to try

        self._used_ports = set()

 

    def _find_available_port(self) -> int:

        """Find an available port for mlx_lm.server

 

        TODO: Actually check if port is available, not just unused by us

        """

        for port in range(self._port_range_start, self._port_range_end):

            if port not in self._used_ports:

                return port

        raise RuntimeError("No available ports for MLX server")

 

    async def start_agent_server(self, agent, port_override: int = None) -> MLXServerProcess:  # TODO: agent: Agent

        """Start mlx_lm.server for an agent



        Uses agent's configuration to launch server with:

        - Configured model path

        - Optional adapter path

        - LLM generation parameters



        Args:

            agent: Agent configuration object

            port_override: Optional specific port to use (for special services like memory coordinator)



        Returns:

            MLXServerProcess instance tracking the running server



        Raises:

            RuntimeError: If agent already has a running server

            FileNotFoundError: If model/adapter paths don't exist

        """

        agent_id = agent.id  # TODO: Remove when Agent is imported



        # Check if already running

        if agent_id in self._processes and self._processes[agent_id].is_running():

            raise RuntimeError(f"Agent {agent_id} already has a running MLX server")



        # Validate paths exist

        model_path = Path(agent.model_path).expanduser()

        if not model_path.exists():

            raise FileNotFoundError(f"Model path does not exist: {agent.model_path}")



        if agent.adapter_path:

            adapter_path = Path(agent.adapter_path).expanduser()

            if not adapter_path.exists():

                raise FileNotFoundError(f"Adapter path does not exist: {agent.adapter_path}")



        # Find available port or use override

        port = port_override if port_override else self._find_available_port()

 

        # Build command

        cmd = [

            "mlx_lm.server",

            "--model", str(model_path),

            "--port", str(port),

            "--trust-remote-code",

        ]



        # Add chat template if it exists in model directory

        chat_template_path = model_path / "chat_template.jinja"

        if chat_template_path.exists():

            cmd.extend(["--chat-template", str(chat_template_path)])

 

        # Add adapter if configured

        if agent.adapter_path:

            cmd.extend(["--adapter-path", str(adapter_path)])

 

        # Add LLM config parameters

        cmd.extend(["--temp", str(agent.temperature)])



        if hasattr(agent, 'top_p') and agent.top_p is not None:

            cmd.extend(["--top-p", str(agent.top_p)])



        if hasattr(agent, 'top_k') and agent.top_k is not None and agent.top_k > 0:

            cmd.extend(["--top-k", str(agent.top_k)])



        # Seed is not supported by mlx_lm.server
        # if agent.seed is not None:
        #     cmd.extend(["--seed", str(agent.seed)])



        if agent.max_output_tokens_enabled:

            cmd.extend(["--max-tokens", str(agent.max_output_tokens)])

 

        # TODO: Handle reasoning_enabled (might need model config file)

        # if agent.reasoning_enabled:

        #     # This might require special model configuration

        #     pass

 

        # Set up proper logging

        log_dir = Path("logs")

        log_dir.mkdir(exist_ok=True)

        log_file = log_dir / f"mlx_server_{agent_id}.log"

        log_handle = open(log_file, 'w')



        # Start process

        try:

            process = subprocess.Popen(

                cmd,

                stdout=log_handle,

                stderr=subprocess.STDOUT,  # Merge stderr into stdout

            )

        except FileNotFoundError:

            raise RuntimeError("mlx_lm.server not found. Is mlx-lm installed?")

 

        # Wait for server to be ready (not just started, but accepting connections)

        max_wait_time = 60  # seconds

        check_interval = 2  # seconds

        elapsed = 0

        server_ready = False



        print(f"[MLX Manager] Waiting for MLX server on port {port} to be ready...")



        while elapsed < max_wait_time:

            # Check if process crashed

            if process.poll() is not None:

                log_handle.close()

                with open(log_file, 'r') as f:

                    log_output = f.read()

                raise RuntimeError(

                    f"MLX server failed to start.\n"

                    f"Exit code: {process.returncode}\n"

                    f"Command: {' '.join(cmd)}\n"

                    f"Log output:\n{log_output}"

                )



            # Check if server is responding (try v1/models endpoint which mlx_lm.server has)

            try:

                async with httpx.AsyncClient(timeout=2.0) as client:

                    response = await client.get(f"http://localhost:{port}/v1/models")

                    if response.status_code in [200, 404]:  # Even 404 means server is up

                        server_ready = True

                        print(f"[MLX Manager] MLX server ready on port {port}")

                        break

            except (httpx.ConnectError, httpx.TimeoutException):

                # Server not ready yet, keep waiting

                pass



            await asyncio.sleep(check_interval)

            elapsed += check_interval



        if not server_ready:

            process.terminate()

            log_handle.close()

            with open(log_file, 'r') as f:

                log_output = f.read()

            raise RuntimeError(

                f"MLX server started but not responding after {max_wait_time}s.\n"

                f"Port: {port}\n"

                f"Command: {' '.join(cmd)}\n"

                f"Last 500 chars of log:\n{log_output[-500:]}"

            )

 

        # Track the process

        mlx_process = MLXServerProcess(agent_id, process, port)

        self._processes[agent_id] = mlx_process

        self._used_ports.add(port)

 

        return mlx_process

 

    async def stop_agent_server(self, agent_id: UUID, timeout: int = 10):

        """Stop the MLX server for an agent

 

        Args:

            agent_id: ID of agent whose server to stop

            timeout: Seconds to wait before force-killing

 

        Raises:

            ValueError: If agent has no running server

        """

        if agent_id not in self._processes:

            raise ValueError(f"No MLX server running for agent {agent_id}")

 

        mlx_process = self._processes[agent_id]

        await mlx_process.stop(timeout=timeout)

 

        # Clean up tracking

        self._used_ports.discard(mlx_process.port)

        del self._processes[agent_id]

 

    def get_agent_server(self, agent_id: UUID) -> Optional[MLXServerProcess]:

        """Get the running server for an agent

 

        Returns None if agent has no running server

        """

        mlx_process = self._processes.get(agent_id)

        if mlx_process and mlx_process.is_running():

            return mlx_process

        return None

 

    async def stop_all_servers(self, timeout: int = 10):

        """Stop all running MLX servers

 

        Called during application shutdown

        """

        agent_ids = list(self._processes.keys())

        for agent_id in agent_ids:

            try:

                await self.stop_agent_server(agent_id, timeout=timeout)

            except Exception as e:

                # Log error but continue stopping others

                print(f"Error stopping server for agent {agent_id}: {e}")

 

    def get_all_servers(self) -> Dict[UUID, MLXServerProcess]:

        """Get all running MLX servers

 

        Returns dict mapping agent_id -> MLXServerProcess

        """

        # Filter out dead processes

        active = {

            agent_id: proc

            for agent_id, proc in self._processes.items()

            if proc.is_running()

        }

        return active

 

 

# Global singleton instance

_mlx_manager = None

 

 

def get_mlx_manager() -> MLXManager:

    """Get the global MLXManager instance (dependency injection)"""

    global _mlx_manager

    if _mlx_manager is None:

        _mlx_manager = MLXManager()

    return _mlx_manager

 
