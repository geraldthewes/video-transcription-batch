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
# Install custom Git repositories
RUN git clone https://github.com/geraldthewes/topic-treeseg.git /tmp/topic-treeseg \
    && cd /tmp/topic-treeseg \
    && pip3 install --no-cache-dir . \
    && rm -rf /tmp/topic-treeseg
RUN git clone https://github.com/geraldthewes/multistep-transcriber.git /tmp/multistep-transcriber \
    && cd /tmp/multistep-transcriber \
    && pip3 install --no-cache-dir . \
    && rm -rf /tmp/multistep-transcriber
# Install remaining requirements with dependencies to fix botocore issue - NUCLEAR OPTION V3
COPY docker/requirements.txt /app/
# FORCE CACHE INVALIDATION - SACRIFICE TO THE DOCKER GODS
RUN echo "Cache bust: $(date)" > /tmp/cache_bust.txt
RUN pip3 install --no-cache-dir -r requirements.txt
# Download SpaCy model
RUN python3 -m spacy download en_core_web_sm

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
# ULTIMATE CACHE DESTRUCTION - TIMESTAMP V4 $(date +%s)
RUN echo "Ultimate cache bust timestamp: $(date +%s%N)" > /tmp/ultimate_cache_bust.txt && cat /tmp/ultimate_cache_bust.txt
# Install ALL packages fresh in final stage
COPY docker/requirements.txt /app/
RUN pip3 install --no-cache-dir boto3>=1.35.0 botocore>=1.35.0
# FORCE FRESH GIT INSTALLS - NO CACHE
RUN echo "Installing git packages at: $(date)" && \
    pip3 install --no-cache-dir --force-reinstall git+https://github.com/geraldthewes/topic-treeseg.git && \
    pip3 install --no-cache-dir --force-reinstall git+https://github.com/geraldthewes/multistep-transcriber.git && \
    echo "Git packages installed successfully at: $(date)"
COPY docker/app/ /app/
CMD ["python3", "main.py"]
