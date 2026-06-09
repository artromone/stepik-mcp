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
        "Note: lesson titles are limited to 64 characters on Stepik.\n\n"
        "Grading instructor-reviewed tasks (рецензируется преподавателем):\n"
        "- stepik_get_review_step(step_id): see the task statement, rubric criteria,\n"
        "  max scores and how many submissions are pending.\n"
        "- stepik_list_submissions_to_review(step_id): list pending submissions.\n"
        "- stepik_get_submission(submission_id): one answer + statement + rubric.\n"
        "- stepik_review_submission(submission_id, scores, feedback): grade and submit.\n"
        "  scores is one int per criterion (0..max). This is final — the score goes\n"
        "  to the student, so judge against the rubric before calling it."
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
                    "is_options_feedback": False,
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
def stepik_create_free_answer_step(
    lesson_id: int,
    text_html: str,
    position: int = 1,
    manual_scoring: bool = True,
    has_review: bool = False,
    is_attachments_enabled: bool = False,
    cost: int = 1,
    max_submissions_count: int | None = 5,
    review_criteria: list[str] | None = None,
) -> str:
    """
    Create a free-answer step (open-text answer, manually reviewed).

    Use for practice tasks where the student writes a free-form answer
    (code, explanation, design) and an instructor scores by hand.

    - manual_scoring=True: instructor grades each submission manually (default).
    - has_review=True: enable peer review.
    - is_attachments_enabled=True: allow students to attach files.
    - cost: points awarded for the task (default 1).
    - max_submissions_count: max attempts (default 5; None = unlimited).
    - review_criteria: list of textual criteria for peer/manual review.
    """
    body = {
        "step-source": {
            "lesson": lesson_id,
            "position": position,
            "cost": cost,
            "block": {
                "name": "free-answer",
                "text": text_html,
                "source": {
                    "is_attachments_enabled": is_attachments_enabled,
                    "is_html_enabled": True,
                    "manual_scoring": manual_scoring,
                },
            },
        }
    }
    if max_submissions_count is not None:
        body["step-source"]["max_submissions_count"] = max_submissions_count
    if has_review:
        body["step-source"]["has_review"] = True
    result = _api("POST", "step-sources", body)
    s = result["step-sources"][0]
    source_id = s["id"]

    crit_count = 0
    if review_criteria:
        for text in review_criteria:
            try:
                # criteria endpoint TBD; keeping shim so call signature works
                _api("POST", "review-criteria", {
                    "review-criterion": {"step_source": source_id, "text": text}
                })
                crit_count += 1
            except Exception as e:
                return (
                    f"Free-answer step created: ID={source_id} (lesson {lesson_id}, pos {position}); "
                    f"but failed to add review criterion: {e}"
                )

    extras = []
    if max_submissions_count is not None:
        extras.append(f"max_attempts={max_submissions_count}")
    extras.append(f"cost={cost}")
    if has_review:
        extras.append("peer_review=on")
    if crit_count:
        extras.append(f"criteria={crit_count}")
    return (
        f"Free-answer step created: ID={source_id} in lesson {lesson_id} at position {position} "
        f"({', '.join(extras)})"
    )


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


# --- Review / grading -------------------------------------------------------
#
# Instructor-graded "review" steps (рецензируется преподавателем):
#   step.instruction_type == "instructor"
#   step.instruction  -> instruction with rubrics (each rubric has a `cost` = max score)
#   step.session      -> the single instructor review-session for this step
#
# A student answer is a `submission` (submission.reply.text holds the answer,
# submission.session is the student's review-session).
#
# Grading flow:
#   POST  reviews            {session: <instructor_session>, submission: <id>}  -> draft review + auto rubric-scores
#   PUT   rubric-scores/<id> {score, text}                                       -> one per rubric/criterion
#   PUT   reviews/<id>       {text, is_frozen: true}                             -> finalize; score goes to the student
#
# A submission is "pending" when no frozen review references it.

import re as _re


def _strip_html(html: str) -> str:
    """Collapse HTML to readable plain text."""
    if not html:
        return ""
    text = _re.sub(r"<br\s*/?>", "\n", html, flags=_re.I)
    text = _re.sub(r"</(p|div|li|h[1-6])>", "\n", text, flags=_re.I)
    text = _re.sub(r"<[^>]+>", "", text)
    text = (text.replace("&lt;", "<").replace("&gt;", ">")
                .replace("&amp;", "&").replace("&quot;", '"')
                .replace("&#39;", "'").replace("&nbsp;", " "))
    text = _re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def _step_review_context(step_id: int) -> dict:
    """Resolve instruction, rubrics, instructor session and statement for a review step."""
    step = _api("GET", f"steps/{step_id}")["steps"][0]
    if step.get("instruction_type") != "instructor":
        raise RuntimeError(
            f"Step {step_id} is not instructor-reviewed (instruction_type={step.get('instruction_type')})."
        )
    instruction_id = step["instruction"]
    instructor_session = step["session"]
    instr = _api("GET", f"instructions/{instruction_id}")
    rubrics = sorted(instr.get("rubrics", []), key=lambda r: r.get("position", 0))
    return {
        "step": step,
        "instruction_id": instruction_id,
        "instructor_session": instructor_session,
        "rubrics": rubrics,
        "statement": _strip_html(step.get("block", {}).get("text", "")),
    }


def _instruction_review_state(instruction_id: int) -> dict:
    """
    Paginate all review-sessions of an instruction; map submissions and graded
    state. A student submission counts as graded once its review-session has
    is_taking_finished == True (a finalized instructor review). The instructor's
    own session (submission == None) is ignored. Embedded `reviews` cannot be
    used for this — they carry submission == None until fetched individually.
    """
    sessions: list = []
    submissions: dict[int, Any] = {}
    graded_subs: set[int] = set()
    session_by_id: dict[int, Any] = {}
    page = 1
    while True:
        d = _api("GET", "review-sessions", params={"instruction": instruction_id, "page": page})
        for s in d.get("review-sessions", []):
            sessions.append(s)
            session_by_id[s["id"]] = s
            sub_id = s.get("submission")
            if sub_id and s.get("is_taking_finished"):
                graded_subs.add(sub_id)
        for s in d.get("submissions", []):
            submissions[s["id"]] = s
        if not d.get("meta", {}).get("has_next"):
            break
        page += 1
    return {
        "sessions": sessions,
        "submissions": submissions,
        "graded_subs": graded_subs,
        "session_by_id": session_by_id,
    }


@mcp.tool()
def stepik_get_review_step(step_id: int) -> str:
    """
    Inspect an instructor-reviewed step before grading: the task statement,
    the rubric criteria with their max scores, and how many submissions are
    pending vs already graded. Use this first to learn what to grade against.
    """
    ctx = _step_review_context(step_id)
    state = _instruction_review_state(ctx["instruction_id"])
    pending = graded = 0
    for s in state["sessions"]:
        sub_id = s.get("submission")
        if not sub_id:
            continue  # instructor session
        if sub_id in state["graded_subs"]:
            graded += 1
        else:
            pending += 1
    rubrics = [
        {"rubric_id": r["id"], "position": r.get("position", 0),
         "max_score": r.get("cost", 0), "text": _strip_html(r.get("text", "")) or "(no description)"}
        for r in ctx["rubrics"]
    ]
    total_max = sum(r["max_score"] for r in rubrics)
    return json.dumps({
        "step_id": step_id,
        "statement": ctx["statement"],
        "criteria": rubrics,
        "max_total_score": total_max,
        "pending_count": pending,
        "graded_count": graded,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def stepik_list_submissions_to_review(step_id: int, include_graded: bool = False, limit: int = 30) -> str:
    """
    List student submissions on an instructor-reviewed step.

    By default returns only submissions still awaiting review (pending).
    Each entry includes submission_id (pass it to stepik_review_submission),
    the student's user id, the submission time, and the answer text.
    """
    ctx = _step_review_context(step_id)
    state = _instruction_review_state(ctx["instruction_id"])
    rows = []
    for s in sorted(state["sessions"], key=lambda x: x.get("submission") or 0):
        sub_id = s.get("submission")
        if not sub_id:
            continue
        is_graded = sub_id in state["graded_subs"]
        if is_graded and not include_graded:
            continue
        sub = state["submissions"].get(sub_id, {})
        reply = sub.get("reply", {}) or {}
        entry = {
            "submission_id": sub_id,
            "status": "graded" if is_graded else "pending",
            "session_score": s.get("score"),
            "time": sub.get("time"),
            "answer": _strip_html(reply.get("text", "")),
        }
        rows.append(entry)
        if len(rows) >= limit:
            break
    if not rows:
        return f"No {'submissions' if include_graded else 'pending submissions'} on step {step_id}."
    header = (f"Step {step_id} — {len(rows)} submission(s) "
              f"({'incl. graded' if include_graded else 'pending only'}):\n")
    return header + json.dumps(rows, ensure_ascii=False, indent=2)


@mcp.tool()
def stepik_get_submission(submission_id: int) -> str:
    """
    Get one submission with everything needed to grade it: the student's answer,
    the task statement, and the rubric criteria with max scores. Use before
    stepik_review_submission when grading a single answer.
    """
    sub = _api("GET", f"submissions/{submission_id}")["submissions"][0]
    att = _api("GET", f"attempts/{sub['attempt']}")["attempts"][0]
    ctx = _step_review_context(att["step"])
    state = _instruction_review_state(ctx["instruction_id"])
    reply = sub.get("reply", {}) or {}
    rubrics = [
        {"rubric_id": r["id"], "max_score": r.get("cost", 0),
         "text": _strip_html(r.get("text", "")) or "(no description)"}
        for r in ctx["rubrics"]
    ]
    return json.dumps({
        "submission_id": submission_id,
        "step_id": att["step"],
        "student_user_id": att.get("user"),
        "time": sub.get("time"),
        "already_graded": submission_id in state["graded_subs"],
        "statement": ctx["statement"],
        "criteria": rubrics,
        "max_total_score": sum(r["max_score"] for r in rubrics),
        "answer": _strip_html(reply.get("text", "")),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def stepik_review_submission(
    submission_id: int,
    scores: list[int],
    feedback: str = "",
    criterion_feedback: list[str] | None = None,
    overwrite: bool = False,
) -> str:
    """
    Grade an instructor-reviewed submission and submit the review (final — the
    score is delivered to the student).

    - scores: one integer per rubric criterion, in criterion order (see
      stepik_get_submission). Each must be 0..max_score for that criterion.
      For a single-criterion task pass a one-element list, e.g. [4].
    - feedback: general comment for the student (plain text or HTML).
    - criterion_feedback: optional per-criterion explanations, same order/length
      as scores.
    - overwrite: if the submission was already graded, set True to grade anyway
      (otherwise the call refuses to avoid double-grading).

    Returns the awarded total and a confirmation.
    """
    # Resolve step / instruction / rubrics / instructor session from the submission.
    sub = _api("GET", f"submissions/{submission_id}")["submissions"][0]
    att = _api("GET", f"attempts/{sub['attempt']}")["attempts"][0]
    ctx = _step_review_context(att["step"])
    rubrics = ctx["rubrics"]

    if len(scores) != len(rubrics):
        crit = [f"#{i+1} (max {r.get('cost', 0)})" for i, r in enumerate(rubrics)]
        return (f"Expected {len(rubrics)} score(s), got {len(scores)}. "
                f"Criteria: {', '.join(crit)}.")
    for i, (sc, r) in enumerate(zip(scores, rubrics)):
        cap = r.get("cost", 0)
        if not isinstance(sc, int) or sc < 0 or sc > cap:
            return f"Score for criterion #{i+1} must be an integer 0..{cap}, got {sc}."

    state = _instruction_review_state(ctx["instruction_id"])
    if submission_id in state["graded_subs"] and not overwrite:
        return (f"Submission {submission_id} is already graded. "
                f"Pass overwrite=True to grade it again.")

    # 1. Create the draft review under the instructor session. If this step was
    #    never opened for review, no instructor session exists yet — create one.
    instructor_session = ctx["instructor_session"]
    if not instructor_session:
        sess = _api("POST", "review-sessions", {
            "review-session": {"instruction": ctx["instruction_id"]}
        })
        instructor_session = sess["review-sessions"][0]["id"]
    created = _api("POST", "reviews", {
        "review": {"session": instructor_session, "submission": submission_id}
    })
    review = created["reviews"][0]
    review_id = review["id"]

    # Pull rubric-score objects (auto-created, one per rubric) and map by rubric id.
    rs_objs = created.get("rubric-scores")
    if not rs_objs:
        full = _api("GET", f"reviews/{review_id}")
        rs_objs = full.get("rubric-scores", [])
    rs_by_rubric = {rs["rubric"]: rs for rs in rs_objs}

    # 2. Write each criterion score (+ optional per-criterion text).
    for i, r in enumerate(rubrics):
        rs = rs_by_rubric.get(r["id"])
        if not rs:
            return f"Review {review_id} created but no rubric-score for rubric {r['id']}; aborted before finalizing."
        patch = {"score": scores[i]}
        if criterion_feedback and i < len(criterion_feedback) and criterion_feedback[i]:
            patch["text"] = criterion_feedback[i]
        _api("PUT", f"rubric-scores/{rs['id']}", {"rubric-score": patch})

    # 3. Finalize (freeze) the review.
    finalize: dict[str, Any] = {"is_frozen": True}
    if feedback:
        finalize["text"] = feedback
    _api("PUT", f"reviews/{review_id}", {"review": finalize})

    total = sum(scores)
    max_total = sum(r.get("cost", 0) for r in rubrics)
    return (f"Reviewed submission {submission_id}: {total}/{max_total} "
            f"(criteria: {scores}). Review {review_id} submitted.")


@mcp.tool()
def stepik_list_review_queue(
    course_id: int | None = None,
    section_id: int | None = None,
    show_empty: bool = False,
) -> str:
    """
    Scan a course (or a single section) for instructor-reviewed steps and report
    how many submissions await review on each — the API equivalent of the
    "Проверка решений" page.

    Provide section_id to scan one module (fast), or course_id to scan the whole
    course (slower: one request per lesson). By default only steps with pending
    submissions are listed; set show_empty=True to include zero-pending steps.
    """
    if not course_id and not section_id:
        return "Provide course_id or section_id."

    if section_id:
        section_ids = [section_id]
    else:
        course = _api("GET", f"courses/{course_id}")["courses"][0]
        section_ids = course.get("sections", [])

    results = []
    total_pending = 0
    for sid in section_ids:
        section = _api("GET", f"sections/{sid}")["sections"][0]
        unit_ids = section.get("units", [])
        # Resolve units -> lessons in bulk.
        lesson_ids = []
        for i in range(0, len(unit_ids), 100):
            chunk = unit_ids[i:i + 100]
            ur = _api("GET", "units", params={"ids[]": chunk})
            lesson_ids.extend(u["lesson"] for u in ur.get("units", []))
        for lid in lesson_ids:
            steps = _api("GET", "steps", params={"lesson": lid}).get("steps", [])
            for st in steps:
                if st.get("instruction_type") != "instructor" or not st.get("instruction"):
                    continue
                state = _instruction_review_state(st["instruction"])
                pending = sum(
                    1 for s in state["sessions"]
                    if s.get("submission") and s["submission"] not in state["graded_subs"]
                )
                total_pending += pending
                if pending or show_empty:
                    results.append({
                        "section": section["title"],
                        "step_id": st["id"],
                        "position": st.get("position"),
                        "pending": pending,
                    })

    if not results:
        return f"No pending reviews found (total pending: {total_pending})."
    results.sort(key=lambda r: -r["pending"])
    header = f"{total_pending} submission(s) awaiting review across {len(results)} step(s):\n"
    return header + json.dumps(results, ensure_ascii=False, indent=2)


@mcp.tool()
def stepik_health_check() -> str:
    """Verify connection and auth to Stepik API."""
    token = _get_token()
    return f"Connected to Stepik API. Token acquired (len={len(token)})."


if __name__ == "__main__":
    mcp.run()
