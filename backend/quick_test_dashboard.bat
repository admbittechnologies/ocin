@echo off
REM Quick Dashboard Testing Script for Windows
REM Replace YOUR_JWT_TOKEN below with your actual token

echo ============================================================
echo OCIN Dashboard API Testing
echo ============================================================
echo.

echo Step 1: Set your JWT token
echo -----------------------------------
echo.
set /p JWT_TOKEN=YOUR_JWT_TOKEN

echo You need to replace YOUR_JWT_TOKEN with your actual JWT token.
echo.
echo To get a token, run:
echo   1. Open browser DevTools (F12)
echo   2. Go to http://localhost:8000/api/v1/auth/login
echo   3. Switch to Network tab
echo   4. Set Method to POST
echo   5. Set URL to http://localhost:8000/api/v1/auth/login
echo   6. Add Body: {"email":"YOUR_EMAIL","password":"YOUR_PASSWORD"}
echo   7. Click Send
echo   8. Copy the "access_token" value from the response
echo.

pause

echo Step 2: Test Dashboard Stats Endpoint
echo -----------------------------------
curl http://localhost:8000/api/v1/dashboard/stats ^
  -H "Authorization: Bearer %JWT_TOKEN%" ^
  -H "Content-Type: application/json"

echo.
echo Expected: tools_connected should be LOW (only external tools)
echo         Built-in tools should NOT be counted
echo.

pause

echo Step 3: Test Recent Runs Endpoint
echo -----------------------------------
curl http://localhost:8000/api/v1/dashboard/recent-runs?limit=3 ^
  -H "Authorization: Bearer %JWT_TOKEN%" ^
  -H "Content-Type: application/json"

echo.
echo Expected:
echo   - agent field (not agent_name)
echo   - agent_id field added
echo   - started field (not started_at)
echo   - duration field added
echo   - schedule_id and schedule_name fields included
echo.

pause

echo Step 4: Test Pagination
echo -----------------------------------
echo Testing with limit=1...
curl http://localhost:8000/api/v1/dashboard/recent-runs?limit=1 ^
  -H "Authorization: Bearer %JWT_TOKEN%" ^
  -H "Content-Type: application/json"

echo.
echo Testing with limit=10...
curl http://localhost:8000/api/v1/dashboard/recent-runs?limit=10 ^
  -H "Authorization: Bearer %JWT_TOKEN%" ^
  -H "Content-Type: application/json"

echo.

echo ============================================================
echo Testing Complete!
echo ============================================================
echo.
echo Check the responses above to verify:
echo   - New field names are present
echo   - Schedule information is included
echo   - tools_connected only counts external tools
echo.
pause