# 🧪 OCIN Dashboard API Testing Guide

## 🚀 Quick Start

### Step 1: Get Authentication Token

First, get your JWT token by logging in:

**Option A: Via cURL (Windows)**
```powershell
# Login to get token
curl -X POST http://localhost:8000/api/v1/auth/login `
  -H "Content-Type: application/json" `
  -d "{\"email\":\"YOUR_EMAIL\",\"password\":\"YOUR_PASSWORD\"}"
```

**Option B: Via Browser Dev Tools**
1. Open browser Dev Tools (F12 in Chrome/Edge)
2. Go to Network tab
3. Open: `http://localhost:8000/api/v1/auth/login`
4. Set Method to POST
5. Add Body: `{"email":"YOUR_EMAIL","password":"YOUR_PASSWORD"}`
6. Click Send
7. Copy the `access_token` from the response

### Step 2: Set Your Token

Replace `YOUR_JWT_TOKEN` in the commands below with your actual token from Step 1.

## 📊 Test Commands

### 1. Test Dashboard Stats Endpoint

**Test: Verify tools_connected counts only external tools**

```powershell
curl http://localhost:8000/api/v1/dashboard/stats `
  -H "Authorization: Bearer YOUR_JWT_TOKEN" `
  -H "Content-Type: application/json"
```

**Expected Response:**
```json
{
  "active_agents": 5,
  "runs_today": 23,
  "schedules_active": 3,
  "tools_connected": 1
}
```

**What to Check:**
- ✅ `tools_connected` should be LOW (only external integrations)
- ✅ Built-in tools (File, HTTP, DateTime, Wait) should NOT be counted
- ✅ Other stats should be reasonable numbers

### 2. Test Recent Runs Endpoint

**Test: Verify new response format with schedule information**

```powershell
curl http://localhost:8000/api/v1/dashboard/recent-runs?limit=5 `
  -H "Authorization: Bearer YOUR_JWT_TOKEN" `
  -H "Content-Type: application/json"
```

**Expected Response:**
```json
[
  {
    "id": "run-123",
    "agent": "My Agent",              // ✅ NEW: Renamed from agent_name
    "agent_id": "agent-456",          // ✅ NEW: Agent ID
    "status": "success",
    "started": "2026-04-09T10:00:00Z",  // ✅ NEW: Started timestamp
    "duration": "2m 30s",               // ✅ NEW: Calculated duration
    "schedule_id": "schedule-789",        // ✅ NEW: Schedule ID (null if manual)
    "schedule_name": "Daily Report"           // ✅ NEW: Schedule name (null if manual)
  }
]
```

**What to Check:**
- ✅ `agent` field exists (not `agent_name`)
- ✅ `agent_id` field present
- ✅ `started` field present (not `started_at`)
- ✅ `duration` field present with format like "2m 30s"
- ✅ `schedule_id` field present (null for manual runs)
- ✅ `schedule_name` field present (null for manual runs)

## 🔍 Advanced Testing Scenarios

### Scenario 1: Test Empty Dashboard (No Data)

```powershell
# Test stats with no data
curl http://localhost:8000/api/v1/dashboard/stats `
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Test recent runs with no data  
curl http://localhost:8000/api/v1/dashboard/recent-runs `
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Expected:**
- Stats should show `0` for most fields (except maybe active_agents if you have some)
- Recent runs should return empty array `[]`

### Scenario 2: Test With Schedule Data

Create some test data via the API, then check if schedule information appears:

```powershell
# Create a scheduled run first
curl -X POST http://localhost:8000/api/v1/runs/trigger `
  -H "Authorization: Bearer YOUR_JWT_TOKEN" `
  -H "Content-Type: application/json" `
  -d "{\"agent_id\":\"YOUR_AGENT_ID\",\"input\":\"Test run\"}"

# Check if schedule info appears in recent runs
curl http://localhost:8000/api/v1/dashboard/recent-runs `
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**What to Check:**
- ✅ If run was from a schedule, `schedule_id` and `schedule_name` should be present
- ✅ If run was manual, both fields should be `null`

### Scenario 3: Test Tools Count Accuracy

Create different tool types and verify count:

```powershell
# Create a built-in tool (should NOT be counted)
curl -X POST http://localhost:8000/api/v1/tools `
  -H "Authorization: Bearer YOUR_JWT_TOKEN" `
  -H "Content-Type: application/json" `
  -d "{\"name\":\"Test File Tool\",\"source\":\"builtin\",\"is_active\":true}"

# Create an external tool (should BE counted)
curl -X POST http://localhost:8000/api/v1/tools `
  -H "Authorization: Bearer YOUR_JWT_TOKEN" `
  -H "Content-Type: application/json" `
  -d "{\"name\":\"Test Composio Tool\",\"source\":\"composio\",\"source_key\":\"test_connection\",\"is_active\":true}"

# Check stats - should count only the external tool
curl http://localhost:8000/api/v1/dashboard/stats `
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Expected:**
- `tools_connected` should be `1` (only the Composio tool)
- Built-in tools should NOT affect the count

### Scenario 4: Test Pagination

```powershell
# Test with different limits
curl "http://localhost:8000/api/v1/dashboard/recent-runs?limit=1" `
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

curl "http://localhost:8000/api/v1/dashboard/recent-runs?limit=25" `
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

curl "http://localhost:8000/api/v1/dashboard/recent-runs?limit=50" `
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**What to Check:**
- ✅ Limit `1` returns only 1 run
- ✅ Limit `25` returns 25 runs  
- ✅ Limit `50` returns 50 runs (max allowed)
- ✅ Response should respect the limit parameter

## 🌐 Browser-Based Testing

### Using Chrome DevTools

1. **Open Network Tab** (F12)
2. **Set Request Method** to GET for stats, POST for login
3. **Set URL** to `http://localhost:8000/api/v1/dashboard/stats`
4. **Add Headers:**
   ```
   Authorization: Bearer YOUR_JWT_TOKEN
   Content-Type: application/json
   ```
5. **Click Send** and view the response

### Using Firefox DevTools

1. **Open Network Tab** (F12)
2. **Set Request Method** to GET
3. **Set URL** to `http://localhost:8000/api/v1/dashboard/recent-runs`
4. **Add Headers:**
   ```
   Authorization: Bearer YOUR_JWT_TOKEN
   Content-Type: application/json
   ```
5. **Click Send** and view the response

### Using Edge DevTools

1. **Open Network Tab** (F12)
2. **Click +** to add new request
3. **Set URL**: `http://localhost:8000/api/v1/dashboard/stats`
4. **Add Headers** tab and paste:
   ```
   Authorization: Bearer YOUR_JWT_TOKEN
   ```
5. **Click Send** and view the response

## 🐛 Troubleshooting

### "Unauthorized" / 401 Error

**Problem:** Token is missing or invalid

**Solution:** 
1. Get a fresh token using the login command
2. Make sure to copy the entire `access_token` value
3. Check for extra spaces or quotes in the token

### "Internal Server Error" / 500 Error

**Problem:** Server-side error or database issue

**Solution:**
1. Check if the API server is running (`uvicorn app.main:app`)
2. Look at server logs for error details
3. Ensure database is running (`docker-compose up -d db`)

### "Field Not Found" Error

**Problem:** New field names not appearing

**Solution:**
1. Clear browser cache and reload the page
2. Check the API response in Network tab to see actual field names
3. Verify the backend code is deployed and running

### "Invalid Response Format"

**Problem:** Response doesn't match expected structure

**Solution:**
1. Check the actual JSON response in browser Network tab
2. Compare with expected response format
3. Verify backend code matches the new response structure

## 📋 Validation Checklist

### Dashboard Stats Endpoint
- [ ] `active_agents` is a number
- [ ] `runs_today` is a number
- [ ] `schedules_active` is a number
- [ ] `tools_connected` is a number (low, only external tools)
- [ ] Response time is under 1 second

### Recent Runs Endpoint
- [ ] Response is an array
- [ ] Each run has `id` field
- [ ] Each run has `agent` field (not `agent_name`)
- [ ] Each run has `agent_id` field
- [ ] Each run has `status` field
- [ ] Each run has `started` field (datetime format)
- [ ] Each run has `duration` field (string format)
- [ ] `schedule_id` present for scheduled runs
- [ ] `schedule_id` is null for manual runs
- [ ] `schedule_name` present for scheduled runs
- [ ] `schedule_name` is null for manual runs

## 🎯 Success Criteria

### Dashboard Stats ✅
- Endpoint returns 200 status code
- Response structure matches expected format
- `tools_connected` accurately reflects only external tools
- Response time is acceptable (< 1 second)

### Recent Runs ✅  
- Endpoint returns 200 status code
- Response structure matches expected format
- New field names are present (`agent`, `agent_id`, `started`, `duration`)
- Schedule information is correctly included
- Pagination works correctly
- Duration format is human-readable

## 🔧 Advanced Testing Tips

### Compare Before/After Responses

**Test Before Update:**
```powershell
# Save old response
curl http://localhost:8000/api/v1/dashboard/recent-runs `
  -H "Authorization: Bearer OLD_TOKEN" > before_update.json
```

**Test After Update:**
```powershell
# Save new response
curl http://localhost:8000/api/v1/dashboard/recent-runs `
  -H "Authorization: Bearer NEW_TOKEN" > after_update.json
```

**Compare:**
```powershell
# Use a diff tool or visually compare the files
# Look for:
# - Field name changes (agent_name → agent)
# - New fields added (agent_id, schedule_id, etc.)
# - Response format improvements
```

### Load Testing

```powershell
# Test with many concurrent requests
for i in {1..10}; do
  curl http://localhost:8000/api/v1/dashboard/stats `
    -H "Authorization: Bearer YOUR_JWT_TOKEN" &
done

# Check if all requests succeed without errors
```

### Response Time Testing

```powershell
# Measure response time
Measure-Command {
    curl http://localhost:8000/api/v1/dashboard/stats `
        -H "Authorization: Bearer YOUR_JWT_TOKEN" `
        -w "%{time_total}\n" `
        -o /dev/null
}

# Should be under 1000ms (1 second) for good performance
```

## 📊 Expected Behavior

### When No Schedules Configured
- All runs should have `schedule_id: null`
- All runs should have `schedule_name: null`

### When Mixed Runs Exist
- Scheduled runs: `schedule_id` has value, `schedule_name` has value
- Manual runs: `schedule_id` is null, `schedule_name` is null

### When Only External Tools
- `tools_connected` equals number of Composio + Apify + Maton tools
- Built-in tools don't affect the count

## 🚀 Ready to Test!

Choose your testing method:
1. **Quick Test**: Use the curl commands above
2. **Browser Test**: Use DevTools in your browser
3. **Advanced Test**: Use the validation checklist and scenarios

Replace `YOUR_JWT_TOKEN` with your actual authentication token and start testing!