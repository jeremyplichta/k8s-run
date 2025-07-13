# Task Memory

**Created:** 2025-07-13 10:15:24
**Branch:** feature/add-k8s-resource

## Requirements

Add k8s resource args

## Development Notes

### Work Log

- [2025-07-13 10:15:24] Task setup completed, TASK_MEMORY.md created
- [2025-07-13 10:30:00] ✅ Implemented CPU and memory resource arguments
- [2025-07-13 10:35:00] ✅ Added argument parsing for --mem and --cpu flags
- [2025-07-13 10:40:00] ✅ Implemented resource specification logic in both job and deployment creation
- [2025-07-13 10:45:00] ✅ Tested various resource formats (single values, ranges, different units)
- [2025-07-13 10:50:00] ✅ Updated documentation with resource management examples

### Key Features Implemented

**Resource Arguments:**
- `--mem`: Memory request/limit specification
  - Single value: `--mem 8gb` (sets both requests and limits to 8gb)
  - Range format: `--mem 2gb-8gb` (sets requests to 2gb, limits to 8gb)
- `--cpu`: CPU request/limit specification
  - Supports millicores: `--cpu 1000m` 
  - Supports decimal: `--cpu 1`, `--cpu 0.5`
  - Range format: `--cpu 500m-2000m`, `--cpu 0.5-2`

**Implementation Details:**
- Added `parse_resource_spec()` method to parse resource specifications
- Updated both job and deployment creation paths with resource specifications
- Resources are properly added to Kubernetes V1ResourceRequirements
- Works with all source types (directory, GitHub, Dockerfile, container)

### Files Modified

1. **k8r.py** - Main implementation
   - Added argument parsing for --mem and --cpu
   - Implemented parse_resource_spec() method
   - Updated method signatures for run_job_with_options, create_job_with_yaml_option, create_deployment
   - Added resource specification logic in both job and deployment creation

2. **README.md** - Documentation updates
   - Added --mem and --cpu to the options table
   - Updated real-world examples to include resource specifications
   - Added dedicated "Resource Management" section with comprehensive examples
   - Added resource formats documentation

### Testing Results

All resource formats tested successfully:
- ✅ Single values: `--mem 8gb --cpu 1000m`
- ✅ Range format: `--mem 2gb-8gb --cpu 500m-2000m`
- ✅ Decimal CPU: `--cpu 0.5-2`
- ✅ Integer CPU: `--cpu 1`
- ✅ Different memory units: `--mem 4gi`, `--mem 512mi`
- ✅ Job creation with resources
- ✅ Deployment creation with resources
- ✅ YAML generation shows correct resource specifications

### Recent Work - Secret Job Reference Feature

- [2025-07-13 11:15:00] ✅ Implemented `--secret-job` option for custom secret job name reference  
- [2025-07-13 11:20:00] ✅ Updated secret mounting logic to use custom job name for secret discovery
- [2025-07-13 11:25:00] ✅ Added support for both Jobs and Deployments
- [2025-07-13 11:30:00] ✅ Added informative output when mounting secrets from different job names
- [2025-07-13 11:35:00] ✅ Tested functionality with YAML generation and secret discovery

**Secret Job Reference Feature:**
- `--secret-job`: Allows specifying a different job name for secret discovery
  - Example: `k8r alpine:latest --job-name new-job --secret-job existing-job -- echo "test"`
  - Mounts secrets from `existing-job` into the new job `new-job`
  - Enables sharing secrets between jobs without duplicating them
  - Works with both Jobs and Deployments
  - Gracefully handles non-existent secret job names (no secrets mounted)

**Implementation Details:**
- Added `secret_job_name` parameter to core methods: `create_job()`, `create_job_with_yaml_option()`, `create_deployment()`, `run_job_with_options()`
- Updated secret discovery logic to use `secret_job_name` when provided, falling back to actual job name
- Enhanced user feedback to show when secrets are being mounted from a different job
- Maintains backward compatibility - existing behavior unchanged when option not used

**Files Modified:**
1. **k8r.py** - Core implementation
   - Added `--secret-job` CLI argument parsing
   - Updated method signatures to accept `secret_job_name` parameter
   - Modified secret discovery logic in `get_job_secrets()` calls
   - Enhanced output messages for cross-job secret mounting

**Testing Results:**
- ✅ CLI argument shows up in help output
- ✅ YAML generation shows correct secret mounting from different job
- ✅ Graceful handling of non-existent secret job names
- ✅ Compatible with both Jobs and Deployments
- ✅ Backward compatibility maintained

### Additional Fix - Secret Mounting in YAML Mode

- [2025-07-13 11:45:00] 🐛 **Issue Discovered**: Secrets were not being mounted in --show-yaml mode for deployments
- [2025-07-13 11:50:00] ✅ **Fixed**: Updated both job and deployment creation to always include secrets in YAML output
- [2025-07-13 11:55:00] ✅ **Enhanced**: Added informative warning messages when secrets are included in YAML
- [2025-07-13 12:00:00] ✅ **Tested**: Verified secret mounting works correctly in all modes

