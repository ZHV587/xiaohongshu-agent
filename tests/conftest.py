import os

# Fix httpx NO_PROXY parsing bug on Windows when ::1 is present
if "NO_PROXY" in os.environ:
    os.environ["NO_PROXY"] = ",".join(
        item for item in os.environ["NO_PROXY"].split(",")
        if ":" not in item
    )
