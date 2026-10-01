"""Aggregation of stored check results into the `GET /api/families` response."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app import db, slots
from app.config import Settings

Availability = Literal["yes", "no", "partial", "unknown"]


class ApiModel(BaseModel):
    """Base for response models: snake_case in Python, camelCase in JSON."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AvailabilityPoint(ApiModel):
    datetime: str
    available: Availability


class ModelAvailabilityPoint(AvailabilityPoint):
    """A model's own history point, additionally carrying that round's latency/error."""

    latency_ms: int | None = None
    error: str | None = None


class FamilyHistory(ApiModel):
    availability_points: list[AvailabilityPoint]


class ModelHistory(ApiModel):
    availability_points: list[ModelAvailabilityPoint]


class ModelStatus(ApiModel):
    modelname: str
    provider: str
    company: str
    status: Availability
    last_checked: str | None
    latency_ms: int | None
    error: str | None
    history: ModelHistory


class FamilyStatus(ApiModel):
    title: str
    status: Availability
    history: FamilyHistory
    models: list[ModelStatus]


def _model_availability(success: bool) -> Availability:
    return "yes" if success else "no"


def _family_availability(succeeded: int, total: int) -> Availability:
    if total == 0:
        return "unknown"
    if succeeded == total:
        return "yes"
    if succeeded == 0:
        return "no"
    return "partial"


def _latest_round_availability(latest: list[db.CheckResult]) -> Availability:
    """The family availability of the newest round among the models' latest results."""
    if not latest:
        return "unknown"
    newest = max(latest, key=lambda r: (r.round_at, r.round_id)).round_id
    in_round = [r for r in latest if r.round_id == newest]
    return _family_availability(sum(r.success for r in in_round), len(in_round))


def get_families(settings: Settings, now: datetime | None = None) -> list[FamilyStatus]:
    """Build the status of every family of the active model list, in stored order.

    Histories use the shared slot grid (see `app.slots`): a slot is `yes` if every model of the
    family that was checked in it succeeded, `no` if every one failed, `partial` if mixed and
    `unknown` if none was checked. Families and models without any stored result are `unknown`.
    """
    count = max(settings.history_limit, settings.model_history_limit)
    grid = slots.grid(settings.check_interval_seconds, count, now)
    family_offset = count - settings.history_limit
    model_offset = count - settings.model_history_limit
    families = []
    for family in db.active_models(settings.database_path):
        names = [model.modelname for model in family.models]
        latest = db.latest_results(settings.database_path, family.title, names)
        checks = db.checks_since(settings.database_path, family.title, names, grid[0].start) if grid else []
        buckets = slots.latest_per_slot(grid, checks)
        points = [
            AvailabilityPoint(
                datetime=slot.end,
                available=_family_availability(sum(r.success for r in bucket.values()), len(bucket)),
            )
            for slot, bucket in zip(grid[family_offset:], buckets[family_offset:])
        ]
        models = []
        for model in family.models:
            result = latest.get(model.modelname)
            model_points = [
                ModelAvailabilityPoint(
                    datetime=slot.end,
                    available=_model_availability(check.success) if check else "unknown",
                    latency_ms=check.latency_ms if check else None,
                    error=check.error if check else None,
                )
                for slot, bucket in zip(grid[model_offset:], buckets[model_offset:])
                for check in [bucket.get(model.modelname)]
            ]
            models.append(
                ModelStatus(
                    modelname=model.modelname,
                    provider=model.provider,
                    company=model.company,
                    status=_model_availability(result.success) if result else "unknown",
                    last_checked=result.round_at if result else None,
                    latency_ms=result.latency_ms if result else None,
                    error=result.error if result else None,
                    history=ModelHistory(availability_points=model_points),
                )
            )
        families.append(
            FamilyStatus(
                title=family.title,
                status=_latest_round_availability(list(latest.values())),
                history=FamilyHistory(availability_points=points),
                models=models,
            )
        )
    return families
