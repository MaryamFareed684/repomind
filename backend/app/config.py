from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Optional. Only used for api.github.com calls. Never logged, never sent elsewhere.
    github_token: str | None = None

    # Safety limits (every repo is untrusted input)
    max_repo_kb: int = 50_000            # GitHub-reported repo size, in KB
    max_zip_bytes: int = 20_000_000      # max download size (20 MB)
    max_uncompressed_bytes: int = 100_000_000  # protects against zip bombs
    max_file_bytes: int = 200_000        # skip single files bigger than 200 KB
    max_files: int = 500                 # max files we agree to index

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()