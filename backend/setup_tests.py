#!/usr/bin/env python3
"""
Quick setup script for approval workflow tests.
This script ensures the testing environment is properly configured.
"""

import sys
import subprocess
import os

def check_docker():
    """Check if Docker is running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("✅ Docker is running")
            return True
        else:
            print("❌ Docker is not running")
            return False
    except FileNotFoundError:
        print("❌ Docker is not installed")
        return False

def check_test_database():
    """Check if test database exists."""
    try:
        result = subprocess.run(
            ["docker-compose", "exec", "-T", "db", "psql", "-U", "ocin",
             "-c", "SELECT 1 FROM pg_database WHERE datname='ocin_test'"],
            capture_output=True,
            text=True
        )
        if "1" in result.stdout:
            print("✅ Test database exists")
            return True
        else:
            print("❌ Test database does not exist")
            return False
    except Exception as e:
        print(f"❌ Error checking database: {e}")
        return False

def create_test_database():
    """Create the test database."""
    try:
        result = subprocess.run(
            ["docker-compose", "exec", "-T", "db", "psql", "-U", "ocin",
             "-c", "CREATE DATABASE ocin_test;"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("✅ Test database created")
            return True
        else:
            print(f"❌ Error creating database: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error creating database: {e}")
        return False

def check_dependencies():
    """Check if required Python dependencies are installed."""
    required_packages = ["pytest", "httpx", "asyncpg"]
    missing_packages = []

    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package} is installed")
        except ImportError:
            print(f"❌ {package} is not installed")
            missing_packages.append(package)

    return len(missing_packages) == 0, missing_packages

def install_dependencies():
    """Install required Python dependencies."""
    try:
        result = subprocess.run(
            ["pip", "install", "-r", "requirements.txt"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("✅ Dependencies installed successfully")
            return True
        else:
            print(f"❌ Error installing dependencies: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error installing dependencies: {e}")
        return False

def check_environment_variables():
    """Check if required environment variables are set."""
    required_vars = ["DATABASE_URL", "SECRET_KEY"]
    missing_vars = []

    for var in required_vars:
        if os.getenv(var):
            print(f"✅ {var} is set")
        else:
            print(f"❌ {var} is not set")
            missing_vars.append(var)

    return len(missing_vars) == 0, missing_vars

def main():
    """Main setup function."""
    print("🧪 OCIN Approval Workflow Test Setup")
    print("=" * 50)
    print()

    # Check Docker
    print("Step 1: Checking Docker...")
    if not check_docker():
        print("\nPlease start Docker and try again.")
        sys.exit(1)

    # Check database
    print("\nStep 2: Checking test database...")
    if not check_test_database():
        print("\nCreating test database...")
        if not create_test_database():
            print("\nFailed to create test database. Please check Docker Compose configuration.")
            sys.exit(1)

    # Check dependencies
    print("\nStep 3: Checking Python dependencies...")
    deps_ok, missing = check_dependencies()
    if not deps_ok:
        print(f"\nMissing packages: {', '.join(missing)}")
        print("Installing dependencies...")
        if not install_dependencies():
            print("\nFailed to install dependencies.")
            sys.exit(1)

    # Check environment variables
    print("\nStep 4: Checking environment variables...")
    env_ok, missing = check_environment_variables()
    if not env_ok:
        print(f"\nMissing environment variables: {', '.join(missing)}")
        print("Please set these variables in your .env file.")
        sys.exit(1)

    # Setup complete
    print("\n" + "=" * 50)
    print("✅ Test environment setup complete!")
    print("\nYou can now run tests using:")
    print("  pytest                                    # Run all tests")
    print("  pytest -m unit                           # Run unit tests only")
    print("  pytest -m integration                     # Run integration tests only")
    print("  pytest -m e2e                            # Run e2e tests only")
    print("  pytest --cov=app --cov-report=html     # Run with coverage")
    print("\nOr use the convenience scripts:")
    print("  ./run_tests.sh     # Linux/Mac")
    print("  run_tests.bat       # Windows")

if __name__ == "__main__":
    main()