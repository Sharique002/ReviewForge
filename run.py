"""
Entrypoint for Automated Code Review Board (ReviewForge)
CSE476 CA2 — Microsoft Semantic Kernel Multi-Agent System
"""

import os
import argparse

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from backend.app import create_app


def main():
    parser = argparse.ArgumentParser(description="Automated Code Review Board (CSE476 CA2)")
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on (default 5000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface (default 127.0.0.1)")
    args = parser.parse_args()

    app = create_app()
    print("=" * 65)
    print("  REVIEWFORGE: AUTOMATED CODE REVIEW BOARD (Q14)")
    print("  CSE476 CA2 Multi-Agent Architecture Assignment")
    print(f"  Web Dashboard: http://{args.host}:{args.port}")
    print("=" * 65)
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
