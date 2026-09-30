FROM python:3.10-slim

# Prevent Python from writing .pyc and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV CMAKE_BUILD_PARALLEL_LEVEL=1

# Install runtime and build dependencies for OpenCV and dlib
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Upgrade pip and install precompiled dlib-bin first (avoids slow OOM compilation on Render)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir dlib-bin

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose Render dynamic port
EXPOSE 8000

# Start API server using dynamic PORT
CMD ["python", "run_api.py"]
