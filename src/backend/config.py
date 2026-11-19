"""환경변수 기반 앱 설정. 잘못된 값이면 생성 시점에 예외가 나 시작되지 않는다."""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLATFORMS = ("claude", "chatgpt", "gemini")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", frozen=True
    )

    app_env: str = "debug"
    database_url: str = Field(default="sqlite:///./skillradar.db", max_length=500)
    github_token: SecretStr = Field(default=SecretStr(""), max_length=255)
    llm_api_key: SecretStr = Field(default=SecretStr(""), max_length=255)
    llm_base_url: str = Field(default="https://api.openai.com/v1", max_length=200)
    llm_model: str = Field(default="gpt-4o-mini", max_length=100)
    admin_token: SecretStr = Field(default=SecretStr(""), max_length=255)
    cron_secret: SecretStr = Field(default=SecretStr(""), max_length=255)  # Vercel Cron 인증용
    vapid_public_key: str = Field(default="", max_length=200)
    vapid_private_key: SecretStr = Field(default=SecretStr(""), max_length=255)
    vapid_subject: str = Field(default="mailto:admin@example.com", max_length=200)
    schedule_hour: int = Field(default=6, ge=0, le=23)
    schedule_timezone: str = Field(default="Asia/Seoul", max_length=64)
    queries_path: Path = Path(__file__).parent / "queries.yaml"
    langsmith_api_key: SecretStr = Field(default=SecretStr(""), max_length=255)
    langsmith_project: str = Field(default="skillradar", max_length=100)
    langsmith_tracing: bool = False
    llm_judge_model: str = Field(default="", max_length=100)  # 비우면 llm_model 사용
    checkpoint_path: str = Field(default="", max_length=500)  # LangGraph SQLite 체크포인터

    @field_validator("database_url")
    @classmethod
    def _check_db_url(cls, value: str) -> str:
        if not value.startswith(
            ("sqlite:///", "postgresql://", "postgres://", "postgresql+psycopg://")
        ):
            raise ValueError("DATABASE_URL은 sqlite:/// 또는 postgresql:// 형식이어야 합니다.")
        return value

    @field_validator("llm_base_url")
    @classmethod
    def _check_llm_url(cls, value: str) -> str:
        if value and not value.startswith(("https://", "http://localhost")):
            raise ValueError("LLM_BASE_URL은 https 주소여야 합니다.")
        return value

    @property
    def langsmith_enabled(self) -> bool:
        """입력: 없음 / 출력: 트레이싱 활성 bool / 결과: langsmith_tracing과 API 키 존재 여부"""
        return self.langsmith_tracing and bool(self.langsmith_api_key.get_secret_value())

    @property
    def judge_model(self) -> str:
        """입력: 없음 / 출력: judge 모델명 / 결과: llm_judge_model 우선, 없으면 llm_model"""
        return self.llm_judge_model or self.llm_model

    @property
    def llm_enabled(self) -> bool:
        """입력: 없음 / 출력: LLM 사용 가능 bool / 결과: llm_api_key 존재 여부"""
        return bool(self.llm_api_key.get_secret_value())

    @property
    def push_enabled(self) -> bool:
        """입력: 없음 / 출력: 푸시 발송 가능 bool / 결과: VAPID 키+mailto subject 충족 여부"""
        return bool(
            self.vapid_public_key
            and self.vapid_private_key.get_secret_value()
            and self.vapid_subject.startswith("mailto:")
        )

    def platform_queries(self) -> dict[str, list[str]]:
        """queries.yaml에서 플랫폼별 GitHub 검색 쿼리 목록을 읽는다.

        입력: 없음 (self.queries_path 파일 사용)
        출력: {"claude": [...], "chatgpt": [...], "gemini": [...]} 쿼리 dict
        결과: 파일 없음/파싱 실패 시 예외 전파
        """
        data = yaml.safe_load(self.queries_path.read_text(encoding="utf-8"))
        return {p: list(data.get(p, [])) for p in PLATFORMS}


@lru_cache
def get_settings() -> Settings:
    """환경변수/.env에서 Settings를 로드한다. 프로세스당 1회 캐시.

    입력: 없음
    출력: 검증된 Settings 인스턴스
    결과: 잘못된 env 값이면 생성 시점에 ValidationError 발생
    """
    return Settings()
