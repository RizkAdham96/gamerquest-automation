import os

from social import meta_publisher

SOURCE_ID = "64021e5d7e5f64e9a3efefe6a3c04d712e5019be42041456988b237e2050f43b"
BASE = (
    "https://raw.githubusercontent.com/"
    "RizkAdham96/gamerquest-automation/main/"
    f"social-published/{SOURCE_ID}"
)
IMAGE_URLS = [
    f"{BASE}/slide-1.png",
    f"{BASE}/slide-2.png",
    f"{BASE}/slide-3.png",
]
CAPTION = (
    "Ocarina of Time revient sur Switch 2. "
    "Le Direct du 40e anniversaire de Zelda a confirmé le remake et sa sortie "
    "le 5 novembre 2026. Plus d'infos sur gamerquestfr.com.\n\n"
    "#Zelda #OcarinaOfTime #NintendoSwitch2 #GamerQuestFR"
)


def main():
    token = os.environ["META_FB_PAGE_ACCESS_TOKEN"].strip()
    ig_user_id = os.environ["META_IG_USER_ID"].strip()
    if not token or not ig_user_id:
        raise RuntimeError("Missing Meta Instagram credentials")

    meta_publisher.INSTAGRAM_GRAPH_BASE_URL = meta_publisher.FACEBOOK_GRAPH_BASE_URL

    result = meta_publisher.publish_instagram_carousel(
        image_urls=IMAGE_URLS,
        caption=CAPTION,
        ig_user_id=ig_user_id,
        access_token=token,
    )
    print("Corrected Instagram carousel published.")
    print(f"Instagram media ID: {result.get('post_id', '')}")


if __name__ == "__main__":
    main()
