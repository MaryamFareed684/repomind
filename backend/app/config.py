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
    max_json_bytes: int = 5_000          # bigger .json files are usually data, not code

    # Chunking
    chunk_max_lines: int = 120           # a function/class longer than this gets split
    chunk_window_lines: int = 60         # size of each piece when we split by lines
    chunk_overlap_lines: int = 8         # lines repeated between neighbouring pieces

    # Embeddings and search
    embedding_model: str = "BAAI/bge-small-en-v1.5"  # runs via fastembed (ONNX)
    qdrant_path: str = "data/qdrant"     # local folder; ":memory:" in tests
    embed_batch_size: int = 32           # chunks embedded per step
    candidate_k: int = 30                # results each method returns before merging
    rrf_k: int = 60                      # the "60" in 1 / (60 + rank)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()