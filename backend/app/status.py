"""Aggregation of stored check results into the `GET /api/families` response."""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app import db
from app.config import Settings

Availability = Literal["yes", "no", "unknown"]


class ApiModel(BaseModel):
    """Base for response models: snake_case in Python, camelCase in JSON."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AvailabilityPoint(ApiModel):
    datetime: str
    available: Availability


class ModelHistory(ApiModel):
    availability_points: list[AvailabilityPoint]


class ModelStatus(ApiModel):
    modelname: str
    provider: str
    company: str
    status: Availability
    last_checked: str | None
    latency_ms: int | None
    error: str | None


class FamilyStatus(ApiModel):
    title: str
    status: Availability
    history: ModelHistory
    models: list[ModelStatus]


def _availability(success: bool) -> Availability:
    return "yes" if success else "no"


def get_families(settings: Settings) -> list[FamilyStatus]:
    """Build the status of every configured family, in configuration order.

    A round counts as `yes` only if every model of the family succeeded in it. Families and
    models without any stored result are reported as `unknown`.
    """
    families = []
    for family in settings.model_families:
        names = [model.modelname for model in family.models]
        latest = db.latest_results(settings.database_path, family.title, names)
        rounds = db.recent_rounds(settings.database_path, family.title, names, settings.history_limit)
        points = [AvailabilityPoint(datetime=at, available=_availability(ok)) for at, ok in rounds]
        models = []
        for model in family.models:
            result = latest.get(model.modelname)
            models.append(
                ModelStatus(
                    modelname=model.modelname,
                    provider=model.provider,
                    company=model.company,
                    status=_availability(result.success) if result else "unknown",
                    last_checked=result.round_at if result else None,
                    latency_ms=result.latency_ms if result else None,
                    error=result.error if result else None,
                )
            )
        families.append(
            FamilyStatus(
                title=family.title,
                status=points[-1].available if points else "unknown",
                history=ModelHistory(availability_points=points),
                models=models,
            )
        )
    return families
