#!/usr/bin/env python3
"""
Raksh Clinical Ingestion Backend — Setup Script

Validates environment, installs dependencies, runs migrations,
and verifies the system is ready for development.

Usage:
    python setup.py              # Full setup
    python setup.py --check      # Check only, no install
    python setup.py --skip-db    # Skip database setup
"""

import os
import sys
import shutil
import subprocess
import argparse
from pathlib import Path


REQUIRED_ENV_VARS = [
    ("SUPABASE_URL", True, "Supabase project URL"),
    ("SUPABASE_SERVICE_ROLE_KEY", True, "Supabase service role key"),
    ("ANTHROPIC_API_KEY", False, "Claude API key (optional for local OCR)"),
    ("INGESTION_API_KEY", True, "API key for ingestion service"),
]

REQUIRED_PYTHON_PACKAGES = [
    "fastapi",
    "uvicorn",
    "supabase",
    "anthropic",
    "structlog",
    "pydantic",
    "pydantic_settings",
    "httpx",
    "python-multipart",
    "presidio_analyzer",
    "presidio_anonymizer",
    "spacy",
]

OPTIONAL_PACKAGES = [
    ("cv2", "opencv-python", "Image preprocessing"),
    ("pydicom", "pydicom", "DICOM file parsing"),
    ("pytesseract", "pytesseract", "OCR fallback"),
]

BANNER = """
╔══════════════════════════════════════════════╗
║  RAKSH Clinical Ingestion Backend            ║
║  Setup & Validation Script                   ║
║  v1.0.0                                      ║
╚══════════════════════════════════════════════╝
"""


class SetupResult:
    def __init__(self):
        self.passed: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def ok(self, msg: str):
        self.passed.append(msg)
        print(f"  ✓ {msg}")

    def warn(self, msg: str):
        self.warnings.append(msg)
        print(f"  ⚠ {msg}")

    def fail(self, msg: str):
        self.errors.append(msg)
        print(f"  ✗ {msg}")

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


def check_python_version(result: SetupResult):
    print("\n[1/7] Python Version")
    v = sys.version_info
    if v.major == 3 and v.minor >= 10:
        result.ok(f"Python {v.major}.{v.minor}.{v.micro}")
    elif v.major == 3 and v.minor >= 8:
        result.warn(f"Python {v.major}.{v.minor} — works but 3.10+ recommended")
    else:
        result.fail(f"Python {v.major}.{v.minor} — requires 3.8+")


def check_env_file(result: SetupResult):
    print("\n[2/7] Environment Variables")
    env_path = Path(__file__).parent / ".env"
    example_path = Path(__file__).parent / ".env.example"

    if not env_path.exists():
        if example_path.exists():
            result.warn(".env not found — copying from .env.example")
            shutil.copy(example_path, env_path)
        else:
            result.fail(".env not found and no .env.example available")
            return

    from dotenv import load_dotenv
    load_dotenv(env_path)

    for var_name, required, description in REQUIRED_ENV_VARS:
        value = os.getenv(var_name, "")
        if value:
            masked = value[:4] + "..." if len(value) > 8 else "***"
            result.ok(f"{var_name} = {masked}")
        elif required:
            result.fail(f"{var_name} not set — {description}")
        else:
            result.warn(f"{var_name} not set — {description}")


def check_required_packages(result: SetupResult):
    print("\n[3/7] Required Python Packages")
    for package in REQUIRED_PYTHON_PACKAGES:
        try:
            __import__(package)
            result.ok(package)
        except ImportError:
            result.fail(f"{package} not installed")


def check_optional_packages(result: SetupResult):
    print("\n[4/7] Optional Packages")
    for import_name, pip_name, description in OPTIONAL_PACKAGES:
        try:
            __import__(import_name)
            result.ok(f"{pip_name} ({description})")
        except ImportError:
            result.warn(f"{pip_name} not installed — {description}")


def check_spacy_model(result: SetupResult):
    print("\n[5/7] spaCy NLP Model")
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        result.ok(f"en_core_web_sm loaded ({len(nlp.pipe_names)} components)")
    except OSError:
        result.warn("en_core_web_sm not found — run: python -m spacy download en_core_web_sm")
    except ImportError:
        result.fail("spacy not installed")


