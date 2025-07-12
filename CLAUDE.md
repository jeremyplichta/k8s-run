# CLAUDE.md - k8s-run (k8r) Project Guide

## Project Overview

k8s-run (shortened to `k8r`) is a minimal tool that simplifies running workloads in Kubernetes by automatically creating Jobs from various sources: local directories, GitHub repositories, Dockerfiles, or container images. It abstracts away the complexity of Kubernetes YAML configuration while providing powerful features like parallel execution, timeout control, secret management, and job monitoring.

The tool is designed to bridge the gap between local development and Kubernetes deployment, making it easy to run scripts, process data, or test applications in a Kubernetes environment without requiring deep Kubernetes knowledge.

## Project Structure & File Layout

```
k8s-run/
├── k8r.py              # Main application (single-file architecture)
├── README.md           # Comprehensive user documentation
├── pyproject.toml      # Python project configuration & dependencies
├── install.sh          # Automated installation script
├── spec.md             # Technical specifications
├── TASK_MEMORY.md      # Development task tracking
├── k8rlogo.png         # Project logo
├── k8rchef.png         # Chef mascot image
├── uv.lock            # UV package manager lock file
└── CLAUDE.md          # This file - development guide
```

### File Responsibilities

- **`k8r.py`** (1000+ lines): The entire application in a single Python file containing all logic for Kubernetes job creation, monitoring, and management
- **`pyproject.toml`**: Project metadata, dependencies (kubernetes, click, pyyaml, docker, requests), and build configuration for UV package manager
- **`install.sh`**: Shell script that downloads k8r to `~/.local/bin/k8r/` and sets up shell integration
- **`README.md`**: User-facing documentation with installation instructions, examples, and troubleshooting

## Core Architecture

### Main Class: `K8sRun`

The application is built around a single main class that handles all Kubernetes operations:

**Initialization** (`__init__`):
- Loads Kubernetes configuration (kubeconfig or in-cluster)
- Sets up API clients (`BatchV1Api` for jobs, `CoreV1Api` for pods/secrets/configmaps)
- Configures SSL settings to match kubectl behavior
- Determines active namespace from context or environment

**Key Attributes**:
- `self.batch_v1`: Kubernetes Jobs API client
- `self.core_v1`: Core Kubernetes resources API client  
- `self.namespace`: Active Kubernetes namespace

## High-Level Function Categories

### 1. Source Type Detection & Job Creation

| Function | Location | Purpose |
|----------|----------|---------|
| `detect_source_type()` | k8r.py:75 | Identifies if source is directory, GitHub repo, Dockerfile, or container image |
| `generate_job_name()` | k8r.py:88 | Creates unique job names with auto-incrementing for conflicts |
| `job_exists()` | k8r.py:117 | Checks if a job already exists in the namespace |

### 2. Core Job Management

| Function | Location | Purpose |
|----------|----------|---------|
| `create_job()` | k8r.py:175 | Main job creation orchestrator - handles all source types |
| `run_job_with_options()` | k8r.py:~300 | Enhanced job runner with YAML output and deployment options |
| `monitor_job()` | k8r.py:~400 | Real-time job progress monitoring and status updates |
| `list_jobs()` | k8r.py:~500 | Lists all k8r-created jobs with comprehensive status |
| `delete_job()` | k8r.py:~600 | Deletes jobs with optional secret cleanup |

### 3. Container Creation (by Source Type)

| Function | Location | Purpose |
|----------|----------|---------|
| `create_directory_container()` | k8r.py:~250 | Creates containers that extract and run from ConfigMaps |
| `create_github_container()` | k8r.py:~280 | Creates containers that clone GitHub repos |
| `create_container_container()` | k8r.py:~320 | Creates containers from existing images |
| `build_and_push_dockerfile()` | k8r.py:~350 | Builds Docker images and pushes to registry |

### 4. Secret Management System

| Function | Location | Purpose |
|----------|----------|---------|
| `create_secret()` | k8r.py:~700 | Creates secrets from files, directories, or strings |
| `create_secret_with_options()` | k8r.py:~750 | Enhanced secret creation with job association |
| `get_job_secrets()` | k8r.py:~800 | Retrieves all secrets associated with a job |
| `delete_job_secrets()` | k8r.py:~850 | Bulk deletion of job-associated secrets |

### 5. Resource Management

| Function | Location | Purpose |
|----------|----------|---------|
| `create_directory_configmap()` | k8r.py:127 | Packages directories into tar.gz ConfigMaps |
| `create_deployment()` | k8r.py:~900 | Creates Deployments instead of Jobs for long-running services |
| `get_job_logs()` | k8r.py:~950 | Retrieves pod logs with optional following |

## Key Concepts & Patterns

### Source Type Handling

k8r supports four distinct source types with different execution patterns:

1. **Directory Mode**: 
   - Packages local files into tar.gz ConfigMaps
   - Mounts ConfigMap as volume in container
   - Extracts files to `/workspace` and executes commands

2. **GitHub Mode**:
   - Uses `git clone` directly in container initialization
   - Supports both SSH and HTTPS GitHub URLs
   - Executes optional `k8s-startup.sh` before main command

3. **Dockerfile Mode**:
   - Builds Docker images using local Docker daemon
   - Pushes to configured registry (default: gcr.io)
   - Creates jobs using the built image

4. **Container Mode**:
   - Uses existing container images directly
   - Runs specified command or image's default entrypoint

### Labeling Strategy

All k8r-created resources use consistent labels for identification and management:

```yaml
labels:
  created-by: k8r                    # Identifies all k8r resources
  k8r-job: {job_name}               # Associates resources with jobs
  k8r-source-type: {type}           # Tracks source type (directory/github/dockerfile/container)
  k8r-secret: {secret_name}         # Links secrets to logical names (secrets only)
  k8r-type: deployment              # Distinguishes deployments from jobs (deployments only)
```

### Secret Management Pattern

Secrets follow a sophisticated auto-discovery and mounting system:

- **Naming**: `{job_name}-{sanitized_secret_name}`
- **Environment Variables**: Each secret key becomes `{SECRET_NAME}_{KEY_NAME}`
- **Volume Mounts**: Secrets mounted at `/k8r/secret/{secret_name}/`
- **Auto-Discovery**: Jobs automatically mount secrets matching their name pattern

### Configuration Patterns

**Environment Variables**:
- `K8R_NAMESPACE`: Override default namespace
- `K8R_ORIGINAL_PWD`: Preserve original working directory for job naming
- `K8R_REGISTRY`: Docker registry for Dockerfile mode (default: gcr.io)
- `K8R_PROJECT`: Registry project name (default: default-project)

**Default Values**:
- Base image: `alpine:latest`
- Timeout: `1h` (3600 seconds)
- Parallelism: `1` instance
- Restart policy: `Never` (unless `--retry` specified)
- Working directory: `/workspace` (directory/GitHub modes)

## Development Tips & Context

### Testing the Tool

**Prerequisites**:
- Working Kubernetes cluster with `kubectl` configured
- Python 3.8+ installed
- UV package manager installed
- Docker daemon running (for Dockerfile mode)

**Common Testing Patterns**:

```bash
# Test directory mode locally
k8r ./ -- echo "Hello from k8r"

# Test with multiple instances
k8r ./ --num 3 -- python -c "import os; print(f'Pod: {os.environ.get(\"HOSTNAME\")}')"

# Test GitHub mode
k8r https://github.com/jeremyplichta/k8s-run.git -- python -c "print('GitHub test')"

# Test container mode
k8r alpine:latest -- echo "Container test"

# Test YAML generation without applying
k8r ./ --show-yaml -- echo "test"

# Test secret creation and mounting
k8r secret test-secret "my-value"
k8r ./ -- env | grep TEST_SECRET
```

**Development Workflow**:

1. **Local Development**: Use `uv run python k8r.py` for direct execution
2. **Shell Integration**: Test with `k8r` command after running `python k8r.py env >> ~/.zshrc`
3. **Dependency Management**: Use `uv sync` to install/update dependencies
4. **Code Style**: Project includes black, flake8, and mypy for code quality

### Virtual Environment & UV Integration

The project uses UV (next-generation Python package manager) instead of pip:

- **Virtual Environment**: Automatically managed in `.venv/` directory
- **Lock File**: `uv.lock` ensures reproducible builds
- **Shell Function**: Automatically activates venv and runs commands
- **Installation**: `uv sync` installs all dependencies including dev tools

### Kubernetes Configuration

**SSL/TLS Handling**:
- The tool includes special SSL configuration to match kubectl behavior
- Disables SSL warnings for self-signed certificates
- Falls back to in-cluster config when kubeconfig unavailable

**Namespace Detection**:
- Automatically detects namespace from current kubectl context
- Can be overridden with `--namespace` flag or `K8R_NAMESPACE` environment variable
- Defaults to `default` namespace if detection fails

### Common Development Patterns

**Error Handling**:
- Graceful fallback from kubeconfig to in-cluster config
- Informative error messages for missing dependencies
- SSL/TLS troubleshooting guidance

**Resource Cleanup**:
- Jobs can be deleted individually or with associated secrets
- ConfigMaps are automatically cleaned up with jobs
- Force deletion handles stuck resources

**Monitoring & Debugging**:
- Real-time job status monitoring with progress indicators
- Comprehensive log viewing with follow mode
- YAML output for debugging resource definitions

### Shell Integration Details

The shell function (`k8r env`) provides:
- **Environment Setup**: Automatically creates and activates Python virtual environment
- **Dependency Installation**: Runs `uv sync` on first use
- **Path Preservation**: Maintains original working directory for accurate job naming
- **Cross-Shell Support**: Works with bash, zsh, and other POSIX shells

This architecture allows k8r to be self-contained while providing a seamless user experience that feels like a native command-line tool.

## Working with the Codebase

### Code Organization

The single-file architecture makes the codebase easy to understand and modify:

- **Class Methods**: Most functionality is organized as methods of the `K8sRun` class
- **Helper Functions**: Utility functions for CLI parsing, updates, and environment setup
- **Error Handling**: Comprehensive exception handling with user-friendly error messages
- **Documentation**: Inline docstrings explain complex Kubernetes interactions

### Adding New Features

When extending k8r:

1. **New Source Types**: Add detection logic to `detect_source_type()` and create corresponding container creation method
2. **New CLI Options**: Extend the argument parser in `main()` and pass options through the call chain
3. **New Resource Types**: Follow the existing labeling patterns and cleanup mechanisms
4. **New Secret Features**: Extend the secret management system while maintaining backward compatibility

### Dependencies

Core dependencies and their purposes:
- **kubernetes**: Official Kubernetes Python client
- **click**: Command-line interface framework (though current implementation uses argparse)
- **pyyaml**: YAML parsing for Kubernetes resource generation
- **docker**: Docker daemon interaction for Dockerfile mode
- **requests**: HTTP requests for various operations

The project maintains Python 3.8+ compatibility and uses modern Python features where appropriate.