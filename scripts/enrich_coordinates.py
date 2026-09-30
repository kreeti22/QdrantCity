"""
Enrich data/seed/experiences.json with realistic coordinates, event/movie type, and OSM references.
"""

import json
from pathlib import Path

# Comprehensive venue coordinates mapping
VENUE_COORDINATES = {
    # Delhi Venues
    "Abhimanch Auditorium, NSD": (28.6251, 77.2356),
    "Arun Jaitley Stadium (Feroz Shah Kotla Ground)": (28.6377, 77.2432),
    "Chandni Chowk & Jama Masjid Precinct": (28.6507, 77.2334),
    "Crafts Museum Workshop Studio": (28.6145, 77.2422),
    "Culinary Heritage Studio": (28.5495, 77.2012),
    "Dilli Haat INA": (28.5732, 77.2084),
    "Hazrat Nizamuddin Aulia Dargah": (28.5916, 77.2415),
    "Humayun's Tomb Complex": (28.5933, 77.2507),
    "India Habitat Centre (IHC) Stein Auditorium": (28.5898, 77.2249),
    "Kamani Auditorium": (28.6256, 77.2345),
    "Kathak Kendra": (28.5912, 77.1852),
    "Kiran Nadar Museum of Art": (28.5284, 77.2185),
    "Lodhi Art District": (28.5875, 77.2225),
    "Mystery Rooms": (28.5488, 77.2033),
    "National Crafts Museum & Hastkala Academy": (28.6145, 77.2422),
    "National Gallery of Modern Art (NGMA)": (28.6110, 77.2345),
    "National Museum": (28.6119, 77.2193),
    "North Campus Ridge Forest Gate": (28.6830, 77.2150),
    "PVR Director's Cut": (28.5429, 77.1557),
    "PVR Director's Cut, Ambience Mall": (28.5429, 77.1557),
    "Playground Comedy Studio": (28.5535, 77.1942),
    "Purana Qila Amphitheatre": (28.6096, 77.2437),
    "Qutub Complex": (28.5244, 77.1855),
    "Sanjay Van South Gate": (28.5255, 77.1722),
    "Shri Ram Centre for Performing Arts": (28.6272, 77.2335),
    "Stein Auditorium, India Habitat Centre": (28.5898, 77.2249),
    "The Comedy Store Delhi": (28.6315, 77.2167),
    "The Laugh Store": (28.5284, 77.2185),
    "The Piano Man Jazz Club": (28.5620, 77.1950),

    # Mumbai Venues
    "Artisans' Centre": (18.9298, 72.8335),
    "Bandra Fort Amphitheatre": (19.0416, 72.8197),
    "Banganga Water Tank": (18.9458, 72.7937),
    "CSMVS Museum (Prince of Wales Museum)": (18.9269, 72.8327),
    "Canvas Laugh Club Bandra": (19.0596, 72.8295),
    "Danceworx Performing Arts Academy": (19.1363, 72.8277),
    "Dr. Bhau Daji Lad Museum": (18.9789, 72.8347),
    "Experimental Theatre, NCPA": (18.9261, 72.8206),
    "Gateway of India Jetty to Elephanta Island": (18.9220, 72.8347),
    "Jamshed Bhabha Theatre, NCPA": (18.9261, 72.8206),
    "Jehangir Art Gallery": (18.9275, 72.8317),
    "Kala Ghoda Art Precinct": (18.9298, 72.8335),
    "Kanheri Caves, Sanjay Gandhi National Park": (19.2057, 72.9064),
    "Maratha Mandir Cinema": (18.9696, 72.8194),
    "Marine Drive Promenade": (18.9430, 72.8230),
    "Mohammad Ali Road & Girgaon Chowpatty": (18.9548, 72.8155),
    "NCPA Complex & Prithvi Theatre": (18.9261, 72.8206),
    "Oval Maidan / Fort Precinct": (18.9300, 72.8295),
    "PVR INOX IMAX": (18.9950, 72.8250),
    "PVR INOX IMAX Palladium": (18.9950, 72.8250),
    "Prithvi Theatre": (19.1063, 72.8258),
    "Regal Cinema": (18.9248, 72.8319),
    "Royal Bombay Yacht Club Jetty": (18.9220, 72.8335),
    "Shanmukhananda Chandrasekarendra Saraswathi Auditorium": (19.0347, 72.8611),
    "Shivaji Mandir": (19.0222, 72.8427),
    "Tata Theatre, NCPA": (18.9261, 72.8206),
    "The Baking Lab Studio": (19.0596, 72.8295),
    "The Habitat": (19.0688, 72.8364),
    "The Velvet Trap Basement": (19.0596, 72.8295),
    "Wankhede Stadium": (18.9388, 72.8258),

    # Bengaluru Venues
    "8th Cross Malleswaram": (13.0030, 77.5700),
    "Bangalore International Centre (BIC)": (12.9654, 77.6385),
    "Chowdiah Memorial Hall": (13.0039, 77.5746),
    "Clay Station Studio": (12.9716, 77.6412),
    "Cubbon Park Bandstand": (12.9763, 77.5929),
    "Dharmaraya Swamy Temple, Nagarathpete": (12.9667, 77.5818),
    "Equilibrium Climbing Station": (12.9716, 77.6412),
    "Fandom at Gilly's Defined": (12.9345, 77.6190),
    "Jagriti Theatre": (12.9698, 77.7499),
    "Lalbagh Botanical Garden": (12.9507, 77.5848),
    "Museum of Art & Photography (MAP)": (12.9738, 77.5975),
    "National Gallery of Modern Art (NGMA)": (12.9897, 77.5886),
    "PVR IMAX Forum Mall": (12.9345, 77.6113),
    "Play Arena Sarjapur": (12.8988, 77.6828),
    "Ranga Shankara": (12.9114, 77.5866),
    "Sree Kanteerava Outdoor Stadium": (12.9698, 77.5926),
    "Suchitra Cinema and Cultural Academy": (12.9234, 77.5543),
    "That Comedy Club": (12.9352, 77.6190),
    "The Lalit Ashok Lawn": (12.9961, 77.5815),
    "Third Wave Coffee Roastery": (12.9345, 77.6190),
    "Toit Brewpub / 100 Feet Road": (12.9793, 77.6406),
    "Torq03 Karting Arena": (12.9719, 77.7289),
    "Urvashi Cinema": (12.9555, 77.5870),
    "Varnam Craft Collective": (12.9716, 77.6412),
    "Visvesvaraya Industrial and Technological Museum": (12.9752, 77.5963),
    "Zero Latency Arena": (12.9716, 77.6412),

    # Pune Venues
    "Aga Khan Palace": (18.5524, 73.9015),
    "Bal Gandharva Ranga Mandir": (18.5236, 73.8478),
    "Bhandarkar Oriental Research Institute (BORI)": (18.5180, 73.8315),
    "Cinepolis IMAX Seasons Mall": (18.5196, 73.9318),
    "Classic Rock Coffee Co.": (18.5492, 73.9056),
    "Dr. Gangubai Hangal Music Academy": (18.5167, 73.8415),
    "French Window Patisserie Studio": (18.5362, 73.8940),
    "High Spirits Cafe": (18.5362, 73.8940),
    "Kasba Ganpati & Tambdi Jogeshwari Precinct": (18.5204, 73.8580),
    "Khadakwasla Lake Base": (18.4350, 73.7630),
    "NFAI & City Pride Kothrud": (18.5036, 73.8115),
    "National Film Archive of India (NFAI) Auditorium": (18.5167, 73.8322),
    "Pataleshwar Cave Temple": (18.5284, 73.8504),
    "Pawna Dam Campsite": (18.6672, 73.4905),
    "Prabhat Talkies": (18.5165, 73.8562),
    "Raja Dinkar Kelkar Museum": (18.5108, 73.8542),
    "Rajmachi Wilderness Base": (18.8250, 73.4020),
    "Ramanbaug Ground / Bal Gandharva Ranga Mandir": (18.5236, 73.8478),
    "Sandhan Valley Base": (19.5298, 73.7028),
    "Shaniwar Wada Palace Fort": (18.5196, 73.8553),
    "Shree Shiv Chhatrapati Sports Complex (Balewadi Stadium)": (18.5779, 73.7667),
    "Sinhagad Fort Base": (18.3663, 73.7559),
    "The Comedy Garage Studio": (18.5074, 73.8077),
    "Tower Hill Launch Point": (18.7350, 73.5350),
    "Tribal Museum, TRTI": (18.5280, 73.8785),
    "Tulshibaug & Sadashiv Peth": (18.5147, 73.8530),
    "Yashwantrao Chavan Natyagruha": (18.5036, 73.8115),
}

CITY_FALLBACKS = {
    "Delhi": (28.6139, 77.2090),
    "Mumbai": (18.9600, 72.8200),
    "Bengaluru": (12.9716, 77.5946),
    "Pune": (18.5204, 73.8567),
}


def enrich():
    p = Path("data/seed/experiences.json")
    with open(p, "r", encoding="utf-8") as f:
        items = json.load(f)

    for item in items:
        venue = item.get("venue", "").strip()
        city = item.get("city", "Delhi").strip()
        cat = item.get("category", "").lower()

        # Type: movie or event
        item["type"] = "movie" if cat == "movies" else "event"

        # Coordinates
        if venue in VENUE_COORDINATES:
            lat, lon = VENUE_COORDINATES[venue]
        else:
            # Partial match
            found = False
            for v_key, coords in VENUE_COORDINATES.items():
                if v_key in venue or venue in v_key:
                    lat, lon = coords
                    found = True
                    break
            if not found:
                lat, lon = CITY_FALLBACKS.get(city, (28.6139, 77.2090))

        item["latitude"] = round(float(lat), 6)
        item["longitude"] = round(float(lon), 6)
        item["osm_id"] = f"osm_venue_{item['id']}"

    with open(p, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)

    print(f"Successfully enriched {len(items)} items with coordinates, type, and osm_id.")


if __name__ == "__main__":
    enrich()
