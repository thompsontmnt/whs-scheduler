"""Thin wrapper: run the scheduler package CLI. Use: python scheduler.py [args] or python -m scheduler.cli [args]."""

from scheduler.cli import main

if __name__ == "__main__":
    main()
