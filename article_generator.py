from datetime import datetime


def format_price(price):
    if price == 0:
        return "GRATUIT"

    return f"{price:.2f} €".replace(".", ",")


def format_date(date_string):
    if not date_string:
        return None

    try:
        date = datetime.fromisoformat(
            date_string.replace("Z", "+00:00")
        )

        months = {
            1: "janvier",
            2: "février",
            3: "mars",
            4: "avril",
            5: "mai",
            6: "juin",
            7: "juillet",
            8: "août",
            9: "septembre",
            10: "octobre",
            11: "novembre",
            12: "décembre",
        }

        return (
            f"{date.day} "
            f"{months[date.month]} "
            f"{date.year}"
        )

    except (ValueError, TypeError):
        return None


def generate_deal_article(deal, source_id):
    title = deal["title"]
    store = deal["store"]

    original_price = float(
        deal.get("original_price", 0)
    )

    current_price = float(
        deal.get("current_price", 0)
    )

    discount = int(
        deal.get("discount_percent", 0)
    )

    deal_url = deal.get("url", "")

    expires_at = format_date(
        deal.get("expires_at")
    )

    is_free = current_price == 0

    if is_free:
        post_title = (
            f"{title} est gratuit sur "
            f"{store} pendant une durée limitée"
        )

        excerpt = (
            f"{title}, habituellement proposé à "
            f"{format_price(original_price)}, "
            f"est actuellement disponible gratuitement "
            f"sur {store}."
        )

        intro = (
            f"<p><strong>{title}</strong> est actuellement "
            f"disponible gratuitement sur "
            f"<strong>{store}</strong>. "
            f"Le jeu est habituellement vendu "
            f"{format_price(original_price)}.</p>"
        )

    else:
        post_title = (
            f"{title} à -{discount}% sur {store}"
        )

        excerpt = (
            f"{title} bénéficie actuellement d'une "
            f"réduction de {discount}% sur {store}, "
            f"passant de {format_price(original_price)} "
            f"à {format_price(current_price)}."
        )

        intro = (
            f"<p><strong>{title}</strong> bénéficie "
            f"actuellement d'une réduction de "
            f"<strong>{discount}%</strong> sur "
            f"<strong>{store}</strong>.</p>"
        )

    price_section = (
        "<h2>Prix de l'offre</h2>"
        "<ul>"
        f"<li>Prix habituel : "
        f"<strong>{format_price(original_price)}</strong></li>"
        f"<li>Prix actuel : "
        f"<strong>{format_price(current_price)}</strong></li>"
        f"<li>Réduction : "
        f"<strong>{discount}%</strong></li>"
        "</ul>"
    )

    expiration_section = ""

    if expires_at:
        expiration_section = (
            "<h2>Jusqu'à quand l'offre est-elle disponible ?</h2>"
            f"<p>L'offre est annoncée jusqu'au "
            f"<strong>{expires_at}</strong>. "
            f"Elle peut être modifiée ou retirée par la "
            f"plateforme.</p>"
        )

    cta_section = (
        "<h2>Comment profiter de l'offre ?</h2>"
        f"<p>Rendez-vous directement sur "
        f"<strong>{store}</strong> pour consulter l'offre "
        f"et vérifier sa disponibilité.</p>"
        f'<p><a href="{deal_url}" rel="nofollow noopener" '
        f'target="_blank">Voir l’offre sur {store}</a></p>'
    )

    disclaimer = (
        "<p><em>Les prix et disponibilités peuvent évoluer. "
        "GamerQuest vous recommande de vérifier les conditions "
        "directement sur la boutique avant toute acquisition."
        "</em></p>"
    )

    content = (
        intro
        + price_section
        + expiration_section
        + cta_section
        + disclaimer
    )

    return {
        "source_id": source_id,
        "title": post_title,
        "excerpt": excerpt,
        "content": content,
        "source_url": deal_url,
        "deal": {
            "game": title,
            "store": store,
            "original_price": original_price,
            "current_price": current_price,
            "discount_percent": discount,
            "expires_at": deal.get("expires_at"),
        },
    }
