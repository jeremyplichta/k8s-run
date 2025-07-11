# <img src="k8rlogo.png" alt="k8r logo" width="40" height="40" style="vertical-align: middle;"> k8s-run (k8r)

<div align="center">
  <img src="k8rchef.png" alt="k8r chef" width="300">
  <br>
  <em>A minimal tool to easily run Kubernetes Jobs from local directories, GitHub repositories, Dockerfiles, or container images.</em>
  <br><br>
  
  [![Kubernetes](https://img.shields.io/badge/kubernetes-ready-326ce5.svg?logo=kubernetes&logoColor=white)](https://kubernetes.io/)
  [![Python](https://img.shields.io/badge/python-3.8+-3776ab.svg?logo=python&logoColor=white)](https://python.org/)
  [![uv](https://img.shields.io/badge/built%20with-uv-purple.svg)](https://github.com/astral-sh/uv)
</div>

## 🚀 Overview

k8s-run (shortened to `k8r`) simplifies running workloads in Kubernetes by automatically creating Jobs from various sources:

| Source Type | Description | Use Case |
|-------------|-------------|----------|
| 📁 **Local directories** | Files packaged into ConfigMaps | Quick scripts, data processing |
| 🐙 **GitHub repositories** | Code cloned directly in container | CI/CD, testing, deployment |
| 🐳 **Dockerfiles** | Images built and pushed to registry | Custom environments, complex apps |
| 📦 **Container images** | Run existing images directly | Redis, databases, pre-built tools |

## ✨ Key Features

- 🔄 **Parallel execution** - Run multiple job instances simultaneously
- ⏱️ **Timeout control** - Configurable job timeouts with sensible defaults
- 🏷️ **Smart labeling** - Isolates k8r jobs from other cluster workloads
- 🔍 **Easy monitoring** - Built-in job status tracking and log viewing
- 🛡️ **Safety first** - Only manages jobs it created, prevents accidents
- 🎯 **Namespace aware** - Automatically detects your current kubectl context

## 📦 Installation

### Prerequisites

- ✅ Python 3.8+
- ✅ Kubernetes cluster access (kubectl configured)
- ✅ Docker (for Dockerfile mode)
- ✅ [uv package manager](https://github.com/astral-sh/uv)

### ⚡ Quick Install (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/jeremyplichta/k8s-run/main/install.sh | bash
```

This will:
- 📥 Download k8r to `~/.local/bin/k8r/`
- 🔧 Set up dependencies automatically  
- 🔗 Add shell integration to your profile
- ✅ Make `k8r` available globally

### 🔄 Update k8r

```bash
# Re-run the installer to update to the latest version
curl -fsSL https://raw.githubusercontent.com/jeremyplichta/k8s-run/main/install.sh | bash
```

### 🔧 Manual Install

```bash
git clone https://github.com/jeremyplichta/k8s-run.git
cd k8s-run
uv sync  # Optional - the shell function will do this automatically
```

### 🔗 Shell Integration (Manual Install Only)

If you installed manually, add the shell function to your profile:

```bash
# Run from the k8s-run directory
python k8r.py env >> ~/.zshrc  # or ~/.bashrc
source ~/.zshrc

# Now you can use k8r from anywhere! 🎉
k8r --help
```

> 💡 **Note**: The quick install script handles this automatically!

<details>
<summary>🔍 What the shell function does</summary>

The shell function automatically:
- ✨ Creates a virtual environment (`.venv`) in the k8r directory if it doesn't exist
- 📦 Installs dependencies using `uv sync` on first run
- 🔄 Activates the virtual environment and runs the command
- 📍 Keeps you in your current working directory

</details>

## 🚀 Quick Start

### 📁 Run a local directory

```bash
# Run a Python script from current directory with 8 parallel jobs
k8r ./ --num 8 -- python run_script.py --arg1 value1

# Use a specific timeout
k8r ./ --timeout 30m -- ./my_script.sh
```

### 🐙 Run from GitHub

```bash
# Clone and run from GitHub repository
k8r git@github.com:user/repo.git --num 2 -- python main.py

# Using HTTPS URL
k8r https://github.com/user/repo.git -- make test
```

### 🐳 Run from Dockerfile

```bash
# Build image and run
k8r Dockerfile -- python app.py

# Use custom Dockerfile
k8r path/to/Custom.dockerfile -- ./entrypoint.sh
```

### 📦 Run container image

```bash
# Run existing container
k8r redis:7.0 -- redis-server --port 6380

# Run with custom command
k8r ubuntu:22.04 -- bash -c "apt update && apt install -y curl"
```

> 💡 **Pro Tip**: Without shell integration, run from the k8s-run directory:  
> `cd /path/to/k8s-run && uv run python k8r.py ./ --num 8 -- python run_script.py`

## 📖 Command Reference

### 🎯 Main Command

```bash
k8r SOURCE [OPTIONS] -- COMMAND [ARGS...]
```

| Option | Description | Default | Example |
|--------|-------------|---------|---------|
| `--num N` | Number of parallel job instances | `1` | `--num 8` |
| `--timeout DURATION` | Job timeout (1h, 30m, 3600s) | `1h` | `--timeout 30m` |
| `--base-image IMAGE` | Base container for directory/GitHub mode | `alpine:latest` | `--base-image python:3.9` |
| `--job-name NAME` | Custom job name | auto-generated | `--job-name my-job` |
| `-d, --detach` | Run in background without monitoring | disabled | `-d` |

### 🛠️ Job Management

| Command | Description | Example |
|---------|-------------|---------|
| `k8r ls` | 📋 List all k8r jobs | `k8r ls` |
| `k8r logs <job-name>` | 📄 View job logs | `k8r logs my-job` |
| `k8r logs <job-name> -f` | 📺 Follow logs in real-time | `k8r logs my-job -f` |
| `k8r rm <job-name>` | 🗑️ Delete a job | `k8r rm my-job` |
| `k8r rm <job-name> -f` | ⚠️ Force delete (even with running pods) | `k8r rm my-job -f` |
| `k8r env` | 🔧 Print shell integration code | `k8r env` |

### 📊 Example Output

```bash
$ k8r ls
Job Name     | Type       | Desired | Running | Complete | Failed
=================================================================
data-proc    | directory  | 8       | 2       | 6        | 0     
redis-test   | container  | 1       | 0       | 1        | 0
```

## ⚙️ Advanced Usage

### 🌍 Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `K8R_NAMESPACE` | Kubernetes namespace | *auto-detected from kubeconfig* |
| `K8R_REGISTRY` | Docker registry for Dockerfile mode | `gcr.io` |
| `K8R_PROJECT` | Registry project for Dockerfile mode | `default-project` |

### 🚀 Startup Scripts

For directory and GitHub modes, if a `k8s-startup.sh` file exists, it will be executed before your command:

```bash
#!/bin/bash
# k8s-startup.sh - Automatic setup script
apt-get update
apt-get install -y python3-pip
pip3 install -r requirements.txt
```

### 🐳 Custom Base Images

```bash
# Python projects
k8r ./ --base-image python:3.9 -- python app.py

# Node.js projects  
k8r ./ --base-image node:16 -- npm start

# GPU workloads
k8r ./ --base-image tensorflow/tensorflow:latest-gpu -- python train.py
```

### 📦 Registry Configuration

```bash
export K8R_REGISTRY=your-registry.com
export K8R_PROJECT=your-project
k8r Dockerfile -- python app.py
```

## 💡 Real-World Examples

### 📊 Data Processing Pipeline

```bash
# Process large datasets with 10 parallel workers
k8r ./data-processor --num 10 --timeout 2h -- \
  python process.py --input /data --batch-size 1000
```

### 🧪 Distributed Testing

```bash
# Run comprehensive test suite across multiple pods
k8r https://github.com/jeremyplichta/k8s-run.git --num 4 -- \
  pytest tests/ -v --parallel
```

### 🤖 Machine Learning Training

```bash
# Train ML model with GPU acceleration
k8r ./ml-training --base-image tensorflow/tensorflow:latest-gpu -- \
  python train.py --epochs 100 --learning-rate 0.001
```

### ⚡ High-Throughput Batch Processing

```bash
# Process job queue with 20 workers
k8r ./batch-processor --num 20 --timeout 4h -- \
  python worker.py --queue redis://redis:6379 --batch-size 50
```

### 🔄 ETL Pipeline

```bash
# Extract, transform, load data pipeline
k8r git@github.com:company/etl-pipeline.git --num 5 -- \
  python etl.py --source postgres://db:5432 --target s3://bucket/data
```

## 🔧 How It Works

<div align="center">
  <img src="https://img.shields.io/badge/🏗️-Architecture-blue?style=for-the-badge">
</div>

### 📁 Directory Mode
1. 🗜️ **Archive**: Creates tar.gz of your directory
2. 🗂️ **ConfigMap**: Stores archive in Kubernetes ConfigMap  
3. 🔗 **Mount**: Mounts ConfigMap in container at `/configmap`
4. 📦 **Extract**: Unpacks files to `/workspace`
5. 🏃 **Execute**: Runs your command in the workspace

### 🐙 GitHub Mode  
1. 📥 **Clone**: Uses `git clone` in the container
2. 🚀 **Setup**: Runs optional `k8s-startup.sh` 
3. 🎯 **Execute**: Runs your command in cloned directory

### 🐳 Dockerfile Mode
1. 🔨 **Build**: Builds Docker image from Dockerfile
2. 📤 **Push**: Pushes to configured registry
3. 🎯 **Deploy**: Creates Job using built image

### 📦 Container Mode
1. 🚀 **Direct**: Uses specified container image directly
2. 🎯 **Execute**: Runs your command or image's entrypoint

---

## 🛠️ Troubleshooting

### ❓ Common Issues

| Problem | Solution |
|---------|----------|
| 🚫 "Could not load Kubernetes configuration" | • Ensure kubectl is configured: `kubectl cluster-info`<br>• Check kubeconfig: `echo $KUBECONFIG` |
| 🐳 "Permission denied" for Docker | • Ensure Docker daemon is running<br>• Add user to docker group: `sudo usermod -aG docker $USER` |
| ⚠️ Job fails immediately | • Check logs: `k8r logs <job-name>`<br>• Verify base image has required tools<br>• Check k8s-startup.sh for errors |
| 📦 ConfigMap too large | • Directory mode has size limits (~1MB)<br>• Use .gitignore patterns to exclude large files<br>• Consider using GitHub mode instead |

### 🔍 Debug Mode

```bash
export KUBERNETES_DEBUG=1
k8r ./my-project -- python debug.py
```

---

## 🤝 Contributing

We welcome contributions! Here's how to get started:

1. 🍴 Fork the repository
2. 🌿 Create a feature branch: `git checkout -b feature/amazing-feature`
3. ✨ Make your changes
4. 🧪 Run tests: `pytest`
5. 📝 Submit a pull request

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

<div align="center">
  <img src="k8rlogo.png" alt="k8r logo" width="32" height="32">
  <br>
  <strong>k8s-run (k8r)</strong> - Making Kubernetes Jobs simple and fun!
  <br><br>
  
  ⭐ **Star this repo if you find it useful!** ⭐
  
  <br>
  
  Made with ❤️ for the Kubernetes community
</div>