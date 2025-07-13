# Task Memory

**Created:** 2025-07-13 10:15:24  
**Branch:** feature/add-k8s-resource

## Completed Features

### 1. Resource Arguments (`--mem`, `--cpu`)
**Purpose:** Added CPU and memory resource specification for Jobs and Deployments

**Key Implementation:**
- `parse_resource_spec()` method with `normalize_quantity()` helper
- Supports single values: `--mem 8gb --cpu 1000m`
- Supports ranges: `--mem 2gb-8gb --cpu 500m-2000m`
- Auto-converts "gb"→"Gi", "mb"→"Mi" for Kubernetes compatibility

**Files Modified:** k8r.py (argument parsing, resource logic), README.md (documentation)

### 2. Secret Job Reference (`--secret-job`)
**Purpose:** Allow jobs to reference secrets from other jobs without duplication

**Key Implementation:**
- `--secret-job` option to specify different job name for secret discovery
- Example: `k8r alpine:latest --job-name new-job --secret-job existing-job`
- Works with both Jobs and Deployments, graceful fallback for non-existent refs

**Files Modified:** k8r.py (CLI parsing, secret discovery logic)

### 3. Critical Fixes

#### YAML Secret Warnings (stdout contamination)
**Problem:** Warning messages printed to stdout broke `kubectl apply`  
**Fix:** Changed secret warning prints to use `file=sys.stderr`

#### Resource Quantity Format  
**Problem:** "12gb" format rejected by Kubernetes validation  
**Fix:** Auto-normalize to "12Gi" in `parse_resource_spec()`

#### Name Length Limits (63 chars)
**Problem:** Long deployment names exceeded Kubernetes limit  
**Fix:** Enhanced `sanitize_k8s_name()` with truncation, limited base names to 55 chars
- Jobs/Deployments: max 55 chars (allows suffixes like "-source")
- Secrets: dynamic calculation based on job name length
- Volumes: max 56 chars for secret names (allows "secret-" prefix)

## Testing Status
- ✅ All resource formats (single, range, different units)
- ✅ Secret mounting in all modes (execution, YAML, cross-job references)
- ✅ Clean YAML output with warnings on stderr
- ✅ Kubernetes validation passes for all generated resources
- ✅ Name truncation works for all resource types

## Files Modified
1. **k8r.py** - Core implementation (resource parsing, secret logic, name sanitization)
2. **README.md** - Documentation updates

---

*This file serves as your working memory for this task. Keep it updated as you progress through the implementation.*