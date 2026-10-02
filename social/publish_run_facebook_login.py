"""Run Meta publishing with Instagram routed through Facebook Graph.

GamerQuest authenticates Meta publishing with Facebook/Page access tokens.
For that authentication flow, the Instagram professional account endpoints
(/<ig-user-id>/media and /media_publish) must use graph.facebook.com.
"""

from social import meta_publisher

# The existing publisher functions read this module-level base URL at call time.
# Override only the Instagram host; request payloads and safety/history logic stay
# exactly the same.
meta_publisher.INSTAGRAM_GRAPH_BASE_URL = (
    meta_publisher.FACEBOOK_GRAPH_BASE_URL
)

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from social.publish_run import run_publish  # noqa: E402


def main():
    result = run_publish()
    history = meta_publisher.load_publish_history()
    entry = history[result["source_id"]]["instagram"]
    # Keep the successful publish ID in history if verification fails.
    # Recovery must read back that ID rather than create a duplicate post.
    for attempt in range(3):
        try:
            evidence = meta_publisher.verify_instagram_carousel(
                entry["post_id"], os.environ["META_IG_ACCESS_TOKEN"],
            )
            break
        except RuntimeError:
            if attempt == 2:
                raise
            time.sleep(5)
    entry.update(evidence)
    entry["verified_at_utc"] = datetime.now(timezone.utc).isoformat()
    meta_publisher.save_publish_history(history)
    Path("social-publication-evidence.json").write_text(
        json.dumps({**result, "instagram": evidence}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"VERIFIED INSTAGRAM CAROUSEL: {evidence['permalink']}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as file:
            file.write(f"\nVerified Instagram carousel: {evidence['permalink']} (3 slides)\n")
    return result


if __name__ == "__main__":
    print("Instagram Graph route: Facebook Graph (Page/Facebook Login token flow)")
    main()
