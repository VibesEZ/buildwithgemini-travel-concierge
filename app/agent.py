# ruff: noqa
# Copyright 2026 Google LLC

import base64
import datetime
import json
import os
import re
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from dotenv import load_dotenv
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.api_core.exceptions import GoogleAPICallError, NotFound
from google.cloud import firestore, storage
from google.genai import types

from app.a2ui_utils import a2ui_callback

# Load environment variables from .env file
load_dotenv()

# Hardcoded Project ID string as required for Agent Platform compatibility
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-02-8709896a7d34"

# Hardcoded Cloud Storage Bucket name as required
GCS_BUCKET_NAME = "travel-concierge-media-qwiklabs-gcp-02-8709896a7d34"


def _get_firestore_client():
    """Initializes and returns the Firestore client with hardcoded project ID."""
    return firestore.Client(project=FIRESTORE_PROJECT_ID)


def _get_code_executor():
    """Reads the Agent Engine resource name from deployment_metadata.json and initializes AgentEngineSandboxCodeExecutor."""
    metadata_path = os.path.join(
        os.path.dirname(__file__), "..", "deployment_metadata.json"
    )
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r") as f:
                meta = json.load(f)
            runtime_id = meta.get("remote_agent_runtime_id")
            if not runtime_id or runtime_id == "None":
                pending = meta.get("pending_operation", {})
                op_name = pending.get("operation_name", "")
                if "/operations/" in op_name:
                    runtime_id = op_name.split("/operations/")[0]
            if runtime_id and runtime_id != "None":
                return AgentEngineSandboxCodeExecutor(
                    agent_engine_resource_name=runtime_id
                )
        except Exception as e:
            print(f"Warning: Could not initialize AgentEngineSandboxCodeExecutor: {e}")
    return None


code_executor = _get_code_executor()


async def generate_memories_callback(callback_context: CallbackContext):
    """WRITE: after each turn, send the session events to Memory Bank for long-term extraction."""
    await callback_context.add_session_to_memory()
    return None


def list_destinations(category: str = "") -> str:
    """Lists available travel destinations stored in the Firestore database.

    Args:
        category: Optional filter string to search by category (e.g. 'Coastal City', 'Historical & Culture').

    Returns:
        JSON string list of matching destination items.
    """
    try:
        db = _get_firestore_client()
        docs = db.collection("destinations").stream()
        results = [doc.to_dict() for doc in docs]
        if not results:
            results = []
    except (NotFound, GoogleAPICallError, Exception):
        fallback_path = os.path.join(
            os.path.dirname(__file__), "..", "destinations_seed.json"
        )
        if os.path.exists(fallback_path):
            with open(fallback_path, "r") as f:
                results = json.load(f)
        else:
            results = []

    if category:
        results = [
            r for r in results if category.lower() in r.get("category", "").lower()
        ]

    return json.dumps(results, indent=2)


def get_destination_details(destination_id: str) -> str:
    """Gets detailed information about a specific travel destination.

    Args:
        destination_id: The ID or slug of the destination (e.g., 'san-francisco', 'kyoto').

    Returns:
        JSON string with details of the destination or an error message if not found.
    """
    clean_id = destination_id.strip().lower().replace(" ", "-")
    try:
        db = _get_firestore_client()
        doc = db.collection("destinations").document(clean_id).get()
        if doc.exists:
            return json.dumps(doc.to_dict(), indent=2)
    except (NotFound, GoogleAPICallError, Exception):
        pass

    fallback_path = os.path.join(
        os.path.dirname(__file__), "..", "destinations_seed.json"
    )
    if os.path.exists(fallback_path):
        with open(fallback_path, "r") as f:
            items = json.load(f)
            for item in items:
                if (
                    item.get("id") == clean_id
                    or clean_id in item.get("name", "").lower()
                ):
                    return json.dumps(item, indent=2)

    return f"Destination '{destination_id}' not found in the database."


