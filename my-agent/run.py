import sys

from app.web_ui import run_server

if __name__ == "__main__":
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    print(f"Starting Worldbuilding Companion App on http://127.0.0.1:{port}")
    run_server(port=port)
