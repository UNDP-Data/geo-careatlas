# Stage 1: Get the uv tool
FROM ghcr.io/astral-sh/uv:latest AS uv_bin

# Stage 2: Geospatial Base (Ubuntu/Debian based with GDAL/PROJ pre-installed)
FROM ghcr.io/osgeo/gdal:ubuntu-small-latest



# Install uv from the builder
COPY --from=uv_bin /uv /uvbin/uv
ENV PATH="/uvbin:${PATH}"

# 3. Essential System Dependencies
# We need CA-Certs for uv to download Python 3.11 and the 'crazy widgets'
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    git \
    tini \
    && rm -rf /var/lib/apt/lists/*


# 1. Define build arguments with safe defaults
ARG USER_ID=1000
ARG GROUP_ID=1000

# 2. Create a user only if it's not root (ID 0)
# This prevents conflicts in production environments like AKS
RUN if [ "$USER_ID" -ne 0 ]; then \
    groupadd -g $GROUP_ID devuser || true && \
    useradd -l -u $USER_ID -g $GROUP_ID -m devuser || true; \
    fi

# Setup Workdir
WORKDIR /server

# 4. Fix permissions for the WORKDIR
# This ensures that even if you switch users, the folder is accessible
RUN chown -R $USER_ID:$GROUP_ID /server && chmod -R 755 /server

# 5. Switch to the user (optional)
# If you leave this as 'root', the container starts as root but allows the user 
# to take over via docker-compose.
USER $USER_ID



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

ENTRYPOINT ["/usr/bin/tini", "--"]

# Use 'uv run' to ensure the 3.11 environment is used correctly
CMD ["uv", "run", "uvicorn", "careatlas.app.server:app", "--host", "0.0.0.0", "--port", "80"]