def add_destination(
    name: str,
    country: str,
    category: str,
    description: str,
    best_season: str,
    avg_cost_per_day: int,
) -> str:
    """Adds a new travel destination to the Firestore database catalog.

    Args:
        name: Name of the destination (e.g., 'Barcelona').
        country: Country where the destination is located (e.g., 'Spain').
        category: Category of the trip (e.g., 'Coastal City', 'Culinary').
        description: A rich description of what makes this destination special.
        best_season: Ideal season to visit (e.g., 'Spring').
        avg_cost_per_day: Estimated average cost per day in USD.

    Returns:
        A confirmation message with the generated destination ID.
    """
    doc_id = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    item = {
        "id": doc_id,
        "name": name,
        "country": country,
        "category": category,
        "description": description,
        "best_season": best_season,
        "avg_cost_per_day": avg_cost_per_day,
    }

    try:
        db = _get_firestore_client()
        db.collection("destinations").document(doc_id).set(item)
        storage_type = "Firestore database"
    except (NotFound, GoogleAPICallError, Exception):
        fallback_path = os.path.join(
            os.path.dirname(__file__), "..", "destinations_seed.json"
        )
        items = []
        if os.path.exists(fallback_path):
            with open(fallback_path, "r") as f:
                items = json.load(f)
        items.append(item)
        with open(fallback_path, "w") as f:
            json.dump(items, f, indent=2)
        storage_type = "local catalog"

    return f"Successfully added destination '{name}' (ID: {doc_id}) to {storage_type}."


def calculate_trip_budget(
    destination_id: str,
    days: int = 3,
    num_travelers: int = 1,
    buffer_percent: float = 10.0,
) -> str:
    """Calculates an estimated total travel budget for a destination.

    Args:
        destination_id: The destination ID or slug (e.g., 'san-francisco', 'kyoto').
        days: Number of days for the trip (default: 3).
        num_travelers: Number of travelers in the party (default: 1).
        buffer_percent: Percentage buffer for unexpected expenses (default: 10.0).

    Returns:
        JSON string breakdown of estimated costs and total budget.
    """
    clean_id = destination_id.strip().lower().replace(" ", "-")
    avg_cost = 200
    dest_name = destination_id

    try:
        db = _get_firestore_client()
        doc = db.collection("destinations").document(clean_id).get()
        if doc.exists:
            data = doc.to_dict()
            avg_cost = data.get("avg_cost_per_day", 200)
            dest_name = data.get("name", destination_id)
    except (NotFound, GoogleAPICallError, Exception):
        fallback_path = os.path.join(
            os.path.dirname(__file__), "..", "destinations_seed.json"
        )
        if os.path.exists(fallback_path):
            with open(fallback_path, "r") as f:
                for item in json.load(f):
                    if (
                        item.get("id") == clean_id
                        or clean_id in item.get("name", "").lower()
                    ):
                        avg_cost = item.get("avg_cost_per_day", 200)
                        dest_name = item.get("name", destination_id)
                        break

    base_total = avg_cost * days * num_travelers
    buffer_amount = round(base_total * (buffer_percent / 100.0), 2)
    grand_total = round(base_total + buffer_amount, 2)

    result = {
        "destination": dest_name,
        "days": days,
        "num_travelers": num_travelers,
        "avg_cost_per_person_per_day": avg_cost,
        "base_total": base_total,
        "contingency_buffer": buffer_amount,
        "grand_total": grand_total,
    }
    return json.dumps(result, indent=2)


