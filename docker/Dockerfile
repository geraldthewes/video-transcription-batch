# Build stage
FROM docker.io/nvidia/cuda:12.8.0-base-ubuntu24.04 AS builder
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    python3.12-dev \
    python3-pip \
    gcc \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
RUN rm /usr/lib/python3.12/EXTERNALLY-MANAGED
WORKDIR /app
# Install PyTorch for CUDA 12.8
RUN pip3 install --no-cache-dir torch==2.8.0+cu128 --index-url https://download.pytorch.org/whl/cu128
# Install remaining requirements
COPY docker/requirements.txt /app/
RUN pip3 install --no-cache-dir -r requirements.txt
# Ensure temp directories exist and download SpaCy model
RUN mkdir -p /tmp /var/tmp && python3 -m spacy download en_core_web_sm

# Final stage
FROM docker.io/nvidia/cuda:12.8.0-runtime-ubuntu24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    python3.12 \
    python3-pip \
    git \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
RUN rm /usr/lib/python3.12/EXTERNALLY-MANAGED
WORKDIR /app
# Copy Python environment from builder stage
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin /usr/local/bin
# Install git packages in final stage to ensure they're available
RUN pip3 install --no-cache-dir \
    git+https://github.com/geraldthewes/topic-treeseg.git \
    git+https://github.com/geraldthewes/multistep-transcriber.git
COPY docker/app/ /app/
CMD ["python3", "main.py"]
