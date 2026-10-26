import sys
import argparse
import asyncio

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from nova_apex.config.settings import settings

def main():
    parser = argparse.ArgumentParser(description="NOVA-APEX: Universal Autonomous Automation Agent OS")
    parser.add_argument("--server", action="store_true", help="Launch Mission Control web server and UI")
    parser.add_argument("--port", type=int, default=settings.server_port, help="Port to run web server on")
    parser.add_argument("--goal", type=str, help="Execute a single natural language mission goal and exit")
    parser.add_argument("--account-url", type=str, help="Execute automated account creation on target URL")

    args = parser.parse_args()

    if args.server:
        import uvicorn
        from nova_apex.server.app import app
        print(f"\n=======================================================")
        print(f"🚀 NOVA-APEX Mission Control running at: http://localhost:{args.port}")
        print(f"=======================================================\n")
        uvicorn.run(app, host=settings.server_host, port=args.port)

    elif args.goal:
        from nova_apex.core.engine import engine
        print(f"Executing goal: {args.goal}")
        goal = asyncio.run(engine.run_goal(args.goal))
        print(f"Goal finished with status: {goal.status.value}")

    elif args.account_url:
        from nova_apex.skills.web_account_creator import web_account_creator
        print(f"Creating account on: {args.account_url}")
        res = asyncio.run(web_account_creator.create_account(args.account_url))
        print(f"Result: {res}")

    else:
        # Default: interactive CLI
        from nova_apex.cli import main as cli_main
        cli_main()

if __name__ == "__main__":
    main()
