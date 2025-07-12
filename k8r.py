#!/usr/bin/env python3
"""
k8s-run (k8r) - A minimal tool to easily run Kubernetes Jobs
"""

import argparse
import base64
import gzip
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import yaml
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException
    DEPENDENCIES_AVAILABLE = True
except ImportError:
    DEPENDENCIES_AVAILABLE = False


class K8sRun:
    def __init__(self):
        if not DEPENDENCIES_AVAILABLE:
            print("Error: Dependencies not installed. Please run 'uv sync' first.")
            sys.exit(1)
            
        try:
            # Load kubeconfig 
            config.load_kube_config()
            
            # Configure SSL settings to be more permissive like kubectl
            configuration = client.Configuration.get_default_copy()
            
            # Disable SSL warnings for self-signed certificates
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            # Set some SSL configuration that might help
            if hasattr(configuration, 'verify_ssl'):
                # Try to match kubectl's SSL behavior
                pass  # Let it use the kubeconfig settings
            
        except Exception as e:
            try:
                config.load_incluster_config()
            except Exception:
                print(f"Error: Could not load Kubernetes configuration: {e}")
                print("Make sure kubectl is configured and working: kubectl get pods")
                sys.exit(1)
        
        self.batch_v1 = client.BatchV1Api()
        self.core_v1 = client.CoreV1Api()
        
        # Get namespace from current context or environment variable
        try:
            contexts, active_context = config.list_kube_config_contexts()
            if active_context and 'namespace' in active_context['context']:
                default_namespace = active_context['context']['namespace']
            else:
                default_namespace = 'default'
        except:
            default_namespace = 'default'
            
        self.namespace = os.environ.get('K8R_NAMESPACE', default_namespace)

    def detect_source_type(self, source: str) -> str:
        """Detect the type of source: directory, github, dockerfile, or container"""
        if source == "Dockerfile" or (os.path.isfile(source) and source.endswith("Dockerfile")):
            return "dockerfile"
        elif source.startswith(("git@", "https://github.com", "http://github.com")):
            return "github"
        elif os.path.isdir(source):
            return "directory"
        elif ":" in source and not os.path.exists(source):
            return "container"
        else:
            raise ValueError(f"Could not determine source type for: {source}")

    def generate_job_name(self, source: str, job_name: Optional[str] = None) -> str:
        """Generate a unique job name"""
        if job_name:
            base_name = job_name
        elif source == "." or source == "./":
            # Use the original working directory if available, otherwise current directory
            original_pwd = os.environ.get('K8R_ORIGINAL_PWD')
            if original_pwd and os.path.isdir(original_pwd):
                base_name = os.path.basename(original_pwd)
            else:
                base_name = os.path.basename(os.getcwd())
        elif self.detect_source_type(source) == "github":
            base_name = source.split("/")[-1].replace(".git", "")
        elif self.detect_source_type(source) == "directory":
            base_name = os.path.basename(os.path.abspath(source))
        else:
            base_name = re.sub(r'[^a-z0-9-]', '-', source.lower())

        base_name = re.sub(r'[^a-z0-9-]', '-', base_name.lower()).strip('-')
        
        # Check if job exists and increment if needed
        counter = 0
        final_name = base_name
        while self.job_exists(final_name):
            counter += 1
            final_name = f"{base_name}-{counter}"
        
        return final_name

    def job_exists(self, job_name: str) -> bool:
        """Check if a job with the given name exists"""
        try:
            self.batch_v1.read_namespaced_job(name=job_name, namespace=self.namespace)
            return True
        except ApiException as e:
            if e.status == 404:
                return False
            raise

    def create_directory_configmap(self, source_path: str, job_name: str) -> str:
        """Create a configmap from a directory"""
        configmap_name = f"{job_name}-source"
        
        # Create tar.gz of the directory
        with tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False) as tmp_file:
            with tarfile.open(tmp_file.name, 'w:gz') as tar:
                for root, dirs, files in os.walk(source_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, source_path)
                        tar.add(file_path, arcname=arcname)
            
            # Read the tar.gz file and encode it
            with open(tmp_file.name, 'rb') as f:
                tar_data = base64.b64encode(f.read()).decode('utf-8')
        
        os.unlink(tmp_file.name)
        
        # Create configmap
        configmap = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(name=configmap_name),
            data={"source.tar.gz": tar_data}
        )
        
        try:
            self.core_v1.create_namespaced_config_map(
                namespace=self.namespace,
                body=configmap
            )
        except ApiException as e:
            if e.status == 409:  # Already exists
                self.core_v1.replace_namespaced_config_map(
                    name=configmap_name,
                    namespace=self.namespace,
                    body=configmap
                )
            else:
                raise
        except Exception as e:
            print(f"Error creating ConfigMap: {e}")
            print("This might be due to SSL/TLS configuration issues.")
            print("kubectl works but the Python kubernetes client has different SSL handling.")
            print("Try running: kubectl create configmap test --dry-run=client -o yaml")
            raise
        
        return configmap_name

    def create_job(self, source: str, command: List[str], num_instances: int = 1, 
                   timeout: str = "1h", base_image: str = "alpine:latest", 
                   job_name: Optional[str] = None, retry_limit: Optional[int] = None) -> str:
        """Create a Kubernetes job"""
        
        source_type = self.detect_source_type(source)
        final_job_name = self.generate_job_name(source, job_name)
        
        # Convert timeout to seconds
        timeout_seconds = self.parse_timeout(timeout)
        
        # Create job spec based on source type
        volumes = []
        if source_type == "directory":
            configmap_name = self.create_directory_configmap(source, final_job_name)
            container = self.create_directory_container(configmap_name, command, base_image)
            volumes = [
                client.V1Volume(
                    name="source",
                    config_map=client.V1ConfigMapVolumeSource(name=configmap_name)
                )
            ]
        elif source_type == "github":
            container = self.create_github_container(source, command, base_image)
        elif source_type == "dockerfile":
            # For dockerfile, we would build and push image first
            image_name = self.build_and_push_dockerfile(source, final_job_name)
            container = self.create_container_container(image_name, command)
        elif source_type == "container":
            container = self.create_container_container(source, command)
        else:
            raise ValueError(f"Unsupported source type: {source_type}")
        
        # Discover and mount secrets for this job
        job_secrets = self.get_job_secrets(final_job_name)
        secret_volumes = []
        secret_volume_mounts = []
        secret_env_vars = []
        
        for secret_info in job_secrets:
            secret_name = secret_info["secret_name"]
            secret_k8s_name = secret_info["name"]
            
            # Add volume for secret files
            sanitized_volume_name = f"secret-{self.sanitize_k8s_name(secret_name)}"
            secret_volumes.append(
                client.V1Volume(
                    name=sanitized_volume_name,
                    secret=client.V1SecretVolumeSource(secret_name=secret_k8s_name)
                )
            )
            
            # Add volume mounts for each secret key to avoid duplication
            for key in secret_info["data_keys"]:
                secret_volume_mounts.append(
                    client.V1VolumeMount(
                        name=sanitized_volume_name,
                        mount_path=f"/k8r/secrets/{key}",
                        sub_path=key,
                        read_only=True
                    )
                )
            
            # Add environment variables for each key in the secret
            for key in secret_info["data_keys"]:
                env_var_name = key.upper().replace("-", "_").replace(".", "_")
                secret_env_vars.append(
                    client.V1EnvVar(
                        name=env_var_name,
                        value_from=client.V1EnvVarSource(
                            secret_key_ref=client.V1SecretKeySelector(
                                name=secret_k8s_name,
                                key=key
                            )
                        )
                    )
                )
        
        # Add secret volumes to existing volumes
        volumes.extend(secret_volumes)
        
        # Update container with secret mounts and env vars
        if hasattr(container, 'volume_mounts') and container.volume_mounts:
            container.volume_mounts.extend(secret_volume_mounts)
        else:
            container.volume_mounts = secret_volume_mounts
            
        if hasattr(container, 'env') and container.env:
            container.env.extend(secret_env_vars)
        else:
            container.env = secret_env_vars
        
        if job_secrets:
            print(f"Mounting {len(job_secrets)} secrets for job '{final_job_name}'")
        
        # Determine restart policy and backoff limit
        restart_policy = "OnFailure" if retry_limit is not None else "Never"
        
        # Create job spec with conditional backoff limit
        job_spec = client.V1JobSpec(
            parallelism=num_instances,
            completions=num_instances,
            active_deadline_seconds=timeout_seconds,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={
                        "created-by": "k8r",
                        "k8r-job": final_job_name
                    }
                ),
                spec=client.V1PodSpec(
                    containers=[container],
                    volumes=volumes,
                    restart_policy=restart_policy
                )
            )
        )
        
        # Set backoff limit if retry is specified
        if retry_limit is not None:
            job_spec.backoff_limit = retry_limit
            
        # Create job with k8r labels
        job = client.V1Job(
            metadata=client.V1ObjectMeta(
                name=final_job_name,
                labels={
                    "created-by": "k8r",
                    "k8r-source-type": source_type
                }
            ),
            spec=job_spec
        )
        
        self.batch_v1.create_namespaced_job(namespace=self.namespace, body=job)
        return final_job_name

    def create_directory_container(self, configmap_name: str, command: List[str], 
                                 base_image: str):
        """Create container spec for directory mode"""
        init_script = """set -e
cd /workspace
echo "Extracting source..."
base64 -d /configmap/source.tar.gz | tar -xzf -
if [ -f k8s-startup.sh ]; then
    echo "Running k8s-startup.sh..."
    chmod +x k8s-startup.sh
    ./k8s-startup.sh
fi"""
        
        # Join command for shell execution (don't escape to allow variable expansion)
        command_str = " ".join(command)
        full_script = f"{init_script}\necho 'Running command...'\n{command_str}"
        
        full_command = ["sh", "-c", full_script]
        
        return client.V1Container(
            name="runner",
            image=base_image,
            command=full_command,
            working_dir="/workspace",
            volume_mounts=[
                client.V1VolumeMount(
                    name="source",
                    mount_path="/configmap"
                )
            ]
        )

    def create_github_container(self, github_url: str, command: List[str], 
                              base_image: str):
        """Create container spec for GitHub mode"""
        init_script = f"""
set -e
apk add --no-cache git
cd /workspace
git clone {github_url} .
if [ -f k8s-startup.sh ]; then
    echo "Running k8s-startup.sh..."
    chmod +x k8s-startup.sh
    ./k8s-startup.sh
fi
"""
        
        # Join command for shell execution (don't escape to allow variable expansion)  
        command_str = " ".join(command)
        full_command = ["sh", "-c", init_script + " && " + command_str]
        
        return client.V1Container(
            name="runner",
            image=base_image,
            command=full_command,
            working_dir="/workspace"
        )

    def create_container_container(self, image: str, command: List[str]):
        """Create container spec for container mode"""
        if command:
            # Join command args and wrap in shell for proper variable expansion
            command_str = " ".join(command)
            shell_command = ["/bin/sh", "-c", command_str]
        else:
            shell_command = None
            
        return client.V1Container(
            name="runner",
            image=image,
            command=shell_command
        )

    def build_and_push_dockerfile(self, dockerfile_path: str, job_name: str) -> str:
        """Build and push Docker image"""
        import docker
        
        # Get registry from environment or default to GCR
        registry = os.environ.get('K8R_REGISTRY', 'gcr.io')
        project = os.environ.get('K8R_PROJECT', 'default-project')
        
        image_name = f"{registry}/{project}/{job_name}:latest"
        
        try:
            client = docker.from_env()
            
            # Build the image
            print(f"Building Docker image: {image_name}")
            dockerfile_dir = os.path.dirname(os.path.abspath(dockerfile_path)) if dockerfile_path != "Dockerfile" else "."
            
            image, logs = client.images.build(
                path=dockerfile_dir,
                dockerfile=os.path.basename(dockerfile_path),
                tag=image_name,
                rm=True
            )
            
            # Print build logs
            for log in logs:
                if 'stream' in log:
                    print(log['stream'].strip())
            
            # Push the image
            print(f"Pushing image: {image_name}")
            push_logs = client.images.push(image_name, stream=True, decode=True)
            
            for log in push_logs:
                if 'status' in log:
                    print(f"{log['status']}: {log.get('progress', '')}")
                if 'error' in log:
                    raise Exception(f"Push failed: {log['error']}")
            
            return image_name
            
        except Exception as e:
            print(f"Error building/pushing Docker image: {e}")
            raise

    def parse_timeout(self, timeout_str: str) -> int:
        """Parse timeout string (e.g., '1h', '30m', '3600s') to seconds"""
        if timeout_str.endswith('s'):
            return int(timeout_str[:-1])
        elif timeout_str.endswith('m'):
            return int(timeout_str[:-1]) * 60
        elif timeout_str.endswith('h'):
            return int(timeout_str[:-1]) * 3600
        else:
            return int(timeout_str)

    def monitor_job(self, job_name: str, detach: bool = False) -> None:
        """Monitor job progress"""
        if detach:
            print(f"Job '{job_name}' started in background")
            return
        
        print(f"Monitoring job '{job_name}'...")
        
        while True:
            try:
                job = self.batch_v1.read_namespaced_job(name=job_name, namespace=self.namespace)
                status = job.status
                
                active = status.active or 0
                succeeded = status.succeeded or 0
                failed = status.failed or 0
                
                print(f"Status: Active={active}, Succeeded={succeeded}, Failed={failed}")
                
                if status.completion_time:
                    print(f"Job completed successfully at {status.completion_time}")
                    break
                elif status.failed and status.failed > 0:
                    print(f"Job failed with {status.failed} failures")
                    break
                
                time.sleep(5)
                
            except KeyboardInterrupt:
                print("\nMonitoring stopped by user")
                break
            except Exception as e:
                print(f"Error monitoring job: {e}")
                break

    def list_jobs(self) -> None:
        """List current k8r jobs"""
        try:
            # Filter for jobs created by k8r
            jobs = self.batch_v1.list_namespaced_job(
                namespace=self.namespace,
                label_selector="created-by=k8r"
            )
            
            if not jobs.items:
                print("No k8r jobs found in namespace: " + self.namespace)
                return
            
            # Calculate column widths based on content
            max_name_len = max(len(job.metadata.name) for job in jobs.items)
            name_width = max(max_name_len, len("Job Name")) + 2
            
            # Print header
            header = f"{'Job Name':<{name_width}} | {'Type':<10} | {'Desired':<7} | {'Running':<7} | {'Complete':<8} | {'Failed':<6}"
            print(header)
            print("=" * len(header))
            
            for job in jobs.items:
                name = job.metadata.name
                source_type = job.metadata.labels.get("k8r-source-type", "unknown")
                desired = job.spec.completions or 0
                status = job.status
                running = status.active or 0
                complete = status.succeeded or 0
                failed = status.failed or 0
                
                print(f"{name:<{name_width}} | {source_type:<10} | {desired:<7} | {running:<7} | {complete:<8} | {failed:<6}")
                
        except Exception as e:
            print(f"Error listing jobs: {e}")

    def get_job_logs(self, job_name: str, follow: bool = False) -> None:
        """Get logs for a job"""
        try:
            # Get pods for the k8r job
            pods = self.core_v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f"k8r-job={job_name},created-by=k8r"
            )
            
            if not pods.items:
                print(f"No pods found for job '{job_name}'")
                return
            
            for pod in pods.items:
                pod_name = pod.metadata.name
                print(f"\n=== Logs for pod {pod_name} ===")
                
                try:
                    if follow:
                        # Stream logs in follow mode
                        logs_stream = self.core_v1.read_namespaced_pod_log(
                            name=pod_name,
                            namespace=self.namespace,
                            follow=True,
                            _preload_content=False
                        )
                        for line in logs_stream:
                            print(line.decode('utf-8'), end='')
                    else:
                        logs = self.core_v1.read_namespaced_pod_log(
                            name=pod_name,
                            namespace=self.namespace
                        )
                        print(logs)
                    
                except Exception as e:
                    print(f"Error getting logs for pod {pod_name}: {e}")
                    
        except Exception as e:
            print(f"Error getting job logs: {e}")

    def delete_job(self, job_name: str, force: bool = False, rm_secrets: bool = False) -> None:
        """Delete a k8r job"""
        try:
            # Check if this is a k8r job
            try:
                job = self.batch_v1.read_namespaced_job(name=job_name, namespace=self.namespace)
                if not job.metadata.labels or job.metadata.labels.get("created-by") != "k8r":
                    print(f"Job '{job_name}' was not created by k8r")
                    return
            except Exception:
                print(f"Job '{job_name}' not found")
                return
            
            # Check if job has running pods
            pods = self.core_v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f"k8r-job={job_name},created-by=k8r"
            )
            
            running_pods = [pod for pod in pods.items if pod.status.phase == "Running"]
            
            if running_pods and not force:
                print(f"Warning: Job '{job_name}' has {len(running_pods)} running pods.")
                print("Use -f/--force to delete anyway.")
                return
            
            # Delete the job
            self.batch_v1.delete_namespaced_job(
                name=job_name,
                namespace=self.namespace,
                propagation_policy="Background"
            )
            
            # Delete associated configmap if it exists
            try:
                self.core_v1.delete_namespaced_config_map(
                    name=f"{job_name}-source",
                    namespace=self.namespace
                )
            except ApiException as e:
                if e.status != 404:
                    print(f"Warning: Could not delete configmap: {e}")
            
            # Delete associated secrets only if --rm-secrets flag is passed
            if rm_secrets:
                self.delete_job_secrets(job_name)
            else:
                # Count secrets for informational message
                try:
                    secrets = self.core_v1.list_namespaced_secret(
                        namespace=self.namespace,
                        label_selector=f"created-by=k8r,k8r-job={job_name}"
                    )
                    if secrets.items:
                        print(f"Note: {len(secrets.items)} associated secrets preserved. Use --rm-secrets to remove them.")
                except Exception:
                    pass  # Silently ignore secret listing errors
            
            print(f"Job '{job_name}' deleted")
            
        except ApiException as e:
            if e.status == 404:
                print(f"Job '{job_name}' not found")
            else:
                print(f"Error deleting job: {e}")

    def delete_job_secrets(self, job_name: str) -> None:
        """Delete all secrets associated with a job"""
        try:
            secrets = self.core_v1.list_namespaced_secret(
                namespace=self.namespace,
                label_selector=f"created-by=k8r,k8r-job={job_name}"
            )
            
            for secret in secrets.items:
                try:
                    self.core_v1.delete_namespaced_secret(
                        name=secret.metadata.name,
                        namespace=self.namespace
                    )
                    print(f"Deleted secret '{secret.metadata.name}'")
                except ApiException as e:
                    if e.status != 404:
                        print(f"Warning: Could not delete secret {secret.metadata.name}: {e}")
        except Exception as e:
            print(f"Warning: Error listing secrets for cleanup: {e}")

    def get_job_name_from_directory(self) -> str:
        """Get job name from current directory, preferring original working directory"""
        # Check if we have the original working directory from shell function
        original_pwd = os.environ.get('K8R_ORIGINAL_PWD')
        if original_pwd and os.path.isdir(original_pwd):
            return os.path.basename(original_pwd)
        return os.path.basename(os.getcwd())

    def get_job_secrets(self, job_name: str) -> List[Dict]:
        """Get all secrets associated with a job"""
        try:
            secrets = self.core_v1.list_namespaced_secret(
                namespace=self.namespace,
                label_selector=f"created-by=k8r,k8r-job={job_name}"
            )
            
            secret_list = []
            for secret in secrets.items:
                secret_name = secret.metadata.labels.get("k8r-secret", "")
                secret_list.append({
                    "name": secret.metadata.name,
                    "secret_name": secret_name,
                    "data_keys": list(secret.data.keys()) if secret.data else []
                })
            
            return secret_list
        except Exception as e:
            print(f"Warning: Error listing secrets for job {job_name}: {e}")
            return []

    def sanitize_k8s_name(self, name: str) -> str:
        """Sanitize a name to be compliant with Kubernetes RFC 1123 subdomain rules"""
        # Convert to lowercase
        name = name.lower()
        
        # Replace invalid characters with hyphens
        name = re.sub(r'[^a-z0-9.-]', '-', name)
        
        # Ensure it starts and ends with alphanumeric character
        name = re.sub(r'^[^a-z0-9]+', '', name)
        name = re.sub(r'[^a-z0-9]+$', '', name)
        
        # Collapse multiple consecutive hyphens/dots
        name = re.sub(r'[-\.]+', '-', name)
        
        # Ensure it's not empty and doesn't exceed length limits
        if not name:
            name = 'unnamed'
        
        return name

    def create_secret(self, secret_name: str, secret_value: str) -> None:
        """Create a Kubernetes secret with k8r labels"""
        job_name = self.get_job_name_from_directory()
        sanitized_secret_name = self.sanitize_k8s_name(secret_name)
        full_secret_name = f"{job_name}-{sanitized_secret_name}"
        
        # Prepare secret data
        secret_data = {}
        
        # Determine if secret_value is a file, directory, or string
        if os.path.isfile(secret_value):
            # Read file contents
            try:
                with open(secret_value, 'rb') as f:
                    content = f.read()
                # Use base64 encoding for binary data
                secret_data[secret_name] = base64.b64encode(content).decode('utf-8')
                print(f"Creating secret '{full_secret_name}' from file '{secret_value}'")
            except Exception as e:
                print(f"Error reading file {secret_value}: {e}")
                return
        elif os.path.isdir(secret_value):
            # Read all files in directory
            try:
                for root, dirs, files in os.walk(secret_value):
                    for file in files:
                        file_path = os.path.join(root, file)
                        # Use relative path from secret_value as key
                        relative_path = os.path.relpath(file_path, secret_value)
                        # Replace path separators with underscores for secret key
                        key = relative_path.replace(os.path.sep, '_').replace('/', '_')
                        
                        with open(file_path, 'rb') as f:
                            content = f.read()
                        secret_data[key] = base64.b64encode(content).decode('utf-8')
                
                print(f"Creating secret '{full_secret_name}' from directory '{secret_value}' with {len(secret_data)} files")
            except Exception as e:
                print(f"Error reading directory {secret_value}: {e}")
                return
        else:
            # Treat as string value
            secret_data[secret_name] = base64.b64encode(secret_value.encode('utf-8')).decode('utf-8')
            print(f"Creating secret '{full_secret_name}' with string value")
        
        # Create the secret
        secret = client.V1Secret(
            metadata=client.V1ObjectMeta(
                name=full_secret_name,
                labels={
                    "created-by": "k8r",
                    "k8r-job": job_name,
                    "k8r-secret": secret_name
                }
            ),
            data=secret_data,
            type="Opaque"
        )
        
        try:
            self.core_v1.create_namespaced_secret(
                namespace=self.namespace,
                body=secret
            )
            print(f"Secret '{full_secret_name}' created successfully")
        except ApiException as e:
            if e.status == 409:  # Already exists
                # Replace existing secret
                self.core_v1.replace_namespaced_secret(
                    name=full_secret_name,
                    namespace=self.namespace,
                    body=secret
                )
                print(f"Secret '{full_secret_name}' updated successfully")
            else:
                print(f"Error creating secret: {e}")
        except Exception as e:
            print(f"Error creating secret: {e}")
    
    def create_secret_with_options(self, secret_name: str, secret_value: str, 
                                 job_name: Optional[str] = None, show_yaml: bool = False) -> None:
        """Create a secret with additional options like custom job name and YAML output"""
        original_job_name = self.get_job_name_from_directory()
        
        # Use provided job name or fall back to directory-based name
        effective_job_name = job_name if job_name else original_job_name
        sanitized_secret_name = self.sanitize_k8s_name(secret_name)
        full_secret_name = f"{effective_job_name}-{sanitized_secret_name}"
        
        # Prepare secret data (same logic as original create_secret)
        secret_data = {}
        
        if os.path.isfile(secret_value):
            try:
                with open(secret_value, 'rb') as f:
                    content = f.read()
                secret_data[secret_name] = base64.b64encode(content).decode('utf-8')
                print(f"Creating secret '{full_secret_name}' from file '{secret_value}'")
            except Exception as e:
                print(f"Error reading file {secret_value}: {e}")
                return
        elif os.path.isdir(secret_value):
            try:
                for root, dirs, files in os.walk(secret_value):
                    for file in files:
                        file_path = os.path.join(root, file)
                        relative_path = os.path.relpath(file_path, secret_value)
                        key = relative_path.replace(os.path.sep, '_').replace('/', '_')
                        
                        with open(file_path, 'rb') as f:
                            content = f.read()
                        secret_data[key] = base64.b64encode(content).decode('utf-8')
                
                print(f"Creating secret '{full_secret_name}' from directory '{secret_value}' with {len(secret_data)} files")
            except Exception as e:
                print(f"Error reading directory {secret_value}: {e}")
                return
        else:
            secret_data[secret_name] = base64.b64encode(secret_value.encode('utf-8')).decode('utf-8')
            print(f"Creating secret '{full_secret_name}' with string value")
        
        # Create the secret object
        secret = client.V1Secret(
            metadata=client.V1ObjectMeta(
                name=full_secret_name,
                labels={
                    "created-by": "k8r",
                    "k8r-job": effective_job_name,
                    "k8r-secret": secret_name
                }
            ),
            data=secret_data,
            type="Opaque"
        )
        
        if show_yaml:
            # Convert to YAML and print
            secret_dict = client.ApiClient().sanitize_for_serialization(secret)
            secret_dict['apiVersion'] = 'v1'
            secret_dict['kind'] = 'Secret'
            print(yaml.dump(secret_dict, default_flow_style=False))
            return
        
        # Apply the secret
        try:
            self.core_v1.create_namespaced_secret(
                namespace=self.namespace,
                body=secret
            )
            print(f"Secret '{full_secret_name}' created successfully")
        except ApiException as e:
            if e.status == 409:
                self.core_v1.replace_namespaced_secret(
                    name=full_secret_name,
                    namespace=self.namespace,
                    body=secret
                )
                print(f"Secret '{full_secret_name}' updated successfully")
            else:
                print(f"Error creating secret: {e}")
        except Exception as e:
            print(f"Error creating secret: {e}")
    
    def run_job_with_options(self, source: str, command: List[str], num_instances: int = 1, 
                           timeout: str = "1h", base_image: str = "alpine:latest", 
                           job_name: Optional[str] = None, detach: bool = False,
                           show_yaml: bool = False, as_deployment: bool = False, retry_limit: Optional[int] = None, follow: bool = False) -> None:
        """Create and run a job with additional options"""
        
        if as_deployment:
            job_name = self.create_deployment(
                source=source, command=command, num_instances=num_instances,
                timeout=timeout, base_image=base_image, job_name=job_name,
                show_yaml=show_yaml
            )
            if not show_yaml:
                print(f"Deployment '{job_name}' created")
        else:
            job_name = self.create_job_with_yaml_option(
                source=source, command=command, num_instances=num_instances,
                timeout=timeout, base_image=base_image, job_name=job_name,
                show_yaml=show_yaml, retry_limit=retry_limit
            )
            if not show_yaml:
                self.monitor_job(job_name, detach)
                if follow and not detach:
                    self.get_job_logs(job_name, follow=True)
    
    def create_job_with_yaml_option(self, source: str, command: List[str], num_instances: int = 1, 
                                  timeout: str = "1h", base_image: str = "alpine:latest", 
                                  job_name: Optional[str] = None, show_yaml: bool = False, retry_limit: Optional[int] = None) -> str:
        """Create a job with option to output YAML instead of applying"""
        
        source_type = self.detect_source_type(source)
        final_job_name = self.generate_job_name(source, job_name)
        
        # Convert timeout to seconds
        timeout_seconds = self.parse_timeout(timeout)
        
        # Create job spec based on source type (same logic as original create_job)
        volumes = []
        if source_type == "directory":
            if not show_yaml:
                configmap_name = self.create_directory_configmap(source, final_job_name)
            else:
                configmap_name = f"{final_job_name}-source"
            container = self.create_directory_container(configmap_name, command, base_image)
            volumes = [
                client.V1Volume(
                    name="source",
                    config_map=client.V1ConfigMapVolumeSource(name=configmap_name)
                )
            ]
        elif source_type == "github":
            container = self.create_github_container(source, command, base_image)
        elif source_type == "dockerfile":
            if not show_yaml:
                image_name = self.build_and_push_dockerfile(source, final_job_name)
            else:
                image_name = f"registry/project/{final_job_name}:latest"
            container = self.create_container_container(image_name, command)
        elif source_type == "container":
            container = self.create_container_container(source, command)
        else:
            raise ValueError(f"Unsupported source type: {source_type}")
        
        # Handle secrets (skip for show_yaml mode to avoid side effects)
        secret_volumes = []
        secret_volume_mounts = []
        secret_env_vars = []
        
        # Get job secrets (even in show_yaml mode to demonstrate mounting)
        job_secrets = self.get_job_secrets(final_job_name) if not show_yaml else []
        
        # For show_yaml mode, try to get secrets anyway for demonstration
        if show_yaml and not job_secrets:
            try:
                job_secrets = self.get_job_secrets(final_job_name)
            except:
                pass  # Ignore errors in show_yaml mode
        
        if job_secrets:
            for secret_info in job_secrets:
                secret_name = secret_info["secret_name"]
                secret_k8s_name = secret_info["name"]
                
                sanitized_volume_name = f"secret-{self.sanitize_k8s_name(secret_name)}"
                secret_volumes.append(
                    client.V1Volume(
                        name=sanitized_volume_name,
                        secret=client.V1SecretVolumeSource(secret_name=secret_k8s_name)
                    )
                )
                
                # Add volume mounts for each secret key to avoid duplication
                for key in secret_info["data_keys"]:
                    secret_volume_mounts.append(
                        client.V1VolumeMount(
                            name=sanitized_volume_name,
                            mount_path=f"/k8r/secrets/{key}",
                            sub_path=key,
                            read_only=True
                        )
                    )
                
                for key in secret_info["data_keys"]:
                    env_var_name = key.upper().replace("-", "_").replace(".", "_")
                    secret_env_vars.append(
                        client.V1EnvVar(
                            name=env_var_name,
                            value_from=client.V1EnvVarSource(
                                secret_key_ref=client.V1SecretKeySelector(
                                    name=secret_k8s_name,
                                    key=key
                                )
                            )
                        )
                    )
            
            volumes.extend(secret_volumes)
            
            if hasattr(container, 'volume_mounts') and container.volume_mounts:
                container.volume_mounts.extend(secret_volume_mounts)
            else:
                container.volume_mounts = secret_volume_mounts
                
            if hasattr(container, 'env') and container.env:
                container.env.extend(secret_env_vars)
            else:
                container.env = secret_env_vars
            
            if job_secrets:
                print(f"Mounting {len(job_secrets)} secrets for job '{final_job_name}'")
        
        # Determine restart policy and backoff limit
        restart_policy = "OnFailure" if retry_limit is not None else "Never"
        
        # Create job spec with conditional backoff limit
        job_spec = client.V1JobSpec(
            parallelism=num_instances,
            completions=num_instances,
            active_deadline_seconds=timeout_seconds,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={
                        "created-by": "k8r",
                        "k8r-job": final_job_name
                    }
                ),
                spec=client.V1PodSpec(
                    containers=[container],
                    volumes=volumes,
                    restart_policy=restart_policy
                )
            )
        )
        
        # Set backoff limit if retry is specified
        if retry_limit is not None:
            job_spec.backoff_limit = retry_limit
            
        # Create job with k8r labels
        job = client.V1Job(
            metadata=client.V1ObjectMeta(
                name=final_job_name,
                labels={
                    "created-by": "k8r",
                    "k8r-source-type": source_type
                }
            ),
            spec=job_spec
        )
        
        if show_yaml:
            # Convert to YAML and print
            job_dict = client.ApiClient().sanitize_for_serialization(job)
            job_dict['apiVersion'] = 'batch/v1'
            job_dict['kind'] = 'Job'
            print(yaml.dump(job_dict, default_flow_style=False))
            return final_job_name
        
        # Apply the job
        self.batch_v1.create_namespaced_job(namespace=self.namespace, body=job)
        return final_job_name
    
    def create_deployment(self, source: str, command: List[str], num_instances: int = 1, 
                         timeout: str = "1h", base_image: str = "alpine:latest", 
                         job_name: Optional[str] = None, show_yaml: bool = False) -> str:
        """Create a Deployment instead of a Job"""
        
        source_type = self.detect_source_type(source)
        final_deployment_name = self.generate_job_name(source, job_name)
        
        # Create container spec (same logic as job creation)
        volumes = []
        if source_type == "directory":
            if not show_yaml:
                configmap_name = self.create_directory_configmap(source, final_deployment_name)
            else:
                configmap_name = f"{final_deployment_name}-source"
            container = self.create_directory_container(configmap_name, command, base_image)
            volumes = [
                client.V1Volume(
                    name="source",
                    config_map=client.V1ConfigMapVolumeSource(name=configmap_name)
                )
            ]
        elif source_type == "github":
            container = self.create_github_container(source, command, base_image)
        elif source_type == "dockerfile":
            if not show_yaml:
                image_name = self.build_and_push_dockerfile(source, final_deployment_name)
            else:
                image_name = f"registry/project/{final_deployment_name}:latest"
            container = self.create_container_container(image_name, command)
        elif source_type == "container":
            container = self.create_container_container(source, command)
        else:
            raise ValueError(f"Unsupported source type: {source_type}")
        
        # Handle secrets (skip for show_yaml mode)
        secret_volumes = []
        secret_volume_mounts = []
        secret_env_vars = []
        
        if not show_yaml:
            job_secrets = self.get_job_secrets(final_deployment_name)
            for secret_info in job_secrets:
                secret_name = secret_info["secret_name"]
                secret_k8s_name = secret_info["name"]
                
                sanitized_volume_name = f"secret-{self.sanitize_k8s_name(secret_name)}"
                secret_volumes.append(
                    client.V1Volume(
                        name=sanitized_volume_name,
                        secret=client.V1SecretVolumeSource(secret_name=secret_k8s_name)
                    )
                )
                
                # Add volume mounts for each secret key to avoid duplication
                for key in secret_info["data_keys"]:
                    secret_volume_mounts.append(
                        client.V1VolumeMount(
                            name=sanitized_volume_name,
                            mount_path=f"/k8r/secrets/{key}",
                            sub_path=key,
                            read_only=True
                        )
                    )
                
                for key in secret_info["data_keys"]:
                    env_var_name = key.upper().replace("-", "_").replace(".", "_")
                    secret_env_vars.append(
                        client.V1EnvVar(
                            name=env_var_name,
                            value_from=client.V1EnvVarSource(
                                secret_key_ref=client.V1SecretKeySelector(
                                    name=secret_k8s_name,
                                    key=key
                                )
                            )
                        )
                    )
            
            volumes.extend(secret_volumes)
            
            if hasattr(container, 'volume_mounts') and container.volume_mounts:
                container.volume_mounts.extend(secret_volume_mounts)
            else:
                container.volume_mounts = secret_volume_mounts
                
            if hasattr(container, 'env') and container.env:
                container.env.extend(secret_env_vars)
            else:
                container.env = secret_env_vars
        
        # Create deployment
        deployment = client.V1Deployment(
            metadata=client.V1ObjectMeta(
                name=final_deployment_name,
                labels={
                    "created-by": "k8r",
                    "k8r-source-type": source_type,
                    "k8r-type": "deployment"
                }
            ),
            spec=client.V1DeploymentSpec(
                replicas=num_instances,
                selector=client.V1LabelSelector(
                    match_labels={
                        "created-by": "k8r",
                        "k8r-deployment": final_deployment_name
                    }
                ),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(
                        labels={
                            "created-by": "k8r",
                            "k8r-deployment": final_deployment_name
                        }
                    ),
                    spec=client.V1PodSpec(
                        containers=[container],
                        volumes=volumes
                    )
                )
            )
        )
        
        if show_yaml:
            # Convert to YAML and print
            deployment_dict = client.ApiClient().sanitize_for_serialization(deployment)
            deployment_dict['apiVersion'] = 'apps/v1'
            deployment_dict['kind'] = 'Deployment'
            print(yaml.dump(deployment_dict, default_flow_style=False))
            return final_deployment_name
        
        # Apply the deployment
        apps_v1 = client.AppsV1Api()
        apps_v1.create_namespaced_deployment(namespace=self.namespace, body=deployment)
        return final_deployment_name



