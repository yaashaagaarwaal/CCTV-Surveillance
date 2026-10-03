import signal
import threading

# Set the moment the process receives SIGINT/SIGTERM (Ctrl+C, kill, reload).
# uvicorn waits for open connections before it runs lifespan shutdown, and a
# live camera stream is a connection that never ends on its own — so without
# this, Ctrl+C would hang for as long as any browser tab has the dashboard
# open. Stream loops check this flag and finish, letting shutdown proceed.
shutdown_event = threading.Event()


def install_shutdown_hooks() -> None:
    """Chain onto uvicorn's signal handlers (must run on the main thread)."""
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous = signal.getsignal(sig)

        def handler(signum, frame, previous=previous):
            shutdown_event.set()
            if callable(previous):
                previous(signum, frame)

        signal.signal(sig, handler)