def generate_destination_image(
    prompt: str,
    tool_context: ToolContext = None,
) -> str:
    """Generates a promotional travel image for a destination using gemini-3.1-flash-lite-image model.

    Saves the generated image as a Playground artifact and uploads it to Cloud Storage.

    Args:
        prompt: Description or destination name for the image to generate (e.g. 'Kyoto cherry blossoms at dusk').
        tool_context: Context provided by the agent framework for saving artifacts.

    Returns:
        The public HTTPS URL of the generated image stored in Cloud Storage.
    """
    clean_id = (
        re.sub(r"[^a-z0-9]+", "-", prompt.strip().lower()).strip("-")[:40]
        or "destination"
    )
    filename = f"{clean_id}.jpg"

    # Generate image using gemini-3.1-flash-lite-image in global region
    client = genai.Client(
        vertexai=True, project=FIRESTORE_PROJECT_ID, location="global"
    )
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=f"Generate a vibrant, high-quality promotional travel photo for: {prompt}",
    )

    image_bytes = None
    mime_type = "image/jpeg"
    if (
        response.candidates
        and response.candidates[0].content
        and response.candidates[0].content.parts
    ):
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.data:
                image_bytes = part.inline_data.data
                if part.inline_data.mime_type:
                    mime_type = part.inline_data.mime_type
                break

    if not image_bytes:
        return f"Error: Failed to generate image for prompt '{prompt}'."

    # (1) Save artifact for Playground Artifacts panel
    if tool_context is not None:
        try:
            artifact_part = types.Part.from_bytes(
                data=image_bytes, mime_type=mime_type
            )
            tool_context.save_artifact(filename, artifact_part)
        except Exception as e:
            print(f"Warning: Failed to save artifact: {e}")

    # (2) Upload image bytes directly to public Cloud Storage bucket
    try:
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        object_name = f"destinations/{filename}"
        blob = bucket.blob(object_name)
        blob.upload_from_string(image_bytes, content_type=mime_type)
        public_url = (
            f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{object_name}"
        )
        return public_url
    except Exception as e:
        return f"Error uploading image to Cloud Storage: {str(e)}"


def generate_destination_video(
    prompt: str,
    tool_context: ToolContext = None,
) -> str:
    """Generates a short promotional travel video clip for a destination using Google's Omni model (gemini-omni-flash-preview).

    Saves the generated video as a Playground artifact and uploads it to Cloud Storage.

    Args:
        prompt: Description or destination name for the video to generate (e.g. 'Kyoto cherry blossoms at sunset').
        tool_context: Context provided by the agent framework for saving artifacts.

    Returns:
        The public HTTPS URL of the generated video stored in Cloud Storage.
    """
    clean_id = (
        re.sub(r"[^a-z0-9]+", "-", prompt.strip().lower()).strip("-")[:40]
        or "destination-video"
    )
    filename = f"{clean_id}.mp4"

    client = genai.Client(
        vertexai=True, project=FIRESTORE_PROJECT_ID, location="global"
    )

    video_bytes = None
    mime_type = "video/mp4"

    try:
        response = client.interactions.create(
            model="gemini-omni-flash-preview",
            input=f"Generate a short promotional travel video clip for: {prompt}",
        )

        if hasattr(response, "output_video") and response.output_video:
            if response.output_video.mime_type:
                mime_type = response.output_video.mime_type
            if response.output_video.data:
                data_val = response.output_video.data
                if isinstance(data_val, str):
                    video_bytes = base64.b64decode(data_val)
                elif isinstance(data_val, bytes):
                    video_bytes = data_val
            elif response.output_video.uri:
                with urllib.request.urlopen(response.output_video.uri) as resp:
                    video_bytes = resp.read()

        if not video_bytes and hasattr(response, "steps") and response.steps:
            for step in response.steps:
                content_list = getattr(step, "content", []) or []
                for item in content_list:
                    item_type = getattr(item, "type", None)
                    if item_type == "video":
                        if getattr(item, "mime_type", None):
                            mime_type = item.mime_type
                        d = getattr(item, "data", None)
                        if d:
                            if isinstance(d, str):
                                video_bytes = base64.b64decode(d)
                            elif isinstance(d, bytes):
                                video_bytes = d
                            break
                        uri = getattr(item, "uri", None)
                        if uri:
                            with urllib.request.urlopen(uri) as resp:
                                video_bytes = resp.read()
                            break
                if video_bytes:
                    break
    except Exception as e:
        return f"Error generating video with gemini-omni-flash-preview: {str(e)}"

    if not video_bytes:
        return f"Error: Failed to generate video for prompt '{prompt}'."

    # (1) Save artifact for Playground Artifacts panel
    if tool_context is not None:
        try:
            artifact_part = types.Part.from_bytes(
                data=video_bytes, mime_type=mime_type
            )
            tool_context.save_artifact(filename, artifact_part)
        except Exception as e:
            print(f"Warning: Failed to save video artifact: {e}")

    # (2) Upload video bytes directly to public Cloud Storage bucket
    try:
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        object_name = f"videos/{filename}"
        blob = bucket.blob(object_name)
        blob.upload_from_string(video_bytes, content_type=mime_type)
        public_url = (
            f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{object_name}"
        )
        return public_url
    except Exception as e:
        return f"Error uploading video to Cloud Storage: {str(e)}"


def convert_currency(
    amount: float,
    from_currency: str = "USD",
    to_currency: str = "EUR",
) -> str:
    """Converts a monetary amount between currencies using live foreign exchange rates.

    Args:
        amount: The numerical monetary amount to convert (e.g., 100.0).
        from_currency: The 3-letter currency code to convert from (e.g., 'USD', 'EUR').
        to_currency: The 3-letter currency code to convert to (e.g., 'EUR', 'JPY', 'GBP').

    Returns:
        JSON string containing exchange rate and converted amount details.
    """
    base_curr = from_currency.strip().upper()
    target_curr = to_currency.strip().upper()

    url = f"https://api.frankfurter.app/latest?amount={amount}&from={base_curr}&to={target_curr}"

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "TravelConcierge/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            converted = data.get("rates", {}).get(target_curr)
            result = {
                "original_amount": amount,
                "from_currency": base_curr,
                "to_currency": target_curr,
                "converted_amount": converted,
                "rate_date": data.get("date"),
            }
            return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error fetching exchange rate from {base_curr} to {target_curr}: {str(e)}"


def geocode_address(address: str) -> str:
    """Geocodes an address string into latitude and longitude coordinates using Google Maps Geocoding API.

    Args:
        address: The street address or city name to geocode (e.g. '1600 Amphitheatre Pkwy, Mountain View, CA').

    Returns:
        JSON string containing the formatted address and location coordinates (latitude, longitude).
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not api_key or api_key == "PASTE_KEY_HERE":
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not configured with a valid key."

    encoded_address = urllib.parse.quote(address)
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={api_key}"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("status") != "OK" or not data.get("results"):
                return f"Geocoding failed for address '{address}': {data.get('status', 'NO_RESULTS')}"

            result = data["results"][0]
            loc = result["geometry"]["location"]
            formatted = {
                "address": result.get("formatted_address"),
                "location": {
                    "latitude": loc.get("lat"),
                    "longitude": loc.get("lng"),
                },
            }
            return json.dumps(formatted, indent=2)
    except Exception as e:
        return f"Error calling Geocoding API: {str(e)}"


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "tourist_attraction",
    radius: float = 5000.0,
) -> str:
    """Finds nearby places of a specific type around coordinates using Places API (New).

    Args:
        latitude: Latitude of the center location.
        longitude: Longitude of the center location.
        place_type: Type of place to search for (e.g., 'tourist_attraction', 'restaurant', 'museum', 'hotel').
        radius: Search radius in meters (default: 5000.0).

    Returns:
        JSON string list of nearby places with name, address, and location.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not api_key or api_key == "PASTE_KEY_HERE":
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not configured with a valid key."

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.primaryType",
    }
    payload = {
        "includedTypes": [place_type],
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude,
                },
                "radius": radius,
            }
        },
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            places = data.get("places", [])
            results = []
            for p in places:
                display_name = p.get("displayName", {}).get("text", "")
                formatted_address = p.get("formattedAddress", "")
                location = p.get("location", {})
                results.append({
                    "name": display_name,
                    "address": formatted_address,
                    "location": location,
                })
            return json.dumps(results, indent=2)
    except Exception as e:
        return f"Error calling Places API (New): {str(e)}"


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        query: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return (
        f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"
    )


# Build A2UI System Prompt using A2uiSchemaManager version 0.8 and BasicCatalog
schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are Travel Concierge, a helpful AI assistant designed to help users discover "
        "and manage travel destinations. You pay close attention to and remember all user allergies, "
        "dietary restrictions, personal preferences, and health facts from previous conversations. "
        "Always tailor travel, dining, and destination recommendations to accommodate the user's allergies and preferences."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    code_executor=code_executor,
    instruction=instruction,
    tools=[
        PreloadMemoryTool(),
        list_destinations,
        get_destination_details,
        add_destination,
        calculate_trip_budget,
        generate_destination_image,
        generate_destination_video,
        convert_currency,
        geocode_address,
        find_nearby_places,
        get_weather,
        get_current_time,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
