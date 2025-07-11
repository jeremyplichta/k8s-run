#!/bin/bash
set -e

# k8s-run (k8r) installer script
# Usage: curl -fsSL https://raw.githubusercontent.com/jeremyplichta/k8s-run/main/install.sh | bash

INSTALL_DIR="$HOME/.local/bin/k8r"
REPO_URL="https://github.com/jeremyplichta/k8s-run.git"
REPO_NAME="k8s-run"

echo "🚀 Installing k8s-run (k8r)..."

# Check prerequisites
echo "🔍 Checking prerequisites..."

if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed"
    exit 1
fi

if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl is required but not installed"
    exit 1
fi

if ! command -v uv &> /dev/null; then
    echo "❌ uv is required but not installed"
    echo "💡 Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo "✅ All prerequisites found"

# Create install directory
echo "📁 Creating installation directory..."
mkdir -p "$INSTALL_DIR"

# Clone repository
echo "📥 Downloading k8r..."
if [ -d "$INSTALL_DIR/$REPO_NAME" ]; then
    echo "🔄 Updating existing installation..."
    cd "$INSTALL_DIR/$REPO_NAME"
    git pull
else
    cd "$INSTALL_DIR"
    git clone "$REPO_URL"
    cd "$REPO_NAME"
fi

# Install dependencies
echo "📦 Installing dependencies..."
uv sync

# Get user's shell type
USER_SHELL=$(basename "$SHELL")
if [ "$USER_SHELL" = "zsh" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ "$USER_SHELL" = "bash" ]; then
    SHELL_RC="$HOME/.bashrc"
else
    # Default to detecting common shell config files
    if [ -f "$HOME/.zshrc" ]; then
        SHELL_RC="$HOME/.zshrc"
    else
        SHELL_RC="$HOME/.bashrc"
    fi
fi

# Add shell integration
echo "🔧 Setting up shell integration..."
if ! grep -q "k8r()" "$SHELL_RC" 2>/dev/null; then
    echo "" >> "$SHELL_RC"
    echo "# k8s-run (k8r) - Added by installer" >> "$SHELL_RC"
    python k8r.py env >> "$SHELL_RC"
    echo "✅ Shell integration added to $SHELL_RC"
else
    echo "ℹ️  Shell integration already exists in $SHELL_RC"
fi

# Source shell configuration and test installation
echo "🔄 Activating k8r in current shell..."
source "$SHELL_RC" 2>/dev/null || true

echo "🧪 Testing installation..."
if command -v k8r &> /dev/null; then
    echo "✅ k8r is now available!"
else
    echo "⚠️  k8r function loaded but may need new shell session"
fi

echo ""
echo "🎉 k8s-run (k8r) installation complete!"
echo ""
echo "📍 Installed to: $INSTALL_DIR/$REPO_NAME"
echo "🔧 Shell integration: $SHELL_RC"
echo ""
echo "🚀 k8r is ready to use:"
echo "   k8r --help"
echo ""
echo "💡 Example usage:"
echo "   k8r ./ --num 4 -- python my_script.py"
echo "   k8r redis:7.0 -- redis-server --version"
echo "   k8r ls"
echo ""
echo "📚 Full documentation: https://github.com/jeremyplichta/k8s-run"