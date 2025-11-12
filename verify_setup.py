#!/usr/bin/env python3
"""
Setup Verification Script
This script checks if all required dependencies and configurations are in place.
"""

import sys
import os
from pathlib import Path


def print_header(text):
    print("\n" + "=" * 50)
    print(f"  {text}")
    print("=" * 50)


def print_check(name, status, message=""):
    symbol = "✅" if status else "❌"
    print(f"{symbol} {name}")
    if message:
        print(f"   → {message}")


def check_python_version():
    """Check if Python version is 3.9 or higher."""
    version = sys.version_info
    is_valid = version.major == 3 and version.minor >= 9
    return is_valid, f"Python {version.major}.{version.minor}.{version.micro}"


def check_env_file():
    """Check if .env file exists and has required variables."""
    env_path = Path(".env")
    if not env_path.exists():
        return False, ".env file not found"

    with open(env_path) as f:
        content = f.read()

    required_vars = [
        "DATABASE_URL",
        "SECRET_KEY",
        "AZURE_STORAGE_CONNECTION_STRING",
        "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
        "AZURE_SEARCH_ENDPOINT",
        "AZURE_OPENAI_ENDPOINT",
    ]

    missing = []
    placeholder = []

    for var in required_vars:
        if var not in content:
            missing.append(var)
        elif "your-" in content or "change-this" in content.lower():
            # Check if this specific variable has placeholder values
            for line in content.split("\n"):
                if line.startswith(var) and ("your-" in line or "change-this" in line.lower()):
                    placeholder.append(var)

    if missing:
        return False, f"Missing variables: {', '.join(missing)}"
    if placeholder:
        return False, f"Placeholder values detected: {', '.join(placeholder)}"

    return True, "All required variables present"


def check_required_files():
    """Check if all required project files exist."""
    required_files = [
        "app/main.py",
        "app/core/config.py",
        "app/core/database.py",
        "requirements.txt",
        "alembic.ini",
        "alembic/env.py",
    ]

    missing = []
    for file in required_files:
        if not Path(file).exists():
            missing.append(file)

    if missing:
        return False, f"Missing files: {', '.join(missing)}"

    return True, "All required files present"


def check_dependencies():
    """Check if required Python packages are installed."""
    required_packages = [
        "fastapi",
        "uvicorn",
        "sqlalchemy",
        "alembic",
        "azure-storage-blob",
        "azure-ai-formrecognizer",
        "azure-search-documents",
        "openai",
        "pydantic",
        "python-jose",
        "passlib",
    ]

    missing = []
    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
        except ImportError:
            missing.append(package)

    if missing:
        return False, f"Missing packages: {', '.join(missing)}"

    return True, "All required packages installed"


def check_database_connection():
    """Check if database connection can be established."""
    try:
        from dotenv import load_dotenv
        load_dotenv()

        from app.core.config import settings

        if not settings.DATABASE_URL:
            return False, "DATABASE_URL not configured"

        # Basic URL format check
        if not settings.DATABASE_URL.startswith("postgresql"):
            return False, "DATABASE_URL must start with 'postgresql' or 'postgresql+asyncpg'"

        return True, "Database URL configured (connection not tested)"

    except Exception as e:
        return False, f"Error: {str(e)}"


def check_azure_config():
    """Check if Azure services are configured."""
    try:
        from dotenv import load_dotenv
        load_dotenv()

        from app.core.config import settings

        checks = {
            "Blob Storage": bool(settings.AZURE_STORAGE_CONNECTION_STRING),
            "Document Intelligence": bool(settings.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT),
            "AI Search": bool(settings.AZURE_SEARCH_ENDPOINT),
            "OpenAI": bool(settings.AZURE_OPENAI_ENDPOINT),
        }

        missing = [name for name, configured in checks.items() if not configured]

        if missing:
            return False, f"Not configured: {', '.join(missing)}"

        return True, "All Azure services configured"

    except Exception as e:
        return False, f"Error: {str(e)}"


def main():
    print_header("RAG Document Analysis API - Setup Verification")

    print("\n📋 Checking setup...")

    # Check Python version
    status, message = check_python_version()
    print_check("Python Version (3.9+)", status, message)

    # Check required files
    status, message = check_required_files()
    print_check("Required Files", status, message)

    # Check .env file
    status, message = check_env_file()
    print_check("Environment Configuration", status, message)

    # Check dependencies
    status, message = check_dependencies()
    print_check("Python Dependencies", status, message)

    # Check database configuration
    status, message = check_database_connection()
    print_check("Database Configuration", status, message)

    # Check Azure configuration
    status, message = check_azure_config()
    print_check("Azure Services Configuration", status, message)

    print("\n" + "=" * 50)
    print("\n📝 Next Steps:")
    print("1. If any checks failed, review SETUP_GUIDE.md")
    print("2. Ensure all Azure resources are created")
    print("3. Run: alembic upgrade head")
    print("4. Start the server: uvicorn app.main:app --reload")
    print("5. Visit: http://localhost:8000/docs")
    print("\n" + "=" * 50 + "\n")


if __name__ == "__main__":
    main()
