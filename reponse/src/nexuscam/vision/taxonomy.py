from __future__ import annotations

PEOPLE = frozenset({"person", "face", "pedestrian"})
VEHICLES = frozenset(
    {
        "bicycle",
        "motorcycle",
        "motorbike",
        "car",
        "bus",
        "truck",
        "train",
        "airplane",
        "aeroplane",
        "boat",
        "van",
        "scooter",
    }
)
ANIMALS = frozenset(
    {
        "bird",
        "cat",
        "cow",
        "dog",
        "horse",
        "sheep",
        "animal",
        "deer",
        "bear",
        "zebra",
        "giraffe",
        "elephant",
    }
)
OBJECTS = frozenset(
    {
        "bottle",
        "chair",
        "table",
        "diningtable",
        "plant",
        "pottedplant",
        "sofa",
        "screen",
        "tvmonitor",
        "backpack",
        "umbrella",
        "handbag",
        "suitcase",
        "traffic light",
        "stop sign",
        "object",
    }
)

DISPLAY = {
    "motorbike": "motorcycle",
    "aeroplane": "airplane",
    "diningtable": "table",
    "pottedplant": "plant",
    "tvmonitor": "screen",
    "pedestrian": "person",
}


def canonical_label(raw: str) -> str:
    key = raw.strip().lower().replace("_", " ")
    return DISPLAY.get(key.replace(" ", ""), DISPLAY.get(key, key))


def kind_of(label: str) -> str:
    lab = canonical_label(label)
    if lab in PEOPLE:
        return "person"
    if lab in VEHICLES:
        return "vehicle"
    if lab in ANIMALS:
        return "animal"
    return "object"
