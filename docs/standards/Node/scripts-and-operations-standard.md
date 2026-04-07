# Scripts And Operations Standard

Last Updated: 2026-04-04 US/Pacific

## Purpose

This document defines the scripts and operations standard for Hexe nodes.

The goal is to make node repositories operationally predictable for:

- development
- local startup
- service installation
- restart and status control
- operator handoff

## Rule Levels

- **Mandatory**
  Every Hexe node must satisfy these rules.
- **Recommended**
  Strong guidance that should usually be followed.
- **Optional**
  Acceptable patterns that may be used when helpful.

## Core Principle

The scripts and operations standard prioritizes:

- predictable startup behavior
- explicit service ownership
- environment-driven configuration
- consistent operational entrypoints

It does not require every node to ship every helper script imaginable.

It does require a consistent operational baseline.

## 1. Required Script Categories

### Mandatory

Every node repository must provide a minimum operational script baseline covering:

- bootstrap or service installation
- environment-driven runtime startup
- stack control or service control
- stack restart
- example environment configuration
- user-service templates when the node supports service installation

### Recommended

The minimum baseline should usually include:

- `bootstrap.sh`
- `run-from-env.sh`
- `stack-control.sh`
- `restart-stack.sh`
- `stack.env.example`
- service templates under `scripts/systemd/`

## 2. Script Location And Naming

### Mandatory

Operational scripts must be grouped in a predictable repo-local location.

### Recommended

Use:

- `scripts/` for operational scripts
- `scripts/systemd/` for user-service templates

### Recommended

Script names should communicate one clear purpose each.

Avoid vague names for core operational entrypoints.

## 3. Environment-Driven Startup

### Mandatory

Node startup commands must be externally configurable through environment-backed configuration rather than hardcoded only in service templates.

### Mandatory

Backend and frontend startup must be controllable without editing service templates directly.

### Recommended

Use a stack environment file pattern such as:

- `stack.env.example`
- `stack.env`

to define:

- backend command
- frontend command
- optional runtime paths
- optional log paths

## 4. Bootstrap And Service Installation

### Mandatory

If the node supports local service installation, it must provide one clear bootstrap entrypoint for installing its runtime services.

### Mandatory

Bootstrap behavior must be explicit about:

- what services are installed
- where service files are rendered
- what environment file is used
- what service names are started or enabled

### Recommended

Bootstrap should install user-level services instead of assuming system-wide root-managed services unless the node explicitly documents a different model.

## 5. Systemd Template Expectations

### Mandatory

If systemd templates are provided, backend and frontend services must be clearly separated when they are separate processes.

### Mandatory

Service templates must not hardcode machine-specific commands that cannot be changed through environment or documented configuration.

### Recommended

Service template naming should stay predictable and clearly tied to the node runtime components.

Use node-specific template filenames such as:

- `<node-name>-backend.service.in`
- `<node-name>-frontend.service.in`

## 6. Stack Control And Restart Behavior

### Mandatory

Nodes must provide a clear operational way to:

- start services
- stop services
- restart services
- inspect service status

### Recommended

Use:

- `stack-control.sh`
- `restart-stack.sh`

and optionally:

- `status.sh`

to keep these actions obvious and repeatable.

### Mandatory

Restart behavior must be explicit and must not rely on undocumented manual steps.

## 7. Development And Local Run Helpers

### Optional

Nodes may also provide helper scripts such as:

- `dev.sh`
- `start.sh`
- `ui-dev.sh`
- runtime reset helpers
- acceptance helpers

### Recommended

These helpers should build on the same operational model rather than inventing parallel ad hoc startup conventions.

## 8. Logging And Output Expectations

### Mandatory

Operational scripts must provide readable output about what they are doing.

### Mandatory

Failure conditions must be visible and actionable.

Scripts must not fail silently.

### Recommended

Bootstrap and control scripts should state:

- what file or service they are acting on
- what environment source they are using
- what the next operator step is when setup is incomplete

## 9. Runtime Ownership Visibility

### Mandatory

The operational surface must make it clear which runtime processes belong to the node.

This includes, where applicable:

- backend service
- frontend service
- supporting background processes

### Recommended

Documentation and scripts should use consistent names for these runtime units.

## 10. Safe Operational Boundaries

### Mandatory

Operational scripts must avoid hidden destructive behavior.

Reset or cleanup actions must be explicit and clearly separated from normal start or restart behavior.

### Recommended

Runtime reset helpers should exist only as clearly named, operator-intentional scripts.

## 11. Documentation Expectations

### Mandatory

Each node repository must document:

- how to configure the runtime
- how to start the backend
- how to start the frontend
- how to install services if supported
- how to restart and inspect service state

### Recommended

Repo docs should reference the script names directly so new developers and operators do not have to infer the operational entrypoints.

## 12. Compatibility And Growth

### Mandatory

New nodes should start with the standard operational baseline rather than inventing a new operational structure per repository.

### Recommended

As nodes grow, helper scripts may be added, but the baseline operational entrypoints should remain stable.

## 13. Non-Compliance Signals

The node should be considered out of standard if:

- startup commands are only embedded in service templates
- there is no clear bootstrap or service-install path when services are supported
- restart behavior requires undocumented manual steps
- backend and frontend ownership are unclear
- scripts fail silently or with unclear output
- operational behavior depends on hidden machine-specific assumptions

## 14. Formal Compliance Checklist

Use this checklist during new-node design or standards review:

A node follows this standard when:

- it has the minimum operational script baseline
- startup is environment-driven
- service installation behavior is explicit when supported
- backend and frontend service ownership are clear
- restart and status actions are predictable
- scripts are readable and actionable
- repo docs point to the operational entrypoints clearly
