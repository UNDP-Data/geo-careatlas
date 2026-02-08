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

# 4. Copy the entire repository
# This includes your .python-version (3.11) and pyproject.toml
COPY . .

# 5. The 'Honest' Environment Build
# uv sees .python-version, downloads 3.11, and builds the venv.
# We don't use --system here because you want a managed 3.11 venv.
RUN uv sync --frozen --no-dev --no-cache

# 6. Runtime Configuration
ENV PYTHONPATH="/server/src"
ENV PYTHONUNBUFFERED=1

# Use 'uv run' to ensure the 3.11 environment is used correctly
CMD ["uv", "run", "uvicorn", "careatlas.app.server:app", "--host", "0.0.0.0", "--port", "80"]