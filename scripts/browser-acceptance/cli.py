"""Use the real CLI entry point; stdout is captured privately by browser assertions."""

from safety import install

install()

if __name__ == "__main__":
    from app.cli.chat import main

    raise SystemExit(main())
