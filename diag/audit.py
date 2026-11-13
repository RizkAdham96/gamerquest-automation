import io, os, requests
from PIL import Image, ImageFilter, ImageStat
from requests.auth import HTTPBasicAuth
B = os.environ.get("WP_URL", "https://gamerquestfr.com").rstrip("/")
A = HTTPBasicAuth(os.environ["WP_USERNAME"], os.environ["WP_APP_PASSWORD"])
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 GamerQuest-Audit"
posts = []
for page in (1, 2, 3):
    r = S.get(f"{B}/wp-json/wp/v2/posts", params={"per_page": 100, "page": page, "_fields": "id,slug,date,featured_media,categories"}, auth=A, timeout=60)
    if r.status_code != 200: break
    posts += r.json()
cats = {c["id"]: c["slug"] for c in S.get(f"{B}/wp-json/wp/v2/categories", params={"per_page": 100}, timeout=60).json()}
ids = sorted({p["featured_media"] for p in posts})
media = {}
for i in range(0, len(ids), 100):
    for m in S.get(f"{B}/wp-json/wp/v2/media", params={"include": ",".join(map(str, ids[i:i+100])), "per_page": 100, "_fields": "id,source_url,media_details"}, auth=A, timeout=60).json():
        media[m["id"]] = m
blank = []; from collections import Counter; tot = Counter(); bl = Counter()
for p in posts:
    m = media[p["featured_media"]]
    sizes = (m.get("media_details") or {}).get("sizes") or {}
    url = (sizes.get("medium") or {}).get("source_url") or m["source_url"]
    im = Image.open(io.BytesIO(S.get(url, timeout=60).content)).convert("L").resize((320, 168))
    e = ImageStat.Stat(im.filter(ImageFilter.FIND_EDGES)).mean[0]
    c = ",".join(cats.get(x, str(x)) for x in p["categories"]); tot[c] += 1
    if e < 4: blank.append((p["date"][:10], c, p["slug"], round(e, 2), m["source_url"].rsplit("/", 1)[-1])); bl[c] += 1
print("CHECKED", len(posts), "BLANK", len(blank))
print("BY_CATEGORY", {k: f"{bl[k]}/{tot[k]}" for k in tot})
for b in blank: print("  BLANK", *b)
