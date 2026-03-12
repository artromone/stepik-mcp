# stepik-mcp

MCP server for managing [Stepik](https://stepik.org) courses from Claude Code, Cursor, or any MCP-compatible client.

## 20 Tools

| Category | Tools |
|----------|-------|
| **Courses** | `stepik_list_courses`, `stepik_get_course`, `stepik_create_course`, `stepik_update_course`, `stepik_publish_course` |
| **Sections** | `stepik_get_sections`, `stepik_create_section`, `stepik_update_section`, `stepik_delete_section` |
| **Lessons** | `stepik_get_lessons`, `stepik_get_lesson`, `stepik_create_lesson`, `stepik_update_lesson`, `stepik_delete_lesson` |
| **Units** | `stepik_create_unit` |
| **Steps** | `stepik_get_steps`, `stepik_create_text_step`, `stepik_update_text_step`, `stepik_create_quiz_step` |
| **Health** | `stepik_health_check` |

## Quick Start

### 1. Get API Credentials

Go to [stepik.org/oauth2/applications/](https://stepik.org/oauth2/applications/) → Create application → Client type: `Confidential`, Grant type: `Client credentials`.

Copy the **Client ID** and **Client Secret**.

### 2. Install

```bash
git clone https://github.com/seniorcat/stepik-mcp.git
cd stepik-mcp
pip install mcp
```

Or with uv:

```bash
uv pip install mcp
```

### 3. Configure

Set environment variables:

```bash
export STEPIK_CLIENT_ID=your-client-id
export STEPIK_CLIENT_SECRET=your-client-secret
```

Or create a `.env` file next to the server script:

```env
STEPIK_CLIENT_ID=your-client-id
STEPIK_CLIENT_SECRET=your-client-secret
```

(Requires `pip install python-dotenv`)

### 4. Add to Claude Code

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "stepik": {
      "command": "python3",
      "args": ["/path/to/stepik_mcp_server.py"],
      "env": {
        "STEPIK_CLIENT_ID": "your-client-id",
        "STEPIK_CLIENT_SECRET": "your-client-secret"
      }
    }
  }
}
```

### 5. Add to Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "stepik": {
      "command": "python3",
      "args": ["/path/to/stepik_mcp_server.py"],
      "env": {
        "STEPIK_CLIENT_ID": "your-client-id",
        "STEPIK_CLIENT_SECRET": "your-client-secret"
      }
    }
  }
}
```

## Course Hierarchy

```
Course
└── Section (Module 1, Module 2, ...)
    └── Unit (binding)
        └── Lesson
            └── Step (text, video, quiz, ...)
```

Typical workflow for building a course:

```
stepik_create_course        → get course_id
stepik_create_section       → get section_id (repeat per module)
stepik_create_lesson        → get lesson_id  (repeat per lesson)
stepik_create_unit          → attach lesson to section
stepik_create_text_step     → add content to lesson
stepik_publish_course       → make it visible
```

## Usage Examples

Once connected, your AI assistant can manage Stepik courses directly:

```
"Создай новый курс 'Python для начинающих'"
"Покажи все мои курсы"
"Добавь раздел 'Основы' в курс 12345"
"Создай урок 'Переменные и типы данных' и добавь в раздел 67890"
"Добавь текстовый шаг с объяснением в урок 11111"
"Создай тест с 4 вариантами ответа"
"Опубликуй курс 12345"
```

## Requirements

- Python 3.10+
- Stepik account with instructor access
- `mcp` Python package
- `python-dotenv` (optional)

## Notes

- Lesson titles are limited to **64 characters** by the Stepik API (enforced automatically)
- Courses are created as **drafts** — use `stepik_publish_course` when ready
- OAuth2 tokens are cached and refreshed automatically

## License

MIT
