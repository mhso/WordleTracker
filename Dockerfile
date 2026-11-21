FROM python:3.14-trixie
WORKDIR /wordle_tracker

# Set environment variables
ENV UV_INSTALL_DIR=/bin

# Copy pyproject.toml
COPY pyproject.toml uv.lock ./

# Download UV and install requirements
RUN curl -LsSf https://astral.sh/uv/install.sh | bash && uv sync --no-dev

# Copy code and resources
COPY .env ./.env
COPY src ./src
COPY resources ./resources

# Run the server
WORKDIR /wordle_tracker/src
CMD uv run main.py