def update_k8r(branch: str = "main") -> None:
    """Update k8r installation to latest version of specified branch"""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    print(f"🔄 Updating k8r to latest '{branch}' branch...")
    
    try:
        # Check if we're in a git repository
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=script_dir,
            capture_output=True,
            text=True,
            check=True
        )
        
        # Get current branch and commit info before update
        current_branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=script_dir,
            capture_output=True,
            text=True,
            check=True
        )
        current_branch = current_branch_result.stdout.strip()
        
        # Fetch latest changes
        print(f"📥 Fetching latest changes...")
        subprocess.run(
            ["git", "fetch", "origin"],
            cwd=script_dir,
            check=True
        )
        
        # Check if target branch exists on remote
        remote_branch_check = subprocess.run(
            ["git", "ls-remote", "--heads", "origin", branch],
            cwd=script_dir,
            capture_output=True,
            text=True
        )
        
        if not remote_branch_check.stdout.strip():
            print(f"❌ Error: Branch '{branch}' does not exist on remote")
            print(f"💡 Available branches can be seen with: git branch -r")
            sys.exit(1)
        
        # Switch to the target branch if different from current
        if current_branch != branch:
            print(f"🔀 Switching from '{current_branch}' to '{branch}' branch...")
            try:
                subprocess.run(
                    ["git", "checkout", branch],
                    cwd=script_dir,
                    check=True
                )
            except subprocess.CalledProcessError:
                print(f"❌ Error: Could not switch to branch '{branch}'")
                print(f"💡 You may have uncommitted changes. Try: git stash")
                sys.exit(1)
        
        # Pull latest changes
        print(f"⬇️  Pulling latest changes from '{branch}'...")
        subprocess.run(
            ["git", "pull", "origin", branch],
            cwd=script_dir,
            check=True
        )
        
        # Get updated commit information
        commit_hash_result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=script_dir,
            capture_output=True,
            text=True,
            check=True
        )
        commit_hash = commit_hash_result.stdout.strip()
        
        commit_message_result = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%s"],
            cwd=script_dir,
            capture_output=True,
            text=True,
            check=True
        )
        commit_message = commit_message_result.stdout.strip()
        
        commit_date_result = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%cd", "--date=short"],
            cwd=script_dir,
            capture_output=True,
            text=True,
            check=True
        )
        commit_date = commit_date_result.stdout.strip()
        
        # Update dependencies if needed
        venv_dir = os.path.join(script_dir, ".venv")
        if os.path.exists(venv_dir):
            print(f"📦 Updating dependencies...")
            subprocess.run(
                ["uv", "sync"],
                cwd=script_dir,
                check=True
            )
        
        print(f"✅ Updated to {commit_hash} - {commit_message} ({commit_date})")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error updating k8r: {e}")
        print(f"💡 Make sure you're in a git repository and have network access")
        sys.exit(1)
    except FileNotFoundError:
        print(f"❌ Error: git command not found")
        print(f"💡 Please install git to use the update command")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error during update: {e}")
        sys.exit(1)


