---
name: agents_cli_create
description: Create or scaffold a new AI agent project using the agents-cli tool.
---

# Agent Creation with agents-cli

This skill guides the agent on how to use `agents-cli` to create and scaffold new AI agent projects.

## Instructions

1. **Verify CLI availability**: Check if `agents-cli` is installed by running `agents-cli --version` or checking help.
2. **Creation Modes**:
   - **Quickstart/Prototype Mode**: Use `agents-cli create <project-name> --adk` to bypass prompts and use standard defaults (ADK + Agent Runtime + Prototype).
   - **Interactive Mode**: Use `agents-cli create <project-name> -i` to prompt the user for database, templates, and deployment targets.
3. **Execution Guidelines**:
   - Always run the command from the user's workspace directory.
   - Wait for the command to finish, then verify that files like `pyproject.toml`, `agents-cli-manifest.yaml`, and `app/` directory are created.
4. **Post-Scaffold Verification**:
   - Show the user the next steps to get started: running `agents-cli install` and `agents-cli playground` to run local tests.
