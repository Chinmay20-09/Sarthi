def format_project_summary(summaries):
    if not summaries:
        return "No tracked repositories."

    lines = []

    for summary in summaries:
        lines.append(
            f"• {summary['repository']}\n"
            f"  Issues : {summary['open_issues']}\n"
            f"  PRs    : {summary['open_pull_requests']}\n"
            f"  Stars  : {summary['stars']}\n"
            f"  Updated: {summary['last_updated']}\n"
        )

    return "\n".join(lines)