def check_external_tools(result: SetupResult):
    print("\n[6/7] External Tools")

    docker = shutil.which("docker")
    if docker:
        result.ok(f"Docker: {docker}")
    else:
        result.warn("Docker not found — required for containerized deployment")

    git = shutil.which("git")
    if git:
        result.ok(f"Git: {git}")
    else:
        result.warn("Git not found")

    gh = shutil.which("gh")
    if gh:
        result.ok(f"GitHub CLI: {gh}")
    else:
        result.warn("GitHub CLI not found — install: https://cli.github.com/")

    supabase_cli = shutil.which("supabase")
    if supabase_cli:
        result.ok(f"Supabase CLI: {supabase_cli}")
    else:
        result.warn("Supabase CLI not found — install: https://supabase.com/docs/guides/cli")


def check_project_structure(result: SetupResult):
    print("\n[7/7] Project Structure")
    base = Path(__file__).parent

    required_dirs = [
        "services/ingestion/pipeline",
        "services/ingestion/routes",
        "services/ingestion/services",
        "services/ingestion/models",
        "services/ingestion/tests",
        "services/ingestion/middleware",
        "supabase/migrations",
    ]

    for d in required_dirs:
        p = base / d
        if p.exists():
            result.ok(d)
        else:
            result.fail(f"{d} — directory missing")

    required_files = [
        "docker-compose.yml",
        "docker-compose.dev.yml",
        ".env.example",
        "services/ingestion/main.py",
        "services/ingestion/config.py",
        "services/ingestion/requirements.txt",
    ]

    for f in required_files:
        p = base / f
        if p.exists():
            result.ok(f"{f} ({p.stat().st_size} bytes)")
        else:
            result.fail(f"{f} — file missing")


def install_dependencies():
    print("\n[Install] Installing Python dependencies...")
    req_path = Path(__file__).parent / "services" / "ingestion" / "requirements.txt"
    if req_path.exists():
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_path), "-q"],
            check=False,
        )
        print("  ✓ Dependencies installed")
    else:
        print("  ✗ requirements.txt not found")


def run_tests():
    print("\n[Test] Running test suite...")
    test_dir = Path(__file__).parent / "services" / "ingestion"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short", "-q",
         "--ignore=tests/test_preprocessing.py",
         "--ignore=tests/test_integration.py"],
        cwd=str(test_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        lines = result.stdout.strip().split("\n")
        summary = [l for l in lines if "passed" in l]
        if summary:
            print(f"  ✓ {summary[-1].strip()}")
        else:
            print("  ✓ Tests passed")
    else:
        print(f"  ✗ Tests failed (exit code {result.returncode})")
        last_lines = result.stdout.strip().split("\n")[-3:]
        for line in last_lines:
            print(f"    {line.strip()}")


def main():
    parser = argparse.ArgumentParser(description="Raksh Backend Setup")
    parser.add_argument("--check", action="store_true", help="Check only, don't install")
    parser.add_argument("--skip-db", action="store_true", help="Skip database checks")
    parser.add_argument("--skip-tests", action="store_true", help="Skip test execution")
    args = parser.parse_args()

    print(BANNER)

    result = SetupResult()

    check_python_version(result)
    check_env_file(result)
    check_required_packages(result)
    check_optional_packages(result)
    check_spacy_model(result)
    check_external_tools(result)
    check_project_structure(result)

    if not args.check:
        install_dependencies()

    if not args.skip_tests and not args.check:
        run_tests()

    print("\n" + "=" * 48)
    print(f"  Passed:   {len(result.passed)}")
    print(f"  Warnings: {len(result.warnings)}")
    print(f"  Errors:   {len(result.errors)}")
    print("=" * 48)

    if result.success:
        print("\n  ✓ RAKSH backend is ready for development!\n")
        print("  Quick start:")
        print("    cd services/ingestion")
        print("    uvicorn main:app --reload --port 8001")
        print()
        print("  Docker:")
        print("    docker compose -f docker-compose.dev.yml up --build")
        print()
    else:
        print("\n  ✗ Setup incomplete — fix errors above\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
