import logging
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from croniter import croniter

from app.models.schedule import Schedule
from app.core.exceptions import ScheduleParseException
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate
from pydantic import BaseModel, Field
from app.core.system_model import run_system_task
from app.models.agent import Agent as AgentModel

logger = logging.getLogger("ocin")


class _ParsedSchedule(BaseModel):
    """Structured output from schedule label LLM parser."""
    cron: str = Field(description="Standard 5-field Unix cron expression")
    input: str = Field(description="The task agent should perform each time it runs")


def _simple_parse_schedule(label: str) -> str:
    """Simple regex-based cron parser fallback when LLM is unavailable.

    Supports basic patterns:
    - "every minute" -> "* * * * *"
    - "every 5 minutes" -> "*/5 * * * *"
    - "every day" -> "0 0 * * *"
    - "every day at 9am" -> "0 9 * * *"
    - "daily" -> "0 0 * * *"
    - "hourly" -> "0 * * * *"
    """
    text = label.strip().lower()

    # Every minute patterns
    if re.match(r'^every\s+minute\b', text):
        return "* * * * *"
    if re.match(r'^every\s+\d+\s+minutes?\b', text):
        match = re.search(r'\d+', text)
        if match:
            mins = match.group()
            return f"*/{mins} * * * *"

    # Every day patterns
    if re.match(r'^every\s+day\b', text):
        return "0 0 * * *"
    if re.match(r'^daily\b', text):
        return "0 0 * * *"

    # Every day at time patterns
    time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', text)
    if time_match and re.search(r'every\s+day\s+at\b', text):
        hour = int(time_match.group(1))
        minute = int(time_match.group(2)) if time_match.group(2) else 0
        ampm = time_match.group(3)
        if ampm and ampm.lower() == 'pm' and hour != 12:
            hour += 12
        return f"{minute} {hour} * * *"

    # Hourly pattern
    if re.match(r'^hourly\b', text):
        return "0 * * * *"

    # Default fallback
    return "0 0 * * *"


