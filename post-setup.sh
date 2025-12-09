#!/bin/sh

# Source secrets for this session (postCreateCommand)
if [ -f ".vault-secrets" ]; then
      source .vault-secrets
fi

# Add to .bashrc for future SSH sessions
if [ -f ".vault-secrets" ] && ! grep -q ".vault-secrets" ~/.bashrc 2>/dev/null; then
      cat >> ~/.bashrc <<'EOF'

# Auto-source Vault secrets on shell startup
if [ -f .vault-secrets ]; then
     set -a
     source .vault-secrets 2>/dev/null
     set +a
fi
EOF

fi
      
# Install ffmpeg (needs to be <= v7) 
sudo apt update
sudo apt install -y ffmpeg 

# Install basic packages
pip install torch==2.8.0 torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu --no-cache-dir
pip install torchcodec==0.7.0 --no-cache-dir
# GPU
#pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126

# Other Packages
pip install -r requirements.txt
pip install git+https://github.com/geraldthewes/topic-treeseg.git
pip install git+https://github.com/geraldthewes/multistep-transcriber.git
pip install build

# Install Spacy model
python -m spacy download en_core_web_sm
