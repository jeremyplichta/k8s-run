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
                   job_name: Optional[str] = None) -> str:
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
        
        # Create job with k8r labels
        job = client.V1Job(
            metadata=client.V1ObjectMeta(
                name=final_job_name,
                labels={
                    "created-by": "k8r",
                    "k8r-source-type": source_type
                }
            ),
            spec=client.V1JobSpec(
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
                        restart_policy="Never"
                    )
                )
            )
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
        
        # Properly escape and join the command
        command_str = " ".join(f"'{arg}'" if " " in arg else arg for arg in command)
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
        
        full_command = ["sh", "-c", init_script + " && " + " ".join(command)]
        
        return client.V1Container(
            name="runner",
            image=base_image,
            command=full_command,
            working_dir="/workspace"
        )

    def create_container_container(self, image: str, command: List[str]):
        """Create container spec for container mode"""
        return client.V1Container(
            name="runner",
            image=image,
            command=command if command else None
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
                        # For follow mode, we'd need to implement streaming
                        logs = self.core_v1.read_namespaced_pod_log(
                            name=pod_name,
                            namespace=self.namespace,
                            follow=False
                        )
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

    def delete_job(self, job_name: str, force: bool = False) -> None:
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
            
            print(f"Job '{job_name}' deleted")
            
        except ApiException as e:
            if e.status == 404:
                print(f"Job '{job_name}' not found")
            else:
                print(f"Error deleting job: {e}")



def print_env_setup():
    """Print shell function for k8r command (standalone function for bootstrap)"""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    setup_script = f'''# k8s-run (k8r) shell function
# Add this to your ~/.zshrc or ~/.bashrc

k8r() {{
    local k8r_dir="{script_dir}"
    local venv_dir="$k8r_dir/.venv"
    
    # Check if virtual environment exists
    if [ ! -d "$venv_dir" ]; then
        echo "Setting up k8r virtual environment..."
        (cd "$k8r_dir" && uv sync)
    fi
    
    # Activate venv and run k8r
    (cd "$k8r_dir" && source .venv/bin/activate && python k8r.py "$@")
}}
'''
    print(setup_script)


def main():
    # Check if first argument is a known subcommand
    subcommands = ["ls", "logs", "rm", "env"]
    
    if len(sys.argv) > 1 and sys.argv[1] in subcommands:
        # Handle subcommands
        if sys.argv[1] == "env":
            print_env_setup()
            return
        elif sys.argv[1] == "ls":
            k8r = K8sRun()
            k8r.list_jobs()
            return
        elif sys.argv[1] == "logs":
            parser = argparse.ArgumentParser(description="Show job logs")
            parser.add_argument("job_name", help="Job name")
            parser.add_argument("-f", "--follow", action="store_true", help="Follow logs")
            args = parser.parse_args(sys.argv[2:])
            k8r = K8sRun()
            k8r.get_job_logs(args.job_name, args.follow)
            return
        elif sys.argv[1] == "rm":
            parser = argparse.ArgumentParser(description="Delete job")
            parser.add_argument("job_name", help="Job name")
            parser.add_argument("-f", "--force", action="store_true", help="Force delete")
            args = parser.parse_args(sys.argv[2:])
            k8r = K8sRun()
            k8r.delete_job(args.job_name, args.force)
            return
    
    # Handle main run command
    parser = argparse.ArgumentParser(description="k8s-run (k8r) - Run jobs in Kubernetes")
    parser.add_argument("source", help="Source: directory, GitHub URL, Dockerfile, or container image")
    parser.add_argument("--num", type=int, default=1, help="Number of job instances")
    parser.add_argument("--timeout", default="1h", help="Job timeout (e.g., 1h, 30m, 3600s)")
    parser.add_argument("--base-image", default="alpine:latest", help="Base container image")
    parser.add_argument("--job-name", help="Override job name")
    parser.add_argument("-d", "--detach", action="store_true", help="Run in background")
    
    # Look for -- separator to split k8r args from command args
    if "--" in sys.argv:
        sep_index = sys.argv.index("--")
        k8r_args = sys.argv[1:sep_index]
        command_args = sys.argv[sep_index + 1:]
    else:
        k8r_args = sys.argv[1:]
        command_args = []
    
    # If no arguments provided, show help
    if not k8r_args:
        parser.print_help()
        print(f"\nAvailable subcommands: {', '.join(subcommands)}")
        return
    
    args = parser.parse_args(k8r_args)
    
    # Initialize K8sRun and create job
    k8r = K8sRun()
    
    command = command_args if command_args else ["echo", "No command specified"]
    job_name = k8r.create_job(
        source=args.source,
        command=command,
        num_instances=args.num,
        timeout=args.timeout,
        base_image=args.base_image,
        job_name=args.job_name
    )
    k8r.monitor_job(job_name, args.detach)


if __name__ == "__main__":
    main()