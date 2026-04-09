import argparse
import asyncio


def main():
    parser = argparse.ArgumentParser(description="AG-OS: Multi-agent orchestrator")
    parser.add_argument(
        "mode",
        choices=["bot", "tui", "all"],
        default="all",
        nargs="?",
        help="Run mode: bot (Telegram only), tui (dashboard only), all (both)",
    )
    args = parser.parse_args()
    print(f"AG-OS starting in {args.mode} mode...")


if __name__ == "__main__":
    main()
