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

from social.publish_run import main  # noqa: E402


if __name__ == "__main__":
    print("Instagram Graph route: Facebook Graph (Page/Facebook Login token flow)")
    main()
