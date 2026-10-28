"""Launch the Concept Tracking CRM in a desktop window when pywebview is available."""
from pathlib import Path
import os
import threading
import time
import webbrowser

from werkzeug.serving import make_server
from app import app, init_db

HOST = "127.0.0.1"
PORT = int(os.environ.get("CTS_PORT", "5175"))
URL = f"http://{HOST}:{PORT}"


def main():
    init_db()
    try:
        server = make_server(HOST, PORT, app, threaded=True)
    except OSError:
        # A second launch can simply connect to the already-running local app.
        try:
            import webview
            webview.create_window("Concept Tracking CRM", URL, width=1440, height=920, min_size=(1050, 680))
            webview.start()
            return
        except Exception:
            webbrowser.open(URL)
            print(f"Could not start a new local server. Check whether the CRM is already running at {URL}.")
            return

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.55)

    try:
        import webview
        webview.create_window(
            "Concept Tracking CRM",
            URL,
            width=1440,
            height=920,
            min_size=(1050, 680),
            text_select=True,
        )
        webview.start(debug=False)
    except Exception as exc:
        # Browser fallback allows use even if WebView2/pywebview is unavailable.
        print(f"Desktop window unavailable ({exc}). Opening the CRM in your default browser.")
        webbrowser.open(URL)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
    finally:
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
