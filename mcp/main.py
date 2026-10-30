from pathlib import Path

try:
    from src.server import main
except ModuleNotFoundError as error:
    if error.name != "fastmcp":
        raise
    requirements = Path(__file__).with_name("requirements.txt")
    raise SystemExit(
        f"Missing MCP dependencies. Install them with: "
        f"python -m pip install -r {requirements}"
    ) from error


if __name__ == "__main__":
    main()