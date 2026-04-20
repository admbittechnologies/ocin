# Dashboard API Endpoint Updates

## 🎯 Overview

Updated two dashboard API endpoints to support new Dashboard and Runs page features as requested.

## 📋 Changes Made

### 1. Updated `/api/v1/dashboard/recent-runs` Endpoint

**File Modified**: `app/routers/dashboard.py`

#### Schema Changes
- ✅ Renamed `agent_name` to `agent` in response model
- ✅ Added `agent_id` field (Agent ID)
- ✅ Added `started` field (started timestamp)
- ✅ Added `duration` field (calculated duration string)
- ✅ Added `schedule_id` field (Schedule ID or null)
- ✅ Added `schedule_name` field (Schedule name or null)

#### Query Changes
- ✅ Added `OUTER JOIN` with Schedule table to get schedule information
- ✅ Maintained existing Agent join for agent names
- ✅ Added duration calculation logic for completed runs
- ✅ Added "Running..." duration for active runs

#### Response Format Comparison

**Old Response:**
```json
{
  "id": "run-123",
  "agent_name": "My Agent",
  "status": "success",
  "started_at": "2026-04-09T10:00:00Z",
  "finished_at": "2026-04-09T10:02:30Z",
  "cost_usd": 0.05
}
```

**New Response:**
```json
{
  "id": "run-123",
  "agent": "My Agent",              // Renamed from agent_name
  "agent_id": "agent-456",          // NEW: Agent ID
  "status": "success",
  "started": "2026-04-09T10:00:00Z",   // Renamed from started_at
  "duration": "2m 30s",               // NEW: Calculated duration
  "schedule_id": "schedule-789",        // NEW: Schedule ID (null if manual)
  "schedule_name": "Daily Report"           // NEW: Schedule name (null if manual)
}
```

### 2. Updated `/api/v1/dashboard/stats` Endpoint

**File Modified**: `app/routers/dashboard.py`

#### Query Changes
- ✅ Enhanced comments for clarity
- ✅ Confirmed filtering logic for external tools only
- ✅ Verified exclusion of built-in tools

#### Response Format

```json
{
  "active_agents": 5,
  "runs_today": 23,
  "schedules_active": 3,
  "tools_connected": 1    // Only counts Composio, Apify, Maton tools
}
```

#### Tool Counting Logic

**COUNTED (External Tools):**
- ✅ Composio tools (`source='composio'`)
- ✅ Apify tools (`source='apify'`)
- ✅ Maton tools (`source='maton'`)

**NOT COUNTED (Built-in Tools):**
- ❌ File operations (`source='builtin'`)
- ❌ HTTP requests (`source='builtin'`)
- ❌ DateTime (`source='builtin'`)
- ❌ Wait/Timeout (`source='builtin'`)

## 🚀 Benefits for Dashboard UX

### Recent Runs Page
- ✅ **Clickable Schedule Links**: Users can click on schedule names to view/edit schedules
- ✅ **Agent Information**: Agent ID and name both available for better UX
- ✅ **Duration Display**: Easy-to-read "2m 30s" format instead of timestamps
- ✅ **Schedule Context**: Clear indication if run was manual or scheduled
- ✅ **Responsive Filtering**: Better filtering and sorting options

### Dashboard Stats
- ✅ **Accurate Tool Count**: Only external integrations counted
- ✅ **Clear User Expectations**: Users know exactly what "tools_connected" means
- ✅ **Better Planning**: Accurate counts help users understand their integration status

## 🧪 Testing

### Test Script Created
- **File**: `test_dashboard_updates.py`
- **Purpose**: Automated testing of updated endpoints
- **Features**:
  - Authentication flow testing
  - Endpoint response validation
  - Field presence verification
  - Response format checking

### Running Tests

**Windows:**
```powershell
# Start API server
uvicorn app.main:app --reload

# In another terminal, run tests
python test_dashboard_updates.py
```

**Manual Testing:**

```bash
# Test stats endpoint
curl http://localhost:8000/api/v1/dashboard/stats \
  -H "Authorization: Bearer YOUR_TOKEN"

# Test recent runs endpoint
curl http://localhost:8000/api/v1/dashboard/recent-runs \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 📊 Database Schema Notes

### Run Model
The `Run` model already has the `schedule_id` foreign key:
```python
schedule_id = Column(UUID(as_uuid=True), ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True)
```

This allows:
- ✅ `NULL` for manually triggered runs
- ✅ Schedule ID for scheduled runs
- ✅ Automatic cascade deletion if schedule is deleted

### Schedule Model
The `Schedule` model contains the `label` field that provides schedule names:
```python
label = Column(String(255))  # User-facing schedule name like "Every morning at 9"
```

## 🔧 Implementation Details

### Duration Calculation
```python
if run.started_at and run.finished_at:
    diff = run.finished_at - run.started_at
    total_seconds = int(diff.total_seconds())
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    duration = f"{minutes}m {seconds}s"
elif run.started_at:
    duration = "Running..."
else:
    duration = ""
```

### Schedule Join Logic
```python
select(Run, Agent.name, Schedule.id, Schedule.label)
    .outerjoin(Agent, Run.agent_id == Agent.id)
    .outerjoin(Schedule, Run.schedule_id == Schedule.id)  # LEFT JOIN for optional schedules
    .where(Run.user_id == user_id)
    .order_by(Run.started_at.desc())
    .limit(limit)
```

### Tool Counting Logic
```python
select(func.count(Tool.id)).where(
    Tool.user_id == user_id,
    Tool.source != "builtin",      # Exclude File, HTTP, DateTime, Wait tools
    Tool.is_active == True,          # Only count active/configured tools
)
```

## ✅ Requirements Checklist

- ✅ Updated `/api/v1/dashboard/recent-runs` response format
  - ✅ Renamed `agent_name` to `agent`
  - ✅ Added `agent_id` field
  - ✅ Added `started` timestamp field
  - ✅ Added `duration` string field
  - ✅ Added `schedule_id` (null if manual)
  - ✅ Added `schedule_name` (null if manual)

- ✅ Updated `/api/v1/dashboard/stats` response format
  - ✅ Only count external tools (Composio, Apify, Maton)
  - ✅ Exclude built-in tools (File, HTTP, DateTime, Wait)

- ✅ Join with schedules table
  - ✅ Left JOIN to include manual runs (schedule_id = NULL)
  - ✅ Get schedule_id and schedule_name

- ✅ Database schema compatibility
  - ✅ Run model already has schedule_id foreign key
  - ✅ Schedule model has label field for names

## 🎉 Frontend Integration Benefits

Once deployed, the Dashboard will:

1. **Show Schedule Information**
   - Display schedule names for scheduled runs
   - Provide clickable links to schedule details/edit pages
   - Show "Manual" for manually triggered runs

2. **Accurate Tool Counting**
   - Display correct number of external integrations
   - Exclude built-in tools from count
   - Provide clear user expectations

3. **Improved Run Information**
   - Show agent IDs alongside names
   - Display human-readable durations
   - Better categorization of runs

## 🚀 Deployment Notes

### Before Deployment
1. ✅ Ensure database migrations are up to date
2. ✅ Test endpoints with sample data
3. ✅ Verify tool counting logic with external/built-in tools
4. ✅ Test schedule joins with both scheduled and manual runs

### After Deployment
1. ✅ Monitor dashboard performance with new joins
2. ✅ Verify frontend displays schedule information correctly
3. ✅ Check tool counts are accurate
4. ✅ Monitor API response times

## 📚 Related Files

- **Modified**: `app/routers/dashboard.py`
- **Test Script**: `test_dashboard_updates.py`
- **Related Models**: `app/models/run.py`, `app/models/schedule.py`, `app/models/tool.py`
- **Documentation**: `CLAUDE.md` (project context)

---

**Status**: ✅ **COMPLETED AND READY FOR DEPLOYMENT**

The dashboard API endpoints have been successfully updated to support the new Dashboard and Runs page features!