def _extract_task_hint(label: str) -> str:
    """Heuristic task extraction used ONLY when LLM path is unavailable."""
    text = label.strip()
    lower = text.lower()
    prefixes = [
        r"^please\s+",
        r"^create\s+a\s+schedule\s+(that\s+)?",
        r"^make\s+a\s+(run|schedule)\s+(that\s+)?",
        r"^schedule\s+(that\s+)?",
        r"^set\s+up\s+a\s+(run|schedule)\s+(that\s+)?",
    ]
    for pat in prefixes:
        m = re.match(pat, lower)
        if m:
            text = text[m.end():]
            lower = text.lower()
            break
    scheduling = [
        r"\b(every|each)\s+\d+\s+(minutes?|hours?|days?)\b",
        r"\b(every|each)\s+(minute|hour|day|morning|evening|night|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\b(daily|hourly|minutely|weekly)\b",
        r"\bat\s+\d{1,2}(:\d{2})?\s*(am|pm)?\b",
        r"\btwice\s+a\s+day\b",
        r"\bthat\s+runs?\b",
        r'\bname\s+it\s+"[^"]*\.".?',
        r"\bname\s+it\s+'[^']*'\.?",
        r"\b(daily|hourly|minutely|weekly)\b",
    ]
    for pat in scheduling:
        text = re.sub(pat, "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"^(and|that|which)\s+", "", text, flags=re.IGNORECASE)
    text = text.strip(" ,.")
    if not text:
        return "Run: scheduled task."
    return text[0].upper() + text[1:] + ("." if not text.endswith((".", "!", "?")) else "")


async def _parse_schedule_with_llm(
    db: AsyncSession,
    user_id: str,
    label: str,
) -> dict:
    """Parse a plain-language schedule label into {'cron': ..., 'input': ...}.

    Uses user's coordinator model via PydanticAI. Falls back to regex
    parser if no coordinator is configured, LLM call fails, or returned
    cron is invalid.
    """
    system_prompt = (
        "You extract a cron schedule AND a task description from natural-language "
        "schedule requests in ANY language.\n\n"
        "Rules for `cron`:\n"
        "  - Standard 5-field Unix cron: minute hour day month weekday\n"
        "  - 'every minute' -> * * * * *\n"
        "  - 'every 5 minutes' -> */5 * * * *\n"
        "  - 'every day at 9am' -> 0 9 * * *\n"
        "  - 'every Monday at 8am' -> 0 8 * * 1\n\n"
        "Rules for `input`:\n"
        "  - The task/instruction that agent should perform each time it runs.\n"
        "  - Keep it in ORIGINAL user's language, do NOT translate.\n"
        "  - Strip out scheduling words and meta-words in ANY language.\n"
        "  - Keep quoted literals as-is including their quotes.\n"
        "  - If no task is specified, use: language of input or 'Run: scheduled task.'\n\n"
        "Examples:\n"
        "  Input (EN): Create a schedule that runs every minute and says \"ping\" in output\n"
        "  Output: cron=\"* * * * *\", input='Say \"ping\" in the output.'\n\n"
        "  Input (ES): Cada mañana a las 9 revisa mi correo y resúmelo\n"
        "  Output: cron=\"0 9 * * *\", input=\"Revisa mi correo y resúmelo.\"\n\n"
        "  Input (ES): cada 30 minutos\n"
        "  Output: cron=\"*/30 * * * *\", input=\"Ejecuta: tarea programada.\"\n\n"
        "  Input (FR): Toutes les matins à 9h, vérifie mes emails\n"
        "  Output: cron=\"0 9 * * *\", input=\"Vérifie mes emails.\"\n\n"
        "  Input (DE): Jeden Montag um 8 Uhr\n"
        "  Output: cron=\"0 8 * * 1\", input=\"Ausführen: geplante Aufgabe.\""
    )

    result = await run_system_task(
        db=db,
        user_id=user_id,
        system_prompt=system_prompt,
        user_message=f"Label: {label}",
        result_type=_ParsedSchedule,
        max_tokens=256,
        temperature=0.0,
    )

    if result is None:
        # Fallback to regex parser when no coordinator/API key available
        cron_expr = _simple_parse_schedule(label)
        try:
            croniter(cron_expr)
        except (ValueError, TypeError):
            raise ScheduleParseException(
                "Could not understand schedule. Try 'every minute', 'every 5 minutes', "
                "'every day at 9am', or 'every Monday at 8am'."
            )
        input_text = _extract_task_hint(label)
        logger.info({
            "event": "parse_schedule_regex",
            "cron": cron_expr,
            "input": input_text,
            "label": label,
        })
        return {"cron": cron_expr, "input": input_text}

    cron_expr = (result.cron or "").strip().strip("`'\"")
    input_text = (result.input or "").strip() or "Run: scheduled task."
    try:
        croniter(cron_expr)
        logger.info({
            "event": "parse_schedule_llm",
            "cron": cron_expr,
            "input": input_text,
            "label": label,
        })
        return {"cron": cron_expr, "input": input_text}
    except (ValueError, TypeError):
        logger.warning({
            "event": "parse_schedule_llm_invalid_cron",
            "invalid_cron": cron_expr,
            "label": label,
        })
        # fall through to regex

    # Fallback: regex parser + heuristic input extraction
    cron_expr = _simple_parse_schedule(label)
    try:
        croniter(cron_expr)
    except (ValueError, TypeError):
        raise ScheduleParseException(
            "Could not understand schedule. Try 'every minute', 'every 5 minutes', "
            "'every day at 9am', or 'every Monday at 8am'."
        )
    input_text = _extract_task_hint(label)
    logger.info({
        "event": "parse_schedule_regex",
        "cron": cron_expr,
        "input": input_text,
        "label": label,
    })
    return {"cron": cron_expr, "input": input_text}


async def parse_schedule_label(
    db: AsyncSession,
    user_id: str,
    label: str,
) -> dict:
    """Parse a plain-language schedule label to {'cron': ..., 'input': ...}."""
    parsed = await _parse_schedule_with_llm(db, user_id, label)
    try:
        croniter(parsed["cron"])
        return parsed
    except (ValueError, TypeError) as e:
        logger.error({"event": "parse_schedule", "error": str(e), "label": label})
        raise ScheduleParseException(f"Invalid cron expression generated: {str(e)}")


def calculate_next_run(cron_expression: str) -> datetime:
    """Calculate next run time from a cron expression."""
    cron = croniter(cron_expression, datetime.utcnow())
    return cron.get_next(datetime)


async def create_schedule(
    db: AsyncSession,
    user_id: str,
    schedule_data: ScheduleCreate,
) -> Schedule:
    """Create a new schedule."""
    # Parse label to cron and input
    parsed = await parse_schedule_label(db, user_id, schedule_data.label)
    cron_expr = parsed["cron"]
    extracted_input = parsed["input"]

    # Verify agent belongs to user
    from app.services.agent_service import get_agent
    agent = await get_agent(db, schedule_data.agent_id, user_id)
    if not agent:
        raise ValueError("Agent not found")

    # Merge extracted input into payload
    payload = dict(schedule_data.payload or {})
    if "input" not in payload or not payload["input"]:
        payload["input"] = extracted_input

    schedule = Schedule(
        user_id=user_id,
        agent_id=schedule_data.agent_id,
        label=schedule_data.label,
        cron_expression=cron_expr,
        trigger_type=schedule_data.trigger_type,
        payload=payload,
        next_run_at=calculate_next_run(cron_expr),
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)

    logger.info({"event": "create_schedule", "schedule_id": str(schedule.id), "user_id": user_id})
    return schedule


async def list_schedules(
    db: AsyncSession,
    user_id: str,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
) -> list[Schedule]:
    """List schedules for a user."""
    query = select(Schedule).where(Schedule.user_id == user_id)
    if active_only:
        query = query.where(Schedule.is_active == True)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_schedule(db: AsyncSession, schedule_id: str, user_id: str) -> Optional[Schedule]:
    """Get a schedule by ID (user-scoped)."""
    result = await db.execute(
        select(Schedule).where(Schedule.id == schedule_id, Schedule.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_schedule(
    db: AsyncSession,
    schedule_id: str,
    user_id: str,
    schedule_data: ScheduleUpdate,
) -> Schedule:
    """Update a schedule."""
    schedule = await get_schedule(db, schedule_id, user_id)
    if not schedule:
        raise ValueError("Schedule not found")

    # If label changed, re-parse to cron and input
    if schedule_data.label is not None and schedule_data.label != schedule.label:
        schedule.label = schedule_data.label
        parsed = await parse_schedule_label(db, user_id, schedule_data.label)
        schedule.cron_expression = parsed["cron"]
        schedule.next_run_at = calculate_next_run(schedule.cron_expression)

        # Merge extracted input into payload
        if schedule_data.payload is None:
            current_payload = dict(schedule.payload or {})
        else:
            current_payload = schedule_data.payload

        if "input" not in current_payload or not current_payload.get("input"):
            current_payload["input"] = parsed["input"]

        schedule.payload = current_payload

    # Update other fields
    if schedule_data.trigger_type is not None:
        schedule.trigger_type = schedule_data.trigger_type
    if schedule_data.payload is not None:
        schedule.payload = schedule_data.payload
    if schedule_data.is_active is not None:
        schedule.is_active = schedule_data.is_active

    await db.commit()
    await db.refresh(schedule)

    logger.info({"event": "update_schedule", "schedule_id": str(schedule.id), "user_id": user_id})
    return schedule


async def delete_schedule(db: AsyncSession, schedule_id: str, user_id: str) -> bool:
    """Delete a schedule."""
    schedule = await get_schedule(db, schedule_id, user_id)
    if not schedule:
        raise ValueError("Schedule not found")

    await db.delete(schedule)
    await db.commit()

    logger.info({"event": "delete_schedule", "schedule_id": str(schedule.id), "user_id": user_id})
    return True


async def pause_schedule(db: AsyncSession, schedule_id: str, user_id: str) -> Schedule:
    """Pause a schedule."""
    schedule = await get_schedule(db, schedule_id, user_id)
    if not schedule:
        raise ValueError("Schedule not found")

    schedule.is_active = False
    await db.commit()
    await db.refresh(schedule)

    logger.info({"event": "pause_schedule", "schedule_id": str(schedule.id), "user_id": user_id})
    return schedule


async def resume_schedule(db: AsyncSession, schedule_id: str, user_id: str) -> Schedule:
    """Resume a schedule."""
    schedule = await get_schedule(db, schedule_id, user_id)
    if not schedule:
        raise ValueError("Schedule not found")

    schedule.is_active = True
    schedule.next_run_at = calculate_next_run(schedule.cron_expression)
    await db.commit()
    await db.refresh(schedule)

    logger.info({"event": "resume_schedule", "schedule_id": str(schedule.id), "user_id": user_id})
    return schedule


async def get_all_active_schedules(db: AsyncSession) -> list[Schedule]:
    """Get all active schedules for scheduler loading."""
    result = await db.execute(
        select(Schedule).where(Schedule.is_active == True, Schedule.trigger_type == "cron")
    )
    return list(result.scalars().all())
