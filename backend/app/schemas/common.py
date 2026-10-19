from datetime import datetime, timezone
from typing import Annotated, Any
from pydantic import BeforeValidator, PlainSerializer

def ensure_utc(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, str):
        v = datetime.fromisoformat(v)
    if isinstance(v, datetime):
        if v.tzinfo is None:
            # Treat naive datetime as UTC
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)
    return v

UTCDateTime = Annotated[
    datetime,
    BeforeValidator(ensure_utc),
    PlainSerializer(lambda dt: dt.isoformat(), return_type=str, when_used="json"),
]
