# Architecture note: all results pass through truncate_result before returning to Claude
# Avoids: Pitfall 2 - large issue bodies overflow context window

MAX_ISSUES = 20
BODY_PREVIEW_CHARS = 500

def truncate_result(issues: list, limit: int = MAX_ISSUES) -> dict:
    effective_limit = min(limit, 50)
    truncated = len(issues) > effective_limit
    result = []
    for issue in issues[:effective_limit]:
        item = dict(issue)
        if "body" in item and item["body"] and len(item["body"]) > BODY_PREVIEW_CHARS:
            item["body"] = item["body"][:BODY_PREVIEW_CHARS] + "... [truncated]"
        result.append(item)
    return {"issues": result, "truncated": truncated, "total_returned": len(result)}
