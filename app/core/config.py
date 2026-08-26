import base64
import binascii
import json
from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_cors_origins(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return value
    stripped = value.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            return parsed
        raise ValueError("BACKEND_CORS_ORIGINS JSON value must be a list")
    return [origin.strip() for origin in stripped.split(",") if origin.strip()]


def _blank_to_none(value: str | float | int | None) -> str | float | int | None:
    if isinstance(value, str) and not value.strip():
        return None
    return value


LOCAL_ENVIRONMENTS = {"local", "dev", "development", "test", "testing"}
DEFAULT_JWT_SECRET = "change-me-local-development-secret-at-least-32-bytes"

CorsOrigins = Annotated[list[str], BeforeValidator(_parse_cors_origins)]
OptionalFloat = Annotated[float | None, BeforeValidator(_blank_to_none)]
OptionalInt = Annotated[int | None, BeforeValidator(_blank_to_none)]
OptionalSecret = Annotated[SecretStr | None, BeforeValidator(_blank_to_none)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "mobility-adtech-api"
    environment: str = "local"
    api_v1_prefix: str = "/api/v1"
    database_url: str | None = None
    redis_url: str | None = None
    sentry_dsn: str = ""
    login_rate_limit_ip_max_failures: int = 150
    login_rate_limit_ip_window_seconds: int = 300
    login_rate_limit_account_max_failures: int = 5
    login_rate_limit_account_window_seconds: int = 900
    login_rate_limit_global_max_failures: int = 250
    login_rate_limit_global_window_seconds: int = 300
    login_rate_limit_trust_client_ip_header: bool = False
    login_rate_limit_trusted_proxy_cidrs: str = ""
    # W3-04A is a cohort-gated public surface.  Registration keeps separate
    # buckets from login so a public applicant can never consume or refund a
    # credential-guessing allowance.
    driver_registration_enabled: bool = False
    driver_registration_rate_limit_ip_max_attempts: int = 10
    driver_registration_rate_limit_ip_window_seconds: int = 3600
    driver_registration_rate_limit_email_max_attempts: int = 3
    driver_registration_rate_limit_email_window_seconds: int = 3600
    driver_registration_rate_limit_global_max_attempts: int = 100
    driver_registration_rate_limit_global_window_seconds: int = 3600
    driver_registration_rate_limit_trust_client_ip_header: bool = False
    driver_registration_rate_limit_trusted_proxy_cidrs: str = ""
    backend_cors_origins: CorsOrigins = Field(default_factory=list)
    log_level: str = "INFO"
    request_id_header: str = "X-Request-ID"
    jwt_secret_key: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    session_absolute_lifetime_minutes: int = 720
    password_min_length: int = 12
    default_currency: str = "NGN"
    invoice_issuer_external_input_reference: str = ""
    payout_crypto_keyring_b64: SecretStr
    payout_crypto_key_version: int = 1
    object_storage_endpoint_url: str = ""
    object_storage_public_endpoint_url: str = ""
    object_storage_region: str = "us-east-1"
    object_storage_bucket: str = ""
    object_storage_access_key_id: SecretStr | None = None
    object_storage_secret_access_key: SecretStr | None = None
    object_storage_presign_ttl_seconds: int = 300
    object_storage_orphan_ttl_hours: int = 24
    object_storage_download_ttl_seconds: int = 60
    # No legal retention period is assumed. Execution remains disabled until
    # an approved value is configured by the deployment environment.
    file_kyc_retention_days: OptionalInt = None
    # Q15/Q17 implementation inputs were requested but not supplied. These
    # remain empty in production until Terrax selects uploader roles, required
    # views and renewal windows; the evidence/proof services fail closed.
    installation_evidence_uploader_roles: str = ""
    installation_evidence_required_views: str = ""
    installation_evidence_validity_hours: OptionalInt = None
    display_proof_challenge_ttl_seconds: OptionalInt = None
    display_proof_validity_seconds: OptionalInt = None
    # Q17 policy values remain deployment inputs. Recurring proof work is
    # disabled until all three are explicitly configured.
    evidence_high_earner_threshold_ngn: str | float | int | None = None
    evidence_renewal_lookback_days: OptionalInt = None
    evidence_challenge_response_hours: OptionalInt = None
    # Production provider and verified sender identity are external inputs.
    # Empty values keep provider dispatch and receipt handling fail closed.
    email_provider: str = ""
    email_sender_address: str = ""
    email_sender_name: str = "Cardvert"
    email_smtp_host: str = ""
    email_smtp_port: int = 1025
    email_smtp_username: str = ""
    email_smtp_password: OptionalSecret = None
    email_smtp_starttls: bool = False
    email_receipt_signing_secret: OptionalSecret = None
    email_receipt_key_id: str = ""
    email_delivery_max_attempts: int = 5
    email_delivery_retry_base_seconds: int = 60
    email_delivery_claim_seconds: int = 120
    malware_scanner_host: str = ""
    malware_scanner_port: int = 3310
    malware_scanner_timeout_seconds: int = 30
    max_campaign_zone_area_sq_km: int = 5000
    max_location_pings_per_batch: int = 500
    location_ping_future_skew_seconds: int = 300
    location_ping_start_skew_seconds: int = 900
    max_location_accuracy_m: int = 10000
    max_location_speed_mps: int = 120
    route_analytics_formula_version: str = "route_analytics_v1"
    route_analytics_min_valid_pings: int = 2
    route_analytics_moving_speed_mps: float = 1.0
    route_analytics_stationary_speed_mps: float = 0.5
    route_analytics_impossible_speed_mps: float = 55.0
    route_analytics_max_ping_gap_seconds: int = 900
    route_analytics_poor_accuracy_threshold_m: float = 100.0
    route_analytics_poor_accuracy_ratio_threshold: float = 0.5
    route_analytics_stationary_ratio_threshold: float = 0.8
    route_analytics_looping_radius_m: float = 50.0
    route_analytics_looping_min_distance_m: float = 1000.0
    route_replay_detector_version: str = "route_replay_v1"
    route_replay_coordinate_precision: int = 5
    route_replay_time_tolerance_seconds: int = 5
    route_replay_min_valid_pings: int = 10
    route_replay_min_distance_m: float = 250.0
    route_replay_max_evidence_matches: int = 10
    fraud_assessment_formula_version: str = "fraud_assessment_v1"
    impression_formula_version: str = "impressions_v1"
    impression_default_traffic_density_per_km: float = 120.0
    impression_default_dwell_impressions_per_minute: float = 3.0
    impression_high_fraud_multiplier: float = 0.25
    impression_medium_fraud_multiplier: float = 0.70
    impression_low_fraud_multiplier: float = 0.90
    impression_insufficient_data_confidence: float = 0.10
    impression_min_confidence: float = 0.0
    impression_max_confidence: float = 1.0
    payout_formula_version: str = "payout_v1"
    payout_eligibility_stationary_radius_m: int = 200
    payout_eligibility_stationary_window_min: int = 5
    payout_eligibility_stationary_grace_min: int = 4
    payout_eligibility_max_accuracy_m: int = 75
    payout_eligibility_teleport_kmh: int = 180
    payout_eligibility_max_ping_gap_seconds: int = 120
    payout_default_hourly_rate_ngn: float = 0.0
    payout_default_base_rate_per_km: float = 0.0
    payout_default_base_rate_per_active_hour: float = 0.0
    payout_default_target_zone_bonus_rate_per_km: float = 0.0
    payout_default_bonus_zone_bonus_rate_per_km: float = 0.0
    payout_default_estimated_impression_rate_per_1000: float = 0.0
    payout_default_low_fraud_multiplier: float = 0.90
    payout_default_medium_fraud_multiplier: float = 0.70
    payout_default_high_fraud_multiplier: float = 0.25
    payout_default_min_payout_per_trip: float = 0.0
    payout_default_max_payout_per_trip: OptionalFloat = None
    heatmap_default_resolution_m: int = 500
    heatmap_min_resolution_m: int = 50
    heatmap_max_resolution_m: int = 5000
    heatmap_max_bbox_area_sq_km: int = 2500
    heatmap_max_date_range_days: int = 90
    heatmap_max_cells: int = 5000
    heatmap_min_trips_per_cell: int = 1
    privacy_disclosure_live_authorized: bool = False
    privacy_disclosure_synthetic_test_mode: bool = False
    privacy_legal_approval_reference: str = ""
    privacy_disclosure_config_reference: str = ""
    privacy_query_history_retention_reference: str = ""
    privacy_query_history_retention_days: int = 30
    privacy_min_vehicles_per_cell: int = 3
    privacy_min_trips_per_cell: int = 5
    privacy_min_days_per_cell: int = 2
    privacy_max_contributor_share: float = 0.5
    privacy_min_resolution_m: int = 500
    allow_demo_seed: bool = False
    # RM3 seal protocol: recovery window after an incomplete/legacy trip end
    # before the sweep force-seals; and how far past ended_at a late ping's
    # recorded_at may fall (matches location_ping_future_skew tolerance).
    trip_seal_grace_seconds: int = 600
    location_ping_end_skew_seconds: int = 300
    worker_sweep_interval_minutes: int = 5
    worker_sweep_batch_size: int = 25
    # Q20 deliberately has no invented production default. Keep the raw
    # value so an absent, malformed, non-finite, or non-positive setting can
    # fail closed at the activity worker boundary with observable evidence.
    verified_hours_floor_per_week: str | float | int | None = None
    fraud_review_sla_days: int = 7
    ping_retention_months: int = 12
    partition_premake_months: int = 4

    @field_validator("api_v1_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("API_V1_PREFIX must start with /")
        return value.rstrip("/") or "/"

    @field_validator("backend_cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: list[str], info) -> list[str]:
        environment = str(info.data.get("environment", "local")).lower()
        if environment not in LOCAL_ENVIRONMENTS and "*" in value:
            raise ValueError("Wildcard CORS origins are not allowed outside local/test")
        return value

    @field_validator("access_token_expire_minutes", "session_absolute_lifetime_minutes")
    @classmethod
    def validate_access_token_expire_minutes(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be positive")
        return value

    @field_validator(
        "login_rate_limit_ip_max_failures",
        "login_rate_limit_ip_window_seconds",
        "login_rate_limit_account_max_failures",
        "login_rate_limit_account_window_seconds",
        "login_rate_limit_global_max_failures",
        "login_rate_limit_global_window_seconds",
        "driver_registration_rate_limit_ip_max_attempts",
        "driver_registration_rate_limit_ip_window_seconds",
        "driver_registration_rate_limit_email_max_attempts",
        "driver_registration_rate_limit_email_window_seconds",
        "driver_registration_rate_limit_global_max_attempts",
        "driver_registration_rate_limit_global_window_seconds",
    )
    @classmethod
    def validate_positive_rate_limit_settings(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Login rate-limit settings must be positive")
        return value

    @field_validator("password_min_length")
    @classmethod
    def validate_password_min_length(cls, value: int) -> int:
        if value < 12:
            raise ValueError("PASSWORD_MIN_LENGTH must be at least 12")
        return value

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret_key(cls, value: str, info) -> str:
        environment = str(info.data.get("environment", "local")).lower()
        if environment not in LOCAL_ENVIRONMENTS and value == DEFAULT_JWT_SECRET:
            raise ValueError("JWT_SECRET_KEY must be changed outside local/test")
        if not value.strip() or len(value) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters long")
        return value

    @field_validator("max_campaign_zone_area_sq_km")
    @classmethod
    def validate_max_campaign_zone_area_sq_km(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("MAX_CAMPAIGN_ZONE_AREA_SQ_KM must be positive")
        return value

    @field_validator(
        "object_storage_presign_ttl_seconds",
        "object_storage_orphan_ttl_hours",
        "object_storage_download_ttl_seconds",
        "malware_scanner_port",
        "malware_scanner_timeout_seconds",
    )
    @classmethod
    def validate_positive_file_boundary_settings(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("File-boundary numeric settings must be positive")
        return value

    @field_validator("file_kyc_retention_days")
    @classmethod
    def validate_file_kyc_retention_days(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("FILE_KYC_RETENTION_DAYS must be positive when configured")
        return value

    @field_validator(
        "installation_evidence_validity_hours",
        "display_proof_challenge_ttl_seconds",
        "display_proof_validity_seconds",
        "evidence_renewal_lookback_days",
        "evidence_challenge_response_hours",
    )
    @classmethod
    def validate_optional_evidence_windows(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("Installation evidence windows must be positive when configured")
        return value

    @field_validator("installation_evidence_uploader_roles")
    @classmethod
    def validate_installation_evidence_uploader_roles(cls, value: str) -> str:
        roles = [part.strip().lower() for part in value.split(",") if part.strip()]
        if len(roles) != len(set(roles)) or not set(roles) <= {"driver", "admin"}:
            raise ValueError(
                "INSTALLATION_EVIDENCE_UPLOADER_ROLES must contain unique driver/admin values"
            )
        return ",".join(roles)

    @field_validator("installation_evidence_required_views")
    @classmethod
    def validate_installation_evidence_required_views(cls, value: str) -> str:
        views = [part.strip().lower() for part in value.split(",") if part.strip()]
        if len(views) != len(set(views)) or any(
            len(view) > 64
            or not view
            or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for character in view)
            for view in views
        ):
            raise ValueError(
                "INSTALLATION_EVIDENCE_REQUIRED_VIEWS must contain unique safe view codes"
            )
        return ",".join(views)

    @field_validator(
        "max_location_pings_per_batch",
        "location_ping_future_skew_seconds",
        "location_ping_start_skew_seconds",
        "location_ping_end_skew_seconds",
        "trip_seal_grace_seconds",
        "max_location_accuracy_m",
        "max_location_speed_mps",
    )
    @classmethod
    def validate_positive_tracking_settings(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Location tracking settings must be positive")
        return value

    @field_validator(
        "route_analytics_min_valid_pings",
        "route_analytics_max_ping_gap_seconds",
        "route_replay_time_tolerance_seconds",
        "route_replay_min_valid_pings",
        "route_replay_max_evidence_matches",
    )
    @classmethod
    def validate_positive_route_analytics_ints(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Route analytics integer settings must be positive")
        return value

    @field_validator(
        "route_analytics_moving_speed_mps",
        "route_analytics_stationary_speed_mps",
        "route_analytics_impossible_speed_mps",
        "route_analytics_poor_accuracy_threshold_m",
        "route_analytics_looping_radius_m",
        "route_analytics_looping_min_distance_m",
        "route_replay_min_distance_m",
    )
    @classmethod
    def validate_positive_route_analytics_floats(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Route analytics numeric settings must be positive")
        return value

    @field_validator("route_replay_coordinate_precision")
    @classmethod
    def validate_route_replay_coordinate_precision(cls, value: int) -> int:
        if value < 3 or value > 7:
            raise ValueError("ROUTE_REPLAY_COORDINATE_PRECISION must be between 3 and 7")
        return value

    @field_validator(
        "route_analytics_poor_accuracy_ratio_threshold",
        "route_analytics_stationary_ratio_threshold",
    )
    @classmethod
    def validate_route_analytics_ratios(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("Route analytics ratio settings must be between 0 and 1")
        return value

    @field_validator(
        "impression_default_traffic_density_per_km",
        "impression_default_dwell_impressions_per_minute",
    )
    @classmethod
    def validate_nonnegative_impression_defaults(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Impression default settings must be nonnegative")
        return value

    @field_validator(
        "impression_high_fraud_multiplier",
        "impression_medium_fraud_multiplier",
        "impression_low_fraud_multiplier",
        "impression_insufficient_data_confidence",
        "impression_min_confidence",
        "impression_max_confidence",
    )
    @classmethod
    def validate_impression_ratios(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("Impression ratio settings must be between 0 and 1")
        return value

    @field_validator(
        "payout_eligibility_stationary_radius_m",
        "payout_eligibility_stationary_window_min",
        "payout_eligibility_max_accuracy_m",
        "payout_eligibility_teleport_kmh",
        "payout_eligibility_max_ping_gap_seconds",
    )
    @classmethod
    def validate_positive_payout_eligibility_settings(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Payout eligibility settings must be positive")
        return value

    @field_validator("payout_eligibility_stationary_grace_min")
    @classmethod
    def validate_payout_eligibility_grace(cls, value: int) -> int:
        if value < 0:
            raise ValueError("PAYOUT_ELIGIBILITY_STATIONARY_GRACE_MIN must be non-negative")
        return value

    @field_validator("payout_default_hourly_rate_ngn")
    @classmethod
    def validate_payout_default_hourly_rate(cls, value: float) -> float:
        if value < 0:
            raise ValueError("PAYOUT_DEFAULT_HOURLY_RATE_NGN must be nonnegative")
        return value

    @field_validator(
        "payout_default_base_rate_per_km",
        "payout_default_base_rate_per_active_hour",
        "payout_default_target_zone_bonus_rate_per_km",
        "payout_default_bonus_zone_bonus_rate_per_km",
        "payout_default_estimated_impression_rate_per_1000",
        "payout_default_min_payout_per_trip",
    )
    @classmethod
    def validate_nonnegative_payout_defaults(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Payout default settings must be nonnegative")
        return value

    @field_validator("payout_default_max_payout_per_trip")
    @classmethod
    def validate_optional_payout_max(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("Payout max default must be nonnegative")
        return value

    @field_validator(
        "payout_default_low_fraud_multiplier",
        "payout_default_medium_fraud_multiplier",
        "payout_default_high_fraud_multiplier",
    )
    @classmethod
    def validate_payout_ratios(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("Payout ratio settings must be between 0 and 1")
        return value

    @field_validator(
        "heatmap_default_resolution_m",
        "heatmap_min_resolution_m",
        "heatmap_max_resolution_m",
        "heatmap_max_bbox_area_sq_km",
        "heatmap_max_date_range_days",
        "heatmap_max_cells",
    )
    @classmethod
    def validate_positive_heatmap_settings(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Heatmap settings must be positive")
        return value

    @field_validator("heatmap_min_trips_per_cell")
    @classmethod
    def validate_heatmap_min_trips_per_cell(cls, value: int) -> int:
        if value < 1:
            raise ValueError("HEATMAP_MIN_TRIPS_PER_CELL must be at least 1")
        return value

    @field_validator(
        "privacy_query_history_retention_days",
        "privacy_min_vehicles_per_cell",
        "privacy_min_trips_per_cell",
        "privacy_min_days_per_cell",
        "privacy_min_resolution_m",
    )
    @classmethod
    def validate_positive_privacy_settings(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Privacy disclosure settings must be positive")
        return value

    @field_validator("privacy_max_contributor_share")
    @classmethod
    def validate_privacy_contributor_share(cls, value: float) -> float:
        if value <= 0 or value > 1:
            raise ValueError("PRIVACY_MAX_CONTRIBUTOR_SHARE must be in (0, 1]")
        return value

    @field_validator("worker_sweep_interval_minutes")
    @classmethod
    def validate_worker_sweep_interval_minutes(cls, value: int) -> int:
        if not (1 <= value <= 60 and 60 % value == 0):
            raise ValueError(
                "WORKER_SWEEP_INTERVAL_MINUTES must be a divisor of 60 between 1 and 60"
            )
        return value

    @field_validator("worker_sweep_batch_size")
    @classmethod
    def validate_worker_sweep_batch_size(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("WORKER_SWEEP_BATCH_SIZE must be positive")
        return value

    @field_validator(
        "email_smtp_port",
        "email_delivery_max_attempts",
        "email_delivery_retry_base_seconds",
        "email_delivery_claim_seconds",
    )
    @classmethod
    def validate_positive_email_settings(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Email delivery settings must be positive")
        return value

    @field_validator("email_provider")
    @classmethod
    def validate_email_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"", "smtp"}:
            raise ValueError("EMAIL_PROVIDER must be blank or smtp")
        return normalized

    @field_validator("email_receipt_signing_secret")
    @classmethod
    def validate_email_receipt_signing_secret(
        cls, value: SecretStr | None
    ) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("EMAIL_RECEIPT_SIGNING_SECRET must be at least 32 characters")
        return value

    @field_validator("fraud_review_sla_days")
    @classmethod
    def validate_fraud_review_sla_days(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("FRAUD_REVIEW_SLA_DAYS must be positive")
        return value

    @field_validator("ping_retention_months")
    @classmethod
    def validate_ping_retention_months(cls, value: int) -> int:
        if value < 1:
            raise ValueError("PING_RETENTION_MONTHS must be at least 1")
        return value

    @field_validator("partition_premake_months")
    @classmethod
    def validate_partition_premake_months(cls, value: int) -> int:
        if value < 1:
            raise ValueError("PARTITION_PREMAKE_MONTHS must be at least 1")
        return value

    @field_validator("default_currency")
    @classmethod
    def normalize_default_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("DEFAULT_CURRENCY must be a 3-letter code")
        return normalized

    @field_validator("payout_crypto_keyring_b64")
    @classmethod
    def validate_payout_crypto_keyring(cls, value: SecretStr) -> SecretStr:
        try:
            raw = json.loads(value.get_secret_value())
            if not isinstance(raw, dict) or not raw:
                raise ValueError
            for version, encoded in raw.items():
                if not isinstance(version, str) or not version.isdigit() or int(version) < 1:
                    raise ValueError
                if not isinstance(encoded, str):
                    raise ValueError
                decoded = base64.b64decode(encoded, validate=True)
                if len(decoded) != 32:
                    raise ValueError
        except (binascii.Error, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(
                "PAYOUT_CRYPTO_KEYRING_B64 must be a JSON object of positive versions "
                "to base64-encoded 32-byte keys"
            ) from exc
        return value

    @field_validator("payout_crypto_key_version")
    @classmethod
    def validate_payout_crypto_key_version(cls, value: int) -> int:
        if value < 1:
            raise ValueError("PAYOUT_CRYPTO_KEY_VERSION must be positive")
        return value

    @property
    def payout_crypto_keys(self) -> dict[int, bytes]:
        raw = json.loads(self.payout_crypto_keyring_b64.get_secret_value())
        return {
            int(version): base64.b64decode(encoded, validate=True)
            for version, encoded in raw.items()
        }

    @property
    def installation_evidence_uploaders(self) -> frozenset[str]:
        return frozenset(
            part for part in self.installation_evidence_uploader_roles.split(",") if part
        )

    @property
    def installation_evidence_views(self) -> tuple[str, ...]:
        return tuple(part for part in self.installation_evidence_required_views.split(",") if part)

    @model_validator(mode="after")
    def validate_impression_confidence_bounds(self) -> "Settings":
        if self.payout_crypto_key_version not in self.payout_crypto_keys:
            raise ValueError("PAYOUT_CRYPTO_KEY_VERSION must exist in PAYOUT_CRYPTO_KEYRING_B64")
        if self.impression_min_confidence > self.impression_max_confidence:
            raise ValueError("IMPRESSION_MIN_CONFIDENCE must not exceed IMPRESSION_MAX_CONFIDENCE")
        if self.privacy_disclosure_synthetic_test_mode and self.environment.lower() != "test":
            raise ValueError("PRIVACY_DISCLOSURE_SYNTHETIC_TEST_MODE requires environment=test")
        if (
            self.payout_default_max_payout_per_trip is not None
            and self.payout_default_max_payout_per_trip < self.payout_default_min_payout_per_trip
        ):
            raise ValueError(
                "PAYOUT_DEFAULT_MAX_PAYOUT_PER_TRIP must not be below "
                "PAYOUT_DEFAULT_MIN_PAYOUT_PER_TRIP"
            )
        if not (
            self.heatmap_min_resolution_m
            <= self.heatmap_default_resolution_m
            <= self.heatmap_max_resolution_m
        ):
            raise ValueError(
                "HEATMAP_MIN_RESOLUTION_M must be <= HEATMAP_DEFAULT_RESOLUTION_M "
                "and HEATMAP_DEFAULT_RESOLUTION_M must be <= HEATMAP_MAX_RESOLUTION_M"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
