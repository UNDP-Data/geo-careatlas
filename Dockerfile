# Stage 1: Get the uv tool
FROM ghcr.io/astral-sh/uv:latest AS uv_bin

# Stage 2: Geospatial Base (Ubuntu/Debian based with GDAL/PROJ pre-installed)
FROM ghcr.io/osgeo/gdal:ubuntu-small-latest

# Setup Workdir
WORKDIR /server

# Install uv from the builder
COPY --from=uv_bin /uv /uvbin/uv
ENV PATH="/uvbin:${PATH}"

# 3. Essential System Dependencies
# We need CA-Certs for uv to download Python 3.11 and the 'crazy widgets'
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

# 4. Copy ONLY the lock/config files first
COPY pyproject.toml uv.lock .python-version ./

# 5. Install libraries (This layer is pulled from GHA cache if lock is unchanged)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# 6. NOW copy your local repo code (the part you edit often)
COPY . .

# 7. Fast link
RUN uv sync --frozen --no-dev

# 6. Runtime Configuration
ENV PYTHONPATH="/server/src"
ENV PYTHONUNBUFFERED=1

# Use 'uv run' to ensure the 3.11 environment is used correctly
CMD ["uv", "run", "uvicorn", "careatlas.app.server:app", "--host", "0.0.0.0", "--port", "80"]