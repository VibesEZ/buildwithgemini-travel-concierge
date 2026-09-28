# Seed script for Firestore collection
import json
import os
from google.cloud import firestore
from google.api_core.exceptions import GoogleAPICallError, NotFound

# Hardcoded Project ID string as required for Agent Platform compatibility
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-02-8709896a7d34"

INITIAL_DESTINATIONS = [
    {
        "id": "san-francisco",
        "name": "San Francisco",
        "country": "USA",
        "category": "Coastal City",
        "description": "Iconic bay views, historic cable cars, Golden Gate Bridge, and vibrant food scene.",
        "best_season": "Fall",
        "avg_cost_per_day": 250,
    },
    {
        "id": "kyoto",
        "name": "Kyoto",
        "country": "Japan",
        "category": "Historical & Culture",
        "description": "Classical Buddhist temples, gardens, imperial palaces, Shinto shrines, and traditional wooden houses.",
        "best_season": "Spring",
        "avg_cost_per_day": 180,
    },
    {
        "id": "paris",
        "name": "Paris",
        "country": "France",
        "category": "Cultural & Arts",
        "description": "Global center for art, fashion, gastronomy, and culture with famous landmarks like Eiffel Tower and Louvre.",
        "best_season": "Spring / Autumn",
        "avg_cost_per_day": 220,
    },
    {
        "id": "reykjavik",
        "name": "Reykjavik",
        "country": "Iceland",
        "category": "Nature & Adventure",
        "description": "Gateway to geothermal spas, northern lights, volcanic landscapes, and dramatic waterfalls.",
        "best_season": "Winter / Summer",
        "avg_cost_per_day": 280,
    },
]


def seed_database():
    print(f"Seeding Firestore collection 'destinations' for project '{FIRESTORE_PROJECT_ID}'...")
    try:
        db = firestore.Client(project=FIRESTORE_PROJECT_ID)
        collection_ref = db.collection("destinations")
        for item in INITIAL_DESTINATIONS:
            doc_id = item["id"]
            doc_ref = collection_ref.document(doc_id)
            doc_ref.set(item)
            print(f"  - Added to Firestore: {item['name']} ({doc_id})")
        print("Firestore seeding complete!")
    except (NotFound, GoogleAPICallError, Exception) as e:
        print(f"Firestore not provisioned ({e}). Seeding local JSON fallback...")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        fallback_path = os.path.join(script_dir, "destinations_seed.json")
        with open(fallback_path, "w") as f:
            json.dump(INITIAL_DESTINATIONS, f, indent=2)
        print(f"Local seed written to {fallback_path}!")


if __name__ == "__main__":
    seed_database()
