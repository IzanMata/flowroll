import json

import requests
from bs4 import BeautifulSoup

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


# --- Función de ayuda ---
def get_description(url):
    """Extrae la descripción principal de una página del BlackBeltWiki."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; BJJBot/1.0)"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        content_div = soup.find("h1")

        variations = soup.find(id="strong")

        for variations in soup.find_all("strong"):
            text = variations.get_text().strip()
            print(text)
            variations.decompose()

        if not content_div:
            return "No description found."

        text = content_div.get_text(separator="\n").strip()

        return text[:800]
    except Exception as e:
        return f"Error fetching {url}: {e}"


def main():

    json = {}

    for name, url in TECHNIQUE_URLS:

        json[name] = url

        a = get_description(url)
        print(a)


if __name__ == "__main__":
    main()
