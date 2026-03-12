#!/usr/bin/env python3
"""Stepik MCP Server — manage courses, sections, lessons, and steps via Stepik API."""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from mcp.server.fastmcp import FastMCP

# --- Config -----------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

CLIENT_ID = os.environ.get("STEPIK_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("STEPIK_CLIENT_SECRET", "")

if not CLIENT_ID or not CLIENT_SECRET:
    raise SystemExit("STEPIK_CLIENT_ID and STEPIK_CLIENT_SECRET environment variables are required")

BASE_URL = "https://stepik.org/api"
TOKEN_URL = "https://stepik.org/oauth2/token/"

mcp = FastMCP(
    "stepik",
    instructions=(
        "Stepik MCP Server — manage online courses on Stepik.\n\n"
        "Hierarchy: Course → Sections → Units → Lessons → Steps.\n"
        "- Use stepik_list_courses to find your courses.\n"
        "- Use stepik_get_course to inspect a course.\n"
        "- Use stepik_get_sections to list sections (modules) of a course.\n"
        "- Use stepik_get_lessons to list lessons in a section.\n"
        "- Use stepik_get_steps to list steps in a lesson.\n"
        "- Steps are the actual content: text, video, quiz, etc.\n"
        "- Use stepik_create_* in order: course → section → lesson → unit → step.\n"
        "Note: lesson titles are limited to 64 characters on Stepik."
    ),
)

# --- Auth -------------------------------------------------------------------
_token_cache: dict[str, Any] = {"token": None, "expires": 0}


def _get_token() -> str:
    if _token_cache["token"] and time.time() < _token_cache["expires"]:
        return _token_cache["token"]

    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}".encode()
    import base64
    auth_header = base64.b64encode(credentials).decode()

    data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())

    token = result.get("access_token", "")
    if not token:
        raise RuntimeError(f"Auth failed: {result}")

    expires_in = result.get("expires_in", 3600)
    _token_cache["token"] = token
    _token_cache["expires"] = time.time() + expires_in - 60
    return token


def _api(method: str, path: str, body: Any = None, params: dict | None = None) -> Any:
    token = _get_token()
    url = f"{BASE_URL}/{path.lstrip('/')}"
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} {method} {url}: {body_text}") from e


# --- Tools ------------------------------------------------------------------

@mcp.tool()
def stepik_list_courses(page: int = 1) -> str:
    """List your own courses on Stepik (as instructor)."""
    result = _api("GET", "courses", params={"is_my_own": "true", "page": page})
    courses = result.get("courses", [])
    if not courses:
        return "No courses found."
    lines = []
    for c in courses:
        lines.append(
            f"ID={c['id']} | {c['title']} | "
            f"published={c.get('is_enabled', False)} | "
            f"learners={c.get('learners_count', 0)}"
        )
    meta = result.get("meta", {})
    lines.append(f"\nPage {meta.get('page', 1)}/{meta.get('pages_count', 1)}")
    return "\n".join(lines)


@mcp.tool()
def stepik_get_course(course_id: int) -> str:
    """Get detailed info about a course by ID."""
    result = _api("GET", f"courses/{course_id}")
    courses = result.get("courses", [])
    if not courses:
        return f"Course {course_id} not found."
    c = courses[0]
    return json.dumps({
        "id": c["id"],
        "title": c["title"],
        "summary": c.get("summary", ""),
        "workload": c.get("workload", ""),
        "is_enabled": c.get("is_enabled", False),
        "learners_count": c.get("learners_count", 0),
        "certificate_footer": c.get("certificate_footer", ""),
        "url": f"https://stepik.org/course/{c['id']}",
        "edit_url": f"https://stepik.org/course/{c['id']}/edit",
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def stepik_create_course(
    title: str,
    summary: str = "",
    workload: str = "",
    target_audience: str = "",
    requirements: str = "",
) -> str:
    """Create a new course on Stepik (created as draft)."""
    body = {
        "course": {
            "title": title,
            "summary": summary,
            "workload": workload,
            "target_audience": target_audience,
            "requirements": requirements,
            "is_enabled": False,
        }
    }
    result = _api("POST", "courses", body)
    c = result["courses"][0]
    return f"Course created: ID={c['id']} — {c['title']}\nEdit: https://stepik.org/course/{c['id']}/edit"


@mcp.tool()
def stepik_update_course(
    course_id: int,
    title: str | None = None,
    summary: str | None = None,
    workload: str | None = None,
    target_audience: str | None = None,
    requirements: str | None = None,
    is_enabled: bool | None = None,
    certificate_footer: str | None = None,
) -> str:
    """Update course metadata. Only provided fields are changed."""
    patch: dict[str, Any] = {}
    if title is not None:
        patch["title"] = title
    if summary is not None:
        patch["summary"] = summary
    if workload is not None:
        patch["workload"] = workload
    if target_audience is not None:
        patch["target_audience"] = target_audience
    if requirements is not None:
        patch["requirements"] = requirements
    if is_enabled is not None:
        patch["is_enabled"] = is_enabled
    if certificate_footer is not None:
        patch["certificate_footer"] = certificate_footer

    if not patch:
        return "Nothing to update."

    result = _api("PUT", f"courses/{course_id}", {"course": patch})
    c = result["courses"][0]
    return f"Course updated: ID={c['id']} — {c['title']}"


@mcp.tool()
def stepik_publish_course(course_id: int) -> str:
    """Publish a course (make it visible to learners)."""
    result = _api("PUT", f"courses/{course_id}", {"course": {"is_enabled": True}})
    c = result["courses"][0]
    return f"Course published: https://stepik.org/course/{c['id']}"


@mcp.tool()
def stepik_get_sections(course_id: int) -> str:
    """List all sections (modules) in a course."""
    result = _api("GET", "sections", params={"course": course_id})
    sections = result.get("sections", [])
    if not sections:
        return f"No sections found in course {course_id}."
    lines = []
    for s in sorted(sections, key=lambda x: x.get("position", 0)):
        lines.append(f"ID={s['id']} | pos={s['position']} | {s['title']}")
    return "\n".join(lines)


@mcp.tool()
def stepik_create_section(course_id: int, title: str, position: int = 1) -> str:
    """Create a section (module) in a course."""
    body = {
        "section": {
            "course": course_id,
            "title": title,
            "position": position,
            "required_percent": 100,
        }
    }
    result = _api("POST", "sections", body)
    s = result["sections"][0]
    return f"Section created: ID={s['id']} — {s['title']} (pos={s['position']})"


@mcp.tool()
def stepik_update_section(section_id: int, title: str | None = None, position: int | None = None) -> str:
    """Update a section title or position."""
    patch: dict[str, Any] = {"id": section_id}
    if title is not None:
        patch["title"] = title
    if position is not None:
        patch["position"] = position
    result = _api("PUT", f"sections/{section_id}", {"section": patch})
    s = result["sections"][0]
    return f"Section updated: ID={s['id']} — {s['title']}"


@mcp.tool()
def stepik_get_lessons(section_id: int) -> str:
    """List lessons in a section (via units)."""
    units_result = _api("GET", "units", params={"section": section_id})
    units = units_result.get("units", [])
    if not units:
        return f"No lessons in section {section_id}."

    lesson_ids = [u["lesson"] for u in sorted(units, key=lambda x: x.get("position", 0))]
    ids_param = [("ids[]", lid) for lid in lesson_ids]
    lessons_result = _api("GET", "lessons", params=dict(ids_param))
    lessons_by_id = {l["id"]: l for l in lessons_result.get("lessons", [])}

    lines = []
    for u in sorted(units, key=lambda x: x.get("position", 0)):
        l = lessons_by_id.get(u["lesson"], {})
        lines.append(
            f"unit={u['id']} lesson={u['lesson']} pos={u['position']} | {l.get('title', '?')}"
        )
    return "\n".join(lines)


@mcp.tool()
def stepik_get_lesson(lesson_id: int) -> str:
    """Get lesson details."""
    result = _api("GET", f"lessons/{lesson_id}")
    lessons = result.get("lessons", [])
    if not lessons:
        return f"Lesson {lesson_id} not found."
    l = lessons[0]
    return json.dumps({
        "id": l["id"],
        "title": l["title"],
        "steps_count": l.get("steps_count", 0),
        "is_public": l.get("is_public", False),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def stepik_create_lesson(title: str, is_public: bool = False) -> str:
    """Create a lesson. Title max 64 chars. Returns lesson ID."""
    title = title[:64]
    body = {"lesson": {"title": title, "is_public": is_public}}
    result = _api("POST", "lessons", body)
    l = result["lessons"][0]
    return f"Lesson created: ID={l['id']} — {l['title']}"


@mcp.tool()
def stepik_update_lesson(lesson_id: int, title: str | None = None, is_public: bool | None = None) -> str:
    """Update lesson title or visibility."""
    patch: dict[str, Any] = {"id": lesson_id}
    if title is not None:
        patch["title"] = title[:64]
    if is_public is not None:
        patch["is_public"] = is_public
    result = _api("PUT", f"lessons/{lesson_id}", {"lesson": patch})
    l = result["lessons"][0]
    return f"Lesson updated: ID={l['id']} — {l['title']}"


@mcp.tool()
def stepik_create_unit(section_id: int, lesson_id: int, position: int = 1) -> str:
    """Attach a lesson to a section (creates a unit). Do this after stepik_create_lesson."""
    body = {"unit": {"section": section_id, "lesson": lesson_id, "position": position}}
    result = _api("POST", "units", body)
    u = result["units"][0]
    return f"Unit created: ID={u['id']} (section={section_id}, lesson={lesson_id}, pos={position})"


@mcp.tool()
def stepik_get_steps(lesson_id: int) -> str:
    """List all steps in a lesson."""
    result = _api("GET", "steps", params={"lesson": lesson_id})
    steps = result.get("steps", [])
    if not steps:
        return f"No steps in lesson {lesson_id}."
    lines = []
    for s in sorted(steps, key=lambda x: x.get("position", 0)):
        block = s.get("block", {})
        lines.append(
            f"ID={s['id']} pos={s['position']} type={block.get('name', '?')} | "
            f"{'(has text)' if block.get('text') else ''}"
        )
    return "\n".join(lines)


@mcp.tool()
def stepik_create_text_step(lesson_id: int, text_html: str, position: int = 1) -> str:
    """
    Create a text step in a lesson. text_html is HTML content.
    Use for lesson introductions, explanations, code examples.
    """
    body = {
        "step-source": {
            "lesson": lesson_id,
            "position": position,
            "block": {
                "name": "text",
                "text": text_html,
            },
        }
    }
    result = _api("POST", "step-sources", body)
    s = result["step-sources"][0]
    return f"Text step created: ID={s['id']} in lesson {lesson_id} at position {position}"


@mcp.tool()
def stepik_update_text_step(step_source_id: int, text_html: str) -> str:
    """Update the HTML content of a text step. Use stepik_get_steps to find step IDs."""
    body = {
        "step-source": {
            "block": {
                "name": "text",
                "text": text_html,
            }
        }
    }
    result = _api("PUT", f"step-sources/{step_source_id}", body)
    s = result["step-sources"][0]
    return f"Step updated: ID={s['id']}"


@mcp.tool()
def stepik_create_quiz_step(
    lesson_id: int,
    question: str,
    choices: list[str],
    correct_indices: list[int],
    position: int = 1,
) -> str:
    """
    Create a multiple-choice quiz step.
    correct_indices: 0-based indices of correct answers.
    Example: choices=["A","B","C"], correct_indices=[1] means B is correct.
    """
    options = [
        {"text": c, "is_correct": i in correct_indices, "feedback": ""}
        for i, c in enumerate(choices)
    ]
    body = {
        "step-source": {
            "lesson": lesson_id,
            "position": position,
            "block": {
                "name": "choice",
                "text": question,
                "source": {
                    "options": options,
                    "is_always_correct": False,
                    "is_html_enabled": True,
                    "preserve_order": False,
                    "is_multiple_choice": len(correct_indices) > 1,
                    "sample_size": len(choices),
                },
            },
        }
    }
    result = _api("POST", "step-sources", body)
    s = result["step-sources"][0]
    return f"Quiz step created: ID={s['id']} in lesson {lesson_id}"


@mcp.tool()
def stepik_delete_section(section_id: int) -> str:
    """Delete a section by ID."""
    _api("DELETE", f"sections/{section_id}")
    return f"Section {section_id} deleted."


@mcp.tool()
def stepik_delete_lesson(lesson_id: int) -> str:
    """Delete a lesson by ID."""
    _api("DELETE", f"lessons/{lesson_id}")
    return f"Lesson {lesson_id} deleted."


@mcp.tool()
def stepik_health_check() -> str:
    """Verify connection and auth to Stepik API."""
    token = _get_token()
    return f"Connected to Stepik API. Token acquired (len={len(token)})."


if __name__ == "__main__":
    mcp.run()