def print_env_setup():
    """Print shell function for k8r command (standalone function for bootstrap)"""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    setup_script = f'''# k8s-run (k8r) shell function
# Add this to your ~/.zshrc or ~/.bashrc

k8r() {{
    local k8r_dir="{script_dir}"
    local venv_dir="$k8r_dir/.venv"
    local original_pwd="$PWD"
    
    # Check if virtual environment exists
    if [ ! -d "$venv_dir" ]; then
        echo "Setting up k8r virtual environment..."
        (cd "$k8r_dir" && uv sync)
    fi
    
    # Activate venv and run k8r with original working directory
    (cd "$k8r_dir" && source .venv/bin/activate && K8R_ORIGINAL_PWD="$original_pwd" python k8r.py "$@")
}}
'''
    print(setup_script)


def main():
    # Main parser
    parser = argparse.ArgumentParser(
        description="k8s-run (k8r) - Run jobs in Kubernetes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  run       Create and run a Kubernetes job (default)
  ls        List k8r jobs
  logs      Show job logs  
  rm        Delete a job
  secret    Manage secrets
  update    Update k8r to latest version
  env       Print shell integration code

Examples:
  k8r run ./ --num 4 -- python my_script.py
  k8r redis:7.0 -- redis-server --version
  k8r ls
  k8r logs my-job
  k8r rm my-job
  k8r update
        """
    )
    
    # Add global options
    parser.add_argument("--namespace", help="Kubernetes namespace (overrides kubeconfig context)")
    
    # Create subparsers
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Run command (default)
    run_parser = subparsers.add_parser("run", help="Create and run a Kubernetes job")
    run_parser.add_argument("source", help="Source: directory, GitHub URL, Dockerfile, or container image")
    run_parser.add_argument("--num", type=int, default=1, help="Number of job instances")
    run_parser.add_argument("--timeout", default="1h", help="Job timeout (e.g., 1h, 30m, 3600s)")
    run_parser.add_argument("--base-image", default="alpine:latest", help="Base container image")
    run_parser.add_argument("--job-name", help="Override job name")
    run_parser.add_argument("-d", "--detach", action="store_true", help="Run in background")
    run_parser.add_argument("--show-yaml", action="store_true", help="Print YAML to stdout instead of applying")
    run_parser.add_argument("--as-deployment", action="store_true", help="Create as Deployment instead of Job")
    run_parser.add_argument("--retry", type=int, metavar="N", help="Set restart policy to OnFailure with backoff limit N (default: Never)")
    run_parser.add_argument("-f", "--follow", action="store_true", help="Follow logs after job starts")
    
    # List command
    ls_parser = subparsers.add_parser("ls", help="List k8r jobs")
    
    # Logs command
    logs_parser = subparsers.add_parser("logs", help="Show job logs")
    logs_parser.add_argument("job_name", help="Job name")
    logs_parser.add_argument("-f", "--follow", action="store_true", help="Follow logs")
    
    # Remove command
    rm_parser = subparsers.add_parser("rm", help="Delete a job")
    rm_parser.add_argument("job_name", help="Job name")
    rm_parser.add_argument("-f", "--force", action="store_true", help="Force delete")
    rm_parser.add_argument("--rm-secrets", action="store_true", help="Also remove associated secrets")
    
    # Secret command
    secret_parser = subparsers.add_parser("secret", help="Manage secrets")
    secret_parser.add_argument("secret_name", help="Secret name")
    secret_parser.add_argument("secret_value", help="Secret value (string, file path, or directory path)")
    secret_parser.add_argument("--job-name", help="Override job name for secret association")
    secret_parser.add_argument("--show-yaml", action="store_true", help="Print YAML to stdout instead of applying")
    
    # Update command
    update_parser = subparsers.add_parser("update", help="Update k8r to latest version")
    update_parser.add_argument("branch", nargs="?", default="main", help="Git branch to update to (default: main)")
    
    # Env command
    env_parser = subparsers.add_parser("env", help="Print shell integration code")
    
    # Look for -- separator to split k8r args from command args
    if "--" in sys.argv:
        sep_index = sys.argv.index("--")
        k8r_args = sys.argv[1:sep_index]
        command_args = sys.argv[sep_index + 1:]
    else:
        k8r_args = sys.argv[1:]
        command_args = []
    
    # Handle case where no subcommand is given but there are args - assume 'run'
    if k8r_args and k8r_args[0] not in ["run", "ls", "logs", "rm", "secret", "update", "env"] and not k8r_args[0].startswith("-"):
        k8r_args.insert(0, "run")
    
    # If no arguments provided, show help
    if not k8r_args:
        parser.print_help()
        return
    
    args = parser.parse_args(k8r_args)
    
    # Handle global namespace override
    namespace_override = args.namespace if hasattr(args, 'namespace') and args.namespace else None
    
    # Handle commands
    if args.command == "env":
        print_env_setup()
        return
    elif args.command == "update":
        update_k8r(args.branch)
        return
    
    # Initialize K8sRun with namespace override
    k8r = K8sRun()
    if namespace_override:
        k8r.namespace = namespace_override
    
    if args.command == "ls":
        k8r.list_jobs()
    elif args.command == "logs":
        k8r.get_job_logs(args.job_name, args.follow)
    elif args.command == "rm":
        k8r.delete_job(args.job_name, args.force, args.rm_secrets)
    elif args.command == "secret":
        k8r.create_secret_with_options(args.secret_name, args.secret_value, 
                                     job_name=args.job_name, show_yaml=args.show_yaml)
    elif args.command == "run" or args.command is None:
        # Handle run command
        command = command_args if command_args else ["echo", "No command specified"]
        k8r.run_job_with_options(
            source=args.source,
            command=command,
            num_instances=args.num,
            timeout=args.timeout,
            base_image=args.base_image,
            job_name=args.job_name,
            detach=args.detach,
            show_yaml=args.show_yaml,
            as_deployment=args.as_deployment,
            retry_limit=args.retry,
            follow=args.follow
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()