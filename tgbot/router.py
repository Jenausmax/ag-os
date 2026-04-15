import re

TAG_PATTERN = re.compile(r"^@(\w+)\s*(.*)", re.DOTALL)


def parse_message(text: str) -> tuple[str, str]:
    match = TAG_PATTERN.match(text.strip())
    if match:
        agent = match.group(1).lower()
        prompt = match.group(2).strip()
        return agent, prompt
    return "master", text.strip()
