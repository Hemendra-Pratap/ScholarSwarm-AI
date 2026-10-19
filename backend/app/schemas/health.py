from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Structured response for health checks."""
    status: str
    app_name: str
    version: str
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "app_name": "ScholarSwarm AI",
                "version": "0.1.0",
            }
        }
    )
