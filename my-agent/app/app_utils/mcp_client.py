import subprocess
import json
import os
import threading
import queue
import time
from typing import Any, Dict, Optional

class StdioMCPClient:
    def __init__(self, mcp_dir: str):
        self.mcp_dir = mcp_dir
        self.process: Optional[subprocess.Popen] = None
        self.req_id = 0
        self.response_queues = {}
        self.lock = threading.Lock()
        self.running = False
        self.read_thread = None

    def start(self):
        if self.running:
            return
        
        # Start server subprocess
        self.process = subprocess.Popen(
            ["uv", "--directory", self.mcp_dir, "run", "python", "-m", "ollama_wrapper.server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env={
                **os.environ,
                "PYTHONPATH": "src",
                "OLLAMA_HOST": "http://localhost:11434"
            }
        )
        self.running = True
        self.read_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.read_thread.start()

        # Initialize handshake
        init_res = self.call_method("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "ObsidianLoreCompanion", "version": "1.0.0"}
        })
        self.send_notification("notifications/initialized")
        return init_res

    def _reader_loop(self):
        while self.running and self.process:
            line = self.process.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line.strip())
                msg_id = msg.get("id")
                if msg_id is not None:
                    with self.lock:
                        q = self.response_queues.get(msg_id)
                    if q:
                        q.put(msg)
            except Exception:
                pass

    def send_notification(self, method: str, params: Optional[Dict] = None):
        if not self.process:
            return
        req = {
            "jsonrpc": "2.0",
            "method": method
        }
        if params is not None:
            req["params"] = params
        try:
            self.process.stdin.write(json.dumps(req) + "\n")
            self.process.stdin.flush()
        except Exception:
            pass

    def call_method(self, method: str, params: Dict, timeout: float = 30.0) -> Dict[str, Any]:
        if not self.process:
            raise Exception("MCP Client is not running.")
        
        with self.lock:
            self.req_id += 1
            cur_id = self.req_id
            q = queue.Queue()
            self.response_queues[cur_id] = q

        req = {
            "jsonrpc": "2.0",
            "id": cur_id,
            "method": method,
            "params": params
        }
        try:
            self.process.stdin.write(json.dumps(req) + "\n")
            self.process.stdin.flush()
        except Exception as e:
            with self.lock:
                if cur_id in self.response_queues:
                    del self.response_queues[cur_id]
            raise e

        try:
            res = q.get(timeout=timeout)
            with self.lock:
                del self.response_queues[cur_id]
            if "error" in res:
                raise Exception(f"MCP JSON-RPC Error: {res['error']}")
            return res.get("result", {})
        except queue.Empty:
            with self.lock:
                if cur_id in self.response_queues:
                    del self.response_queues[cur_id]
            raise TimeoutError(f"MCP request {cur_id} timed out after {timeout} seconds.")

    def call_tool(self, tool_name: str, arguments: Dict, timeout: float = 60.0) -> Dict[str, Any]:
        res = self.call_method("tools/call", {
            "name": tool_name,
            "arguments": arguments
        }, timeout=timeout)
        return res

    def stop(self):
        self.running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
