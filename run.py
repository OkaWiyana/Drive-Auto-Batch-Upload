import sys
import asyncio

def setup_windows_asyncio():
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass

def main():
    setup_windows_asyncio()
    if len(sys.argv) > 1 and sys.argv[1] == "--run-agent":
        import agent_worker
        asyncio.run(agent_worker.main())
        return

    from src.ui.app import GDriveLauncher
    app = GDriveLauncher()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()

if __name__ == "__main__":
    main()