**YAML Mode Secret Behavior:**
- Secrets are now always discovered and included in YAML output
- Warning message displayed: `⚠️ YAML includes N secrets from job 'job-name' - these secrets must exist when applying this YAML`
- Helps users understand dependency requirements when applying generated YAML later
- Works for both regular job secrets and cross-job secret references via `--secret-job`

**Implementation Details:**
- Removed `if not show_yaml:` conditions that were preventing secret discovery
- Unified secret handling logic between jobs and deployments
- Added conditional warning messages for YAML mode vs execution mode
- Maintained all existing functionality while improving YAML generation

**Updated Testing Results:**
- ✅ YAML mode includes secrets for both Jobs and Deployments  
- ✅ Warning messages display correctly in YAML mode
- ✅ Normal execution shows mounting messages (not warnings)
- ✅ Cross-job secret references work in all modes
- ✅ No secrets case handled gracefully

### Critical Fix - YAML Parsing Error with Secret Warnings

- [2025-07-13 15:00:00] 🐛 **Issue Discovered**: YAML parsing failed when secrets were included due to warning messages being printed to stdout
- [2025-07-13 15:15:00] ✅ **Root Cause**: Warning messages like `⚠️ YAML includes N secrets from job 'job-name'` were being printed to stdout, contaminating the YAML output
- [2025-07-13 15:20:00] ✅ **Fixed**: Modified all secret warning print statements to use `file=sys.stderr` instead of stdout
- [2025-07-13 15:25:00] ✅ **Tested**: Verified YAML output is now clean and valid, warnings appear on stderr

**The Problem:**
- When using `--show-yaml` with secrets, warning messages were printed to stdout along with the YAML
- This caused `kubectl apply` to fail with "mapping values are not allowed in this context" error
- Error occurred at line 2 because the warning message appeared before the actual YAML content

**The Fix:**
- Changed four print statements in k8r.py:1050, 1052, 1232, and 1234 to use `file=sys.stderr`
- This ensures warning messages go to stderr while clean YAML goes to stdout
- Maintains the informative warnings while fixing the parsing issue

**Files Modified:**
1. **k8r.py** - Lines 1050, 1052, 1232, 1234
   - Added `file=sys.stderr` parameter to all secret warning print statements
   - Preserved warning functionality while fixing YAML output contamination

**Testing Results:**
- ✅ YAML output is now clean and parseable by kubectl
- ✅ Warning messages still appear on stderr for user awareness
- ✅ Both Jobs and Deployments work correctly with secrets in YAML mode
- ✅ `kubectl apply --dry-run=client` validates generated YAML successfully

### Critical Fix - Resource Quantity Format Error

- [2025-07-13 16:00:00] 🐛 **Issue Discovered**: Kubernetes rejected deployments with invalid quantity format `memory: 12gb`
- [2025-07-13 16:10:00] ✅ **Root Cause**: The `parse_resource_spec()` function was returning raw values like "12gb" instead of Kubernetes-compatible formats
- [2025-07-13 16:15:00] ✅ **Kubernetes Requirements**: Memory quantities must use formats like "12Gi" (gibibytes) or "12G" (gigabytes), not "12gb"
- [2025-07-13 16:20:00] ✅ **Fixed**: Enhanced `parse_resource_spec()` with `normalize_quantity()` function to convert formats automatically
- [2025-07-13 16:25:00] ✅ **Tested**: Verified fix with kubectl dry-run validation

**The Problem:**
- Error: `quantities must match the regular expression '^([+-]?[0-9.]+)([eEinumkKMGTP]*[-+]?[0-9]*)$'`
- User-friendly formats like "12gb" were being passed directly to Kubernetes
- Kubernetes requires specific unit suffixes: Gi, Mi, G, M, etc.

**The Fix:**
- Added `normalize_quantity()` helper function inside `parse_resource_spec()`
- Converts "gb" → "Gi" (gibibytes) for proper Kubernetes format
- Converts "mb" → "Mi" (mebibytes) for proper Kubernetes format  
- Keeps other valid formats unchanged (m, G, M, etc.)
- Applied to both single values and range specifications

**Files Modified:**
1. **k8r.py:76-101** - Enhanced `parse_resource_spec()` method
   - Added nested `normalize_quantity()` function
   - Automatic format conversion for user-friendly input
   - Maintains backward compatibility with existing formats

**Testing Results:**
- ✅ `--mem 12gb` now generates `memory: 12Gi` in YAML output
- ✅ `kubectl apply --dry-run=client` validates successfully  
- ✅ Both Jobs and Deployments work with normalized quantities
- ✅ Range formats work: `--mem 2gb-8gb` → requests: 2Gi, limits: 8Gi
- ✅ Other formats preserved: `--cpu 1000m` unchanged

---

*This file serves as your working memory for this task. Keep it updated as you progress through the implementation.*
