"""Experiment create spec (UI → domain)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExperimentCreateSpec(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    name: str
    dataset_ref: str = Field(alias="datasetRef")
    model_version_ref: str | None = Field(default=None, alias="modelVersionRef")
    feature_refs: list[str] = Field(default_factory=list, alias="featureRefs")
    processor_ref: str | None = Field(default=None, alias="processorRef")
    parameters: dict[str, Any] = Field(default_factory=dict)


__all__ = ["ExperimentCreateSpec"]
