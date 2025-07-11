# Task Memory

**Created:** 2025-07-11 19:16:49
**Branch:** feature/args-clarity

## Requirements

# args clarity

## Description
The help output of k8r.py is kinda confusing right now

```
usage: k8r.py [-h] [--num NUM] [--timeout TIMEOUT] [--base-image BASE_IMAGE] [--job-name JOB_NAME] [-d] source

k8s-run (k8r) - Run jobs in Kubernetes

positional arguments:
  source                Source: directory, GitHub URL, Dockerfile, or container image

options:
  -h, --help            show this help message and exit
  --num NUM             Number of job instances
  --timeout TIMEOUT     Job timeout (e.g., 1h, 30m, 3600s)
  --base-image BASE_IMAGE
                        Base container image
  --job-name JOB_NAME   Override job name
  -d, --detach          Run in background
```

In addition to arg clarity there are a few extra features at the end to implement

## Tasks
- [ ] Refactor it so that the help text clearly shows the main command types (ls rm secret) etc
- [ ] The default command type is to launch something, but maybe it should be called "run", if you dont specify a command it assumes run
- [ ] Each command can have different args (the ones that make sense. Some of them are common (like --job-name
- [ ] You should be able to get different help output and detailed help if you run k8r run -h vs k8r -h vs k8r secret -h etc
- [ ] k8r secret sould support --job-name
- [ ] The default job name should still work - right now since the k8r wrapper first cds and then runs the command it looses the original directory. You can fix this in the python script or the k8r shell function, whatever is more clear
- [ ] Make sure the README reflects the same options as the -h and vice versa
- [ ] Allow kubernetes namespace to be specified for all commands, otherwise use default namespace
- [ ] Add a --show-yaml option for the run and secret commands that will print the kubernetes yaml to stdout instead of actually applying and running it
- [ ] Add a --as-deployment option to run which will allow it to create it as a Deployment instead of a job (you may also need to adjust the other commands for this like ls logs rm etc)

## Development Notes

*Update this section as you work on the task. Include:*
- *Progress updates*
- *Key decisions made*
- *Challenges encountered*
- *Solutions implemented*
- *Files modified*
- *Testing notes*

### Work Log

- [2025-07-11 19:16:49] Task setup completed, TASK_MEMORY.md created
- [2025-07-12] Refactored main() function to use argparse subparsers for better command organization
- [2025-07-12] Implemented "run" as default command when no subcommand is specified
- [2025-07-12] Added --namespace option to all commands with global support
- [2025-07-12] Added --show-yaml option for run and secret commands
- [2025-07-12] Added --as-deployment option for run command to create Deployments instead of Jobs
- [2025-07-12] Fixed job name generation to preserve original directory context via K8R_ORIGINAL_PWD env var
- [2025-07-12] Added --job-name support to secret command
- [2025-07-12] Updated shell function in print_env_setup() to preserve original working directory
- [2025-07-12] Updated README.md with new command structure, examples, and feature documentation
- [2025-07-12] All tasks completed successfully - refactoring provides much clearer help output and better UX
- [2025-07-12] Added 'update' command for self-updating k8r installations with branch switching support

### Key Implementation Details

1. **Subcommand Structure**: Used argparse subparsers to organize commands (run, ls, logs, rm, secret, update, env)
2. **Backward Compatibility**: Maintained compatibility by automatically inserting "run" when first arg is not a known subcommand
3. **Directory Context Fix**: Modified shell function to pass K8R_ORIGINAL_PWD environment variable
4. **New Methods Added**:
   - `create_secret_with_options()` - supports --job-name and --show-yaml
   - `run_job_with_options()` - main entry point for run command
   - `create_job_with_yaml_option()` - job creation with YAML output support
   - `create_deployment()` - deployment creation instead of jobs
   - `update_k8r()` - self-updating functionality with git operations
5. **Global Options**: --namespace can be specified at the top level and applies to all commands

---

*This file serves as your working memory for this task. Keep it updated as you progress through the implementation.*
