# Task Memory

**Created:** 2025-07-11 14:46:30
**Branch:** feature/k8s-run

## Requirements

# K8s Run 

# Overview
Implement a minimal self contained project called k8s-run or `k8r` for short. This tool is meant to make it easy to spin K8s Jobs to run a local project or directory. It can with multiple sources including:

 - A local directory (in that case the files will be tar gz'd to a local directory) then will be added to a k8s configmap that can be referenced and mounted
   - In this mode if there is a file called k8s-startup.sh that will run on container startup to setup the prereqs
 - A github url, in that case the directory will be cloned and will be the pwd of the container that starts up
 - A Dockerfile, in that case it will build an image and push it to a docker registry (by default GCP GCR) but that can be controlled with a CLI flag.
 - A container instance like redis:8.0.0 or riotx/riot:v4.1.3

# Additional requirements
 - You can specify the number of instances of the job to launch
 - It will wait until all jobs are complete and it will monitor the jobs at a certain interval and report if some have failed
 - It will have a default job timeout of 1 hour but that can be overriden with a command line flag
 - By default for directory or github mode it will use a minimal image like alpine as the base, but you can change the base container
 - The arguments at the end will be the command to run in the K8s job once the configmap or github url is expanded to local directory in the Pod and the startup script is run
    - ex usage: k8r ./ --num 8 --timeout 3h -- python run_script.py --some-other-option --etc foo
    - ex usage: k8r git@github.com:abrookins/multi-claude.git --num 2 -- python mcl.py
    - ex usage: k8r Dockerfile -- pyrhon run_scirpt.py
 - It will use the job name based on the current directory name or github name but can be override with --job-name
 - If there is already a job that exists with that name it will use job-name-(increment number)
 - It will print out a message that says the name of the job it started and will monitor and print output about status changing
 - You can launch it in the background so it doesnt stay waiting with -d
 - It will allow you to run other commands like 
  - ls (to list current jobs)
    - `k8r ls` would output
   
   ```
    job name     | desired | running | complete | complete )
    ========================================================
    job-name     | 8       | 7       | 1        | 0         
    multi-claude | 2       | 2       | 0        | 0
   ```
 - logs <job-name> [-f]
   - Will print out the logs for all the pods for that job or run a tail on them. ctrl-c to stop in tail mode
 - rm <job-name> will remove the Job definition from k8s and any pods not running. If there are running pods it will warn and say you can do it again with -f to force
 - env will print out the necessary bash or zsrc function for you to get the `k8r` functionality. Output of this meant to be concattenated to end of your ~/.zshrc, etc
 - Implementation will be minimal and easy to understand and self contained in a file k8r.py (it can use common and well known python dependencies)
 - Python dependencies and packaging will use `uv` and pyproject.toml 
 - The README.md will describe the purpose of this tool, a quick installation and getting started guide, as well as more advanced options and examples of using it.

## Development Notes

*Update this section as you work on the task. Include:*
- *Progress updates*
- *Key decisions made*
- *Challenges encountered*
- *Solutions implemented*
- *Files modified*
- *Testing notes*

### Work Log

- [2025-07-11 14:46:30] Task setup completed, TASK_MEMORY.md created

---

*This file serves as your working memory for this task. Keep it updated as you progress through the implementation.*
