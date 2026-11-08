import sys
import asyncio

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--run-agent":
        import agent_worker
        if sys.platform == "win32":
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            except Exception:
                pass
        asyncio.run(agent_worker.main())
        return

    from src.ui.app import GDriveLauncher
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass

    app = GDriveLauncher()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()

if __name__ == "__main__":
    main()
