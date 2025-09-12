
# Use Ubuntu 24.04 LTS as the base image
FROM ubuntu:24.04

# Set environment variables to avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install basic dependencies and tools
RUN apt-get update && apt-get install -y \
    git \
    gcc \
    g++ \
    build-essential \
    liblzma-dev \
    zlib1g-dev \
    libbz2-dev \
    libffi-dev \
    python3.12 \
    python3.12-dev \
    python3-pip \
    curl \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Disable the very annoying PEP 668 (in a container)
RUN rm /usr/lib/python3.12/EXTERNALLY-MANAGED

# Install NVIDIA CUDA 12.8 and related libraries
RUN curl -fsSL https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb -o cuda-keyring.deb \
    && dpkg -i cuda-keyring.deb \
    && rm cuda-keyring.deb \
    && apt-get update \
    && apt-get install -y \
        cuda-toolkit-12-8 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for CUDA
ENV PATH=/usr/local/cuda-12.8/bin:${PATH}
ENV LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:${LD_LIBRARY_PATH}

# Install cuDNN via pip to provide the required libraries
RUN pip3 install --no-cache-dir --break-system-packages nvidia-cudnn-cu12==9.1.0.70
ENV LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:/usr/local/lib/python3.12/dist-packages/nvidia/cudnn/lib/


# Set the working directory in the container
WORKDIR /app

# Copy requirements file first for better Docker layer caching
COPY requirements.txt /app/

# Install Python dependencies
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Load necessary models
RUN python3 -m spacy download en_core_web_sm


# Copy the application
COPY app/ /app/

# Command to run the transcription service
CMD ["python3", "main.py"]
