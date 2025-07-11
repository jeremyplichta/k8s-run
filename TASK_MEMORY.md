# Task Memory

**Created:** 2025-07-11 17:43:43
**Branch:** feature/feature-secret-management

## Requirements

# Feature: secret management

## Overview
k8s-run (k8r) should be updated to be aware of kubernetes secrets and make it easy to setup a secret for your job. This would make it easy to both create a secret and reference secrets in Jobs.

## Requirements
- [ ] Add new command `k8r secret secret-name secret-value`
- [ ] secret-value can be a string or the name of a file (use the contents of the file) or as a directory (create a sub secret for each file)
- [ ] The name of the secret should be prepended with the job name. So if current directory is riotx and you run `k8r secret pass foobar` you would get a secret created called `riotx-pass`
- [ ] Secrets should be labeled as being managed by k8r and any searching creating or deleting should be restricted on this label
- [ ] When jobs are launched it should check if there are any secrets for that job (by looking at job name pattern for matching secrets) and if so mount those secrets as environment variables (upper case secret names) and as files in /k8r/secret/secret-name
- [ ] Deleting a job should also delete its secrets

## Development Notes

*Update this section as you work on the task. Include:*
- *Progress updates*
- *Key decisions made*
- *Challenges encountered*
- *Solutions implemented*
- *Files modified*
- *Testing notes*

### Work Log

- [2025-07-11 17:43:43] Task setup completed, TASK_MEMORY.md created

---

*This file serves as your working memory for this task. Keep it updated as you progress through the implementation.*
