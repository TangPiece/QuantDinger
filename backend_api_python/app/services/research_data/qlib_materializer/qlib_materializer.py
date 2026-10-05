"""DefaultQlibMaterializer：DataQuery Dataset → 本地 Qlib Cache。"""

from __future__ import annotations

import shutil
from datetime import date, datetime, timezone
from pathlib import Path

from app.services.research_data.contracts import DatasetHandle
from app.services.research_data.data_query import DataQuery

from . import cache as cache_mod
from .calendar import calendar_from_market
from .feature_mapper import UnsupportedFeatureError, build_feature_mapping, write_feature_mapping_json
from .identity import MATERIALIZER_VERSION, compute_materialization_id
from .instrument_mapper import build_mapping_rows, to_qlib_instrument, write_instrument_mapping_parquet
from .manifest import build_manifest, detect_qlib_version, write_manifest
from .protocol import MaterializationResult, MaterializationStatus
from .validation import validate_qlib_provider
from .writer_bins import dump_qlib_dataset


class MaterializerError(RuntimeError):
    """物化失败。"""


class DefaultQlibMaterializer:
    """只读 DataQuery 的 Qlib 物化器。

    唯一写目标：本地 qlib-cache/{materialization_id}/。
    """

    def __init__(
        self,
        query: DataQuery,
        *,
        cache_root: Path | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> None:
        self._query = query
        self._cache_root = cache_root
        # 可选覆盖市场窗口；默认从 market 数据实际范围推断
        self._start = start
        self._end = end

    def materialize(
        self,
        dataset_ref: str,
        *,
        force: bool = False,
        skip_qlib_validate: bool = False,
    ) -> MaterializationResult:
        """物化 `code@version`；force 忽略 READY hit。"""
        handle = self._query.dataset(dataset_ref)
        definition = handle.definition
        dataset_hash = handle.dataset_hash
        mid = compute_materialization_id(dataset_hash)
        final = cache_mod.cache_dir_for(mid, root=self._cache_root)
        manifest_path = final / "manifest.json"

        with cache_mod.materialization_lock(mid, root=self._cache_root):
            if not force and cache_mod.is_ready_cache(final):
                mani = cache_mod.read_manifest(final) or {}
                return MaterializationResult(
                    dataset_hash=dataset_hash,
                    materialization_id=mid,
                    cache_path=str(final),
                    manifest_path=str(manifest_path),
                    status=MaterializationStatus.READY,
                    created_at=_parse_created(mani.get("created_at")),
                    row_count=int(mani.get("row_count") or 0),
                    instrument_count=int((mani.get("instruments") or {}).get("count") or 0),
                    calendar_count=int((mani.get("calendar") or {}).get("count") or 0),
                    feature_count=len(mani.get("features") or []),
                    checksum=str(mani.get("checksum") or ""),
                    cache_hit=True,
                    qlib_version=str(mani.get("qlib_version") or ""),
                    materializer_version=MATERIALIZER_VERSION,
                    notes=["cache_hit"],
                )

            # 损坏/旧版本 → 清理后重建
            if final.exists() and not cache_mod.is_ready_cache(final):
                cache_mod.invalidate(final)

            building = cache_mod.building_dir_for(mid, root=self._cache_root)
            if building.exists():
                shutil.rmtree(building, ignore_errors=True)
            building.mkdir(parents=True, exist_ok=True)

            try:
                result = self._build_into(
                    building,
                    handle=handle,
                    materialization_id=mid,
                    skip_qlib_validate=skip_qlib_validate,
                )
                cache_mod.publish_atomic(building, final)
                # publish 后路径变为 final
                result.cache_path = str(final)
                result.manifest_path = str(final / "manifest.json")
                return result
            except Exception:
                # 失败留下 FAILED 痕迹到 building 再清理，避免半成品 final
                shutil.rmtree(building, ignore_errors=True)
                raise

    def _build_into(
        self,
        building: Path,
        *,
        handle: DatasetHandle,
        materialization_id: str,
        skip_qlib_validate: bool,
    ) -> MaterializationResult:
        definition = handle.definition
        dataset_hash = handle.dataset_hash

        # Universe 必须来自 Snapshot，禁止 PG
        knowledge_time = datetime.now(timezone.utc)
        instruments = self._query.universe(
            definition.universe_code,
            knowledge_time,
            snapshot_id=definition.snapshot_id,
            universe_version=definition.universe_version,
        )
        if not instruments:
            raise MaterializerError("universe snapshot returned empty instruments")

        # Feature 映射（不支持则硬失败，禁止漂移）
        try:
            feature_mapping = build_feature_mapping(definition.features)
        except UnsupportedFeatureError:
            raise
        fields = sorted(feature_mapping.keys())
        if not fields:
            # Dataset 未列 features 时默认 OHLCV
            feature_mapping = build_feature_mapping(
                ["open", "high", "low", "close", "volume", "amount"]
            )
            fields = sorted(feature_mapping.keys())

        start = self._start or date(1970, 1, 1)
        end = self._end or date(2100, 1, 1)
        market = self._query.market(
            instruments,
            start,
            end,
            price_policy=definition.price_policy,
        )
        if market.empty:
            raise MaterializerError("DataQuery.market returned empty frame")

        calendar = calendar_from_market(market)
        if not calendar:
            raise MaterializerError("derived calendar is empty")

        mapping_rows = build_mapping_rows(
            instruments,
            valid_from=calendar[0],
            valid_to=calendar[-1],
        )
        meta_dir = building / "metadata"
        write_instrument_mapping_parquet(meta_dir / "instrument_mapping.parquet", mapping_rows)
        write_feature_mapping_json(meta_dir / "feature_mapping.json", feature_mapping)

        stats = dump_qlib_dataset(
            building,
            market,
            instrument_keys=instruments,
            fields=fields,
            calendar=calendar,
            instruments_name="all",
        )

        checksum = cache_mod.directory_checksum(building)
        qlib_ver = detect_qlib_version()
        mani = build_manifest(
            dataset_code=definition.code,
            dataset_version=definition.version,
            dataset_hash=dataset_hash,
            snapshot_id=definition.snapshot_id,
            schema_version=definition.schema_version,
            price_policy=definition.price_policy.model_dump(mode="json"),
            processor=definition.processor,
            materialization_id=materialization_id,
            qlib_version=qlib_ver,
            calendar_min=calendar[0].isoformat(),
            calendar_max=calendar[-1].isoformat(),
            calendar_count=stats["calendar_count"],
            instrument_count=stats["instrument_count"],
            features=fields,
            checksum=checksum,
            status=MaterializationStatus.READY,
            row_count=stats["row_count"],
        )
        write_manifest(building / "manifest.json", mani)

        if not skip_qlib_validate:
            sample = to_qlib_instrument(instruments[0])
            validate_qlib_provider(
                building,
                expect_calendar_count=stats["calendar_count"],
                expect_instrument_count=stats["instrument_count"],
                sample_instrument=sample,
                sample_field=fields[0] if fields else "close",
            )

        return MaterializationResult(
            dataset_hash=dataset_hash,
            materialization_id=materialization_id,
            cache_path=str(building),
            manifest_path=str(building / "manifest.json"),
            status=MaterializationStatus.READY,
            created_at=datetime.now(timezone.utc).replace(microsecond=0),
            row_count=stats["row_count"],
            instrument_count=stats["instrument_count"],
            calendar_count=stats["calendar_count"],
            feature_count=len(fields),
            checksum=checksum,
            cache_hit=False,
            qlib_version=qlib_ver,
            materializer_version=MATERIALIZER_VERSION,
        )


def _parse_created(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc).replace(microsecond=0)
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text)
