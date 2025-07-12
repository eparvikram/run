# Use an official Python runtime as a parent image.
# We choose a slim-buster image for smaller size, which is good for production.
FROM python:3.10-slim-buster

# Set the working directory in the container.
# All subsequent commands will run relative to this directory.
WORKDIR /app

# Install system dependencies if your Python packages require them.
# For example, if you were using image processing libraries (Pillow), you might need `libjpeg-dev`.
# Currently, your stack doesn't seem to have specific system-level dependencies.
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libpq-dev \  # Example for PostgreSQL client if needed
#     build-essential \ # For compiling some Python packages
#     && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container.
# This step is done first to leverage Docker's build cache.
# If only code changes, this layer won't be rebuilt.
COPY requirements.txt .

# Install any needed Python packages specified in requirements.txt.
# --no-cache-dir: Don't store the cache in the container, reducing image size.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container.
# The `./app` refers to your local `app` directory.
# The `/app/app` is the destination inside the container.
COPY ./app /app/app

# --- Environment Variables (Important for Production) ---
# DO NOT copy .env directly into the production Docker image if it contains sensitive data.
# Instead, pass them during `docker run` or manage them via Kubernetes secrets.
# However, if python-dotenv is explicitly used in your code, it needs a .env file.
# For this specific case, if your OPENAI_API_KEY and APP_API_KEY are passed at runtime,
# you don't strictly need to copy .env. But if your services relies on `load_dotenv()`
# finding it, it must be present.
# For demo/local, copying it is okay, but be aware of the security implication.
RUN source .env

# Expose the port that FastAPI will run on.
# This informs Docker that the container listens on the specified network port.
EXPOSE 8000

# Command to run the application.

# For development (using uvicorn directly with reload for convenience):
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# For production, it's highly recommended to use Gunicorn with Uvicorn workers.
# Gunicorn handles process management, graceful shutdowns, and has better load balancing.
# Adjust the number of workers (-w) based on your server's CPU cores (typically 2*CPU + 1).
# The --timeout 120 is an example, adjust based on your maximum expected generation time.
CMD ["gunicorn", "app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--timeout", "300"]
