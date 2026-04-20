@echo off
REM Quick start script for running approval workflow tests (Windows)

echo ============================================================
echo OCIN Approval Workflow Test Suite
echo ============================================================
echo.

REM Check if pytest is installed
where pytest >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] pytest is not installed
    echo Installing test dependencies...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install dependencies
        exit /b 1
    )
    echo Dependencies installed successfully
    echo.
)

REM Parse arguments
set TEST_TYPE=all
set COVERAGE=false
set PARALLEL=false

:parse_args
if "%~1"=="" goto end_args
if "%~1"=="--unit" (
    set TEST_TYPE=unit
    shift
    goto parse_args
)
if "%~1"=="--integration" (
    set TEST_TYPE=integration
    shift
    goto parse_args
)
if "%~1"=="--e2e" (
    set TEST_TYPE=e2e
    shift
    goto parse_args
)
if "%~1"=="--coverage" (
    set COVERAGE=true
    shift
    goto parse_args
)
if "%~1"=="--parallel" (
    set PARALLEL=true
    shift
    goto parse_args
)
if "%~1"=="--help" (
    echo Usage: run_tests.bat [options]
    echo.
    echo Options:
    echo   --unit         Run only unit tests
    echo   --integration   Run only integration tests
    echo   --e2e          Run only end-to-end tests
    echo   --coverage     Generate coverage report
    echo   --parallel      Run tests in parallel
    echo   --help         Show this help message
    exit /b 0
)
echo [ERROR] Unknown option: %~1
echo Use --help for usage information
exit /b 1

:end_args
echo Running tests...
echo.

REM Build pytest command
set PYTEST_CMD=pytest

if not "%TEST_TYPE%"=="all" (
    set PYTEST_CMD=%PYTEST_CMD% -m %TEST_TYPE%
)

if "%COVERAGE%"=="true" (
    set PYTEST_CMD=%PYTEST_CMD% --cov=app --cov-report=html --cov-report=term
)

if "%PARALLEL%"=="true" (
    set PYTEST_CMD=%PYTEST_CMD% -n auto
)

echo Command: %PYTEST_CMD%
echo.

REM Run tests
%PYTEST_CMD%

REM Check exit code
if %errorlevel%==0 (
    echo.
    echo [SUCCESS] All tests passed!
    echo.
    if "%COVERAGE%"=="true" (
        echo Coverage report generated in htmlcov\index.html
    )
) else (
    echo.
    echo [ERROR] Some tests failed. Please review the output above.
    exit /b 1
)