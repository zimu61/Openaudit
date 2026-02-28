import json


def build_source_identification_prompt(
    method_snippets: list[dict], candidates: dict, file_path: str
) -> list[dict]:
    """Build the prompt for identifying user-controlled input sources.

    Args:
        method_snippets: List of {"method_name": str, "method_line": int, "code": str}
                         representing the enclosing method bodies for all candidates.
        candidates: Dict with "parameters" and "calls" lists from Joern.
        file_path: The source file path being analyzed.
    """

    # Build method code sections with a total budget of 12,000 chars
    max_total_code = 12000
    code_sections = []
    budget_remaining = max_total_code

    for snippet in method_snippets:
        name = snippet.get("method_name", "(unknown)")
        line = snippet.get("method_line", "?")
        code = snippet.get("code", "")

        if budget_remaining <= 0:
            code_sections.append(f"### {name} (line {line})\n```\n// ... (omitted — code budget exceeded)\n```")
            continue

        if len(code) > budget_remaining:
            code = code[:budget_remaining] + "\n// ... (truncated)"

        budget_remaining -= len(code)
        code_sections.append(f"### {name} (line {line})\n```\n{code}\n```")

    code_block = "\n\n".join(code_sections) if code_sections else "(no method bodies available)"

    # Format candidates for readability
    params_text = ""
    if candidates.get("parameters"):
        params_text = "## Function Parameters\n"
        for p in candidates["parameters"]:
            params_text += (
                f"- ID:{p['id']} | {p.get('method_name', p.get('method', '?'))}({p['name']}: {p.get('type', '?')}) "
                f"at {p.get('file', '?')}:{p.get('line', '?')}\n"
            )

    calls_text = ""
    if candidates.get("calls"):
        calls_text = "## Function Calls\n"
        for c in candidates["calls"]:
            in_method = c.get("method_name", "")
            method_note = f" in {in_method}()" if in_method else ""
            calls_text += (
                f"- ID:{c['id']} | {c['name']}{method_note} "
                f"at {c.get('file', '?')}:{c.get('line', '?')} | code: {c.get('code', '?')}\n"
            )

    system_message = """You are an expert code security auditor. Your task is to analyze source code and a list of candidate nodes (function parameters and function calls) to identify which ones represent actual user-controlled input (sources).

User-controlled sources include:
- Network input functions (recv, read from socket, HTTP request parameters)
- File input functions (fread, fgets from user-accessible files)
- Command line arguments (argv, argc)
- Environment variables (getenv)
- Standard input (scanf, gets, fgets from stdin)
- Database query results that contain user data
- Web framework request parameters, headers, cookies, body
- Deserialized data from untrusted sources

NOT user-controlled:
- Internal function parameters called only with hardcoded/constant values
- Configuration read from trusted config files
- Constants and literals
- Internal state variables
- Parameters of static/private utility functions with no external callers

Respond with a JSON object containing:
- "source_ids": array of integer node IDs that are user-controlled sources
- "reasoning": brief explanation of why each ID was selected"""

    user_message = f"""Analyze the following code and candidate list from file: {file_path}

## Method Bodies
{code_block}

{params_text}
{calls_text}

Identify which candidate IDs represent actual user-controlled input sources. Return JSON with "source_ids" (array of integers) and "reasoning" (string)."""

    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]
