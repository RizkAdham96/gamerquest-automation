import html


def verdict_from_percent(percent):
    if percent >= 90:
        return "Exceptionnellement positif"
    if percent >= 80:
        return "Très positif"
    if percent >= 70:
        return "Positif"
    if percent >= 60:
        return "Plutôt positif"
    if percent >= 40:
        return "Mitigé"
    return "Plutôt négatif"


def stars_from_score(score_5):
    filled = max(0, min(5, int(round(float(score_5)))))
    return "★" * filled + "☆" * (5 - filled)


def _platforms(data):
    source = data.get("platforms") or {}
    names = []
    if source.get("windows"):
        names.append("PC")
    if source.get("mac"):
        names.append("macOS")
    if source.get("linux"):
        names.append("Linux")
    return names


def build_review_record(app, reviews):
    total_positive = int(reviews.get("total_positive") or 0)
    total_negative = int(reviews.get("total_negative") or 0)
    total_reviews = int(reviews.get("total_reviews") or (total_positive + total_negative))
    denominator = total_positive + total_negative
    positive_percent = round(100 * total_positive / denominator) if denominator else 0
    score_5 = round(positive_percent / 20, 1)
    label = verdict_from_percent(positive_percent)
    stars = stars_from_score(score_5)
    formatted_reviews = f"{total_reviews:,}".replace(",", " ")

    name = str(app.get("name") or "Jeu").strip()
    description = str(app.get("short_description") or "").strip()
    developers = ", ".join(str(x) for x in (app.get("developers") or [])) or "Non renseigné"
    genres = ", ".join(str(x.get("description")) for x in (app.get("genres") or []) if x.get("description")) or "Non renseigné"
    platforms = " · ".join(_platforms(app)) or "Non renseigné"
    release_date = str((app.get("release_date") or {}).get("date") or "Non renseignée")

    content = f"""
<article class="gq-review">
<p><strong>Score joueurs GamerQuest : {stars} &nbsp; {score_5}/5 — {html.escape(label)}</strong></p>
<p>{positive_percent}% d’avis positifs sur Steam, sur {formatted_reviews} avis joueurs analysés.</p>
<h2>En bref</h2>
<p>{html.escape(description)}</p>
<ul>
<li><strong>Développeur :</strong> {html.escape(developers)}</li>
<li><strong>Genre :</strong> {html.escape(genres)}</li>
<li><strong>Plateformes Steam :</strong> {html.escape(platforms)}</li>
<li><strong>Sortie :</strong> {html.escape(release_date)}</li>
</ul>
<h2>Que pensent les joueurs ?</h2>
<p>La note affichée par GamerQuest est un <strong>indice basé sur les avis joueurs Steam</strong>. Elle ne prétend pas représenter un test éditorial réalisé par notre rédaction.</p>
<p><strong>{total_positive}</strong> avis positifs · <strong>{total_negative}</strong> avis négatifs.</p>
<h2>Verdict GamerQuest</h2>
<p><strong>{html.escape(label)}</strong>. Cet indice est recalculé automatiquement lorsque la fiche est mise à jour.</p>
</article>
""".strip()

    return {
        "appid": int(app["steam_appid"]),
        "name": name,
        "positive_percent": positive_percent,
        "score_5": score_5,
        "score_label": label,
        "total_reviews": total_reviews,
        "image_url": str(app.get("header_image") or ""),
        "content": content,
        "excerpt": (
            f"{stars}  {score_5}/5 · {label} · "
            f"{positive_percent}% positif · {formatted_reviews} avis Steam"
        ),
    }
