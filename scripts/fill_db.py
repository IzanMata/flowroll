import json

import requests
from bs4 import BeautifulSoup
from ftfy import fix_text

TECHNIQUE_URLS = [
    ("Americana Armlock", "https://www.blackbeltwiki.com/americana-armlock"),
    (
        "Americana Armlock Escapes",
        "https://www.blackbeltwiki.com/americana-armlock-escapes",
    ),
    ("Anaconda Choke", "https://www.blackbeltwiki.com/anaconda-choke"),
    ("Anaconda Choke Escapes", "https://www.blackbeltwiki.com/anaconda-choke-escapes"),
    ("Ankle Lock", "https://www.blackbeltwiki.com/ankle-lock"),
    ("Ankle Lock Counter", "https://www.blackbeltwiki.com/ankle-lock-counter"),
    ("Armbar From Guard", "https://www.blackbeltwiki.com/armbar-from-guard"),
    (
        "Armbar From The Mounted Position",
        "https://www.blackbeltwiki.com/armbar-from-the-mounted-position",
    ),
    (
        "Armbar From Side Control",
        "https://www.blackbeltwiki.com/armbar-from-side-control",
    ),
    ("Armbar Defense", "https://www.blackbeltwiki.com/armbar-defense"),
    ("Arm Triangle", "https://www.blackbeltwiki.com/arm-triangle"),
    ("Bicep Slicer", "https://www.blackbeltwiki.com/bicep-slicer"),
    ("Brabo Choke", "https://www.blackbeltwiki.com/brabo-choke"),
    ("Butterfly Guard", "https://www.blackbeltwiki.com/butterfly-guard"),
    ("Butterfly Sweep", "https://www.blackbeltwiki.com/butterfly-sweep"),
    ("Calf Crusher", "https://www.blackbeltwiki.com/calf-crusher"),
    ("Clock Choke", "https://www.blackbeltwiki.com/clock-choke"),
    ("Cobra Choke", "https://www.blackbeltwiki.com/cobra-choke"),
    ("Cross Collar Choke", "https://www.blackbeltwiki.com/cross-collar-choke"),
    ("Crucifix Choke", "https://www.blackbeltwiki.com/crucifix-choke"),
    ("D’Arce Choke", "https://www.blackbeltwiki.com/brabo-choke"),
    ("Double Leg Takedown", "https://www.blackbeltwiki.com/double-leg-takedown"),
    ("Ezekiel Choke", "https://www.blackbeltwiki.com/ezekiel-choke"),
    ("Flying Armbar", "https://www.blackbeltwiki.com/flying-armbar"),
    ("Gogoplata", "https://www.blackbeltwiki.com/gogoplata"),
    ("Guillotine Choke", "https://www.blackbeltwiki.com/guillotine-choke"),
    ("Heel Hook", "https://www.blackbeltwiki.com/heel-hook"),
    ("Kimura From Guard", "https://www.blackbeltwiki.com/kimura-from-the-guard"),
    (
        "Knee Bar From Side Control",
        "https://www.blackbeltwiki.com/knee-bar-from-side-control",
    ),
    ("North South Choke", "https://www.blackbeltwiki.com/north-south-choke"),
    ("Omoplata Shoulder Lock", "https://www.blackbeltwiki.com/omoplata-shoulder-lock"),
    ("Peruvian Necktie", "https://www.blackbeltwiki.com/peruvian-necktie"),
    ("Rear Naked Choke", "https://www.blackbeltwiki.com/rear-naked-choke"),
    ("Scarf Hold", "https://www.blackbeltwiki.com/scarf-hold"),
    ("Side Control Escapes", "https://www.blackbeltwiki.com/side-control-escapes"),
    ("Spider Guard", "https://www.blackbeltwiki.com/spider-guard"),
    ("Triangle Choke", "https://www.blackbeltwiki.com/triangle-choke"),
    ("Twister", "https://www.blackbeltwiki.com/twister"),
    ("X-Guard", "https://www.blackbeltwiki.com/x-guard"),
]


def get_description(url):
    """Extrae títulos (<strong>) y videos (iframe) de una página de BlackBeltWiki."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; BJJBot/1.0)"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        techniques = []
        incorrect = [
            "All rights reserved",
            "Wiki",
            "Privacy Policy",
            "Terms of Service",
            "Contact Us",
            "Make Your Own Hom",
            "Martial arts books are great",
        ]

        # Extraer todos los <strong> con texto
        strong_tags = soup.find_all("strong")
        if strong_tags:
            for tag in strong_tags:
                text = tag.get_text().strip()
                if any(inc in text for inc in incorrect) or not text:
                    continue
                text = fix_text(text)

                # Buscar iframes que estén justo después del <strong>
                videos = []
                next_elements = tag.find_all_next(["iframe"], limit=3)
                for iframe in next_elements:
                    src = iframe.get("src", "")
                    if "youtube" in src:
                        # convertir embed → watch
                        if "youtube.com/embed/" in src:
                            video_id = src.split("/embed/")[-1].split("?")[0]
                            src = f"https://www.youtube.com/watch?v={video_id}"
                        videos.append(src)

                techniques.append({"title": text, "videos": videos})
        else:
            # Si no hay ningún <strong>, intenta buscar iframes genéricos
            generic_videos = []
            for iframe in soup.find_all("iframe"):
                src = iframe.get("src", "")
                if "youtube" in src:
                    if "youtube.com/embed/" in src:
                        video_id = src.split("/embed/")[-1].split("?")[0]
                        src = f"https://www.youtube.com/watch?v={video_id}"
                    generic_videos.append(src)
            if generic_videos:
                techniques.append({"title": "Main Technique", "videos": generic_videos})

        return techniques or [{"title": "No description found", "videos": []}]
    except Exception as e:
        return [{"title": f"Error fetching {url}: {e}", "videos": []}]


def main():
    _json = {}

    for name, url in TECHNIQUE_URLS:
        data = get_description(url)
        _json[name] = {"variations": data, "url": url}
        print(f"✅ {name} → {len(data)} técnicas encontradas")

    # Guardar en JSON
    with open("techniques_variations.json", "w", encoding="utf-8") as f:
        json.dump(_json, f, indent=4, ensure_ascii=False)

    print("\n🎉 Archivo 'techniques_variations.json' generado correctamente.")


if __name__ == "__main__":
    main()
