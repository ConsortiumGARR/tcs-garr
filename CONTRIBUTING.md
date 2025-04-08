# Contributing to TCS-GARR Client

Thank you for considering contributing to TCS-GARR Client! We're excited to have you. This guide will help you get started with the contribution process.

## Table of Contents

- [Contributing to TCS-GARR Client](#contributing-to-tcs-garr-client)
  - [Table of Contents](#table-of-contents)
  - [How to Contribute](#how-to-contribute)
    - [Reporting Bugs](#reporting-bugs)
    - [Suggesting Features](#suggesting-features)
    - [Submitting Code Changes](#submitting-code-changes)
  - [Development Environment Setup](#development-environment-setup)
    - [Prerequisites](#prerequisites)
    - [Installing Poetry](#installing-poetry)
    - [Installing Dependencies](#installing-dependencies)
  - [Style Guide](#style-guide)
  - [Pre-Commit Hooks](#pre-commit-hooks)

## How to Contribute

### Reporting Bugs

If you find a bug in the project, please open an issue with detailed information. Include steps to reproduce the issue, your environment details, and any relevant logs or screenshots.

### Suggesting Features

We welcome feature suggestions! To suggest a new feature, please open an issue and describe your idea. Explain why the feature would be useful and how it should work.

### Submitting Code Changes

1. **Clone the Repository**:

    ```sh
    git clone https://github.com/ConsortiumGARR/tcs-garr
    cd tcs-garr
    ```

2. **Create a Branch**:

    ```sh
    git checkout -b feature/your-feature-name
    ```

3. **Make Your Changes**: Implement your changes in the new branch.
4. **Run Tests**: Ensure all tests pass before committing your changes.
5. **Commit Your Changes**:

    ```sh
    git add .
    git commit -m "Add feature: your feature name"
    ```

6. **Push to Your Branch**:

    ```sh
    git push origin feature/your-feature-name
    ```

7. **Open a Merge Request**: Go to the original repository and open a pull request. Provide a clear description of your changes and reference any related issues.

## Development Environment Setup

### Prerequisites

Ensure you have the following installed:

- Python 3.9+
- Git
- Poetry

### Installing Poetry

To install Poetry, use the following command:

```sh
curl -sSL https://install.python-poetry.org | python3 -
```

### Installing Dependencies

1. **Clone the repository**:

    ```sh
    git clone https://github.com/ConsortiumGARR/tcs-garr
    cd tcs-garr
    ```

2. **Create a virtual environment and install dependencies**:

    ```sh
    poetry install
    ```

3. **Activate Virtual Environment**:

    ```sh
    poetry shell
    ```

4. **Verify package installation**:

    ```sh
    tcs-garr --help
    ```

## Style Guide

Please follow the PEP 8 style guide for Python code. We use `ruff` for linting and formatting to maintain code quality. `Ruff` is automatically installed by Poetry when you install the project dependencies.

To run `ruff` for linting and formatting:

```sh
ruff check .  # Check for PEP 8 compliance and linting issues
ruff format .  # Automatically format code
```

Ensure your code is free of linting errors and properly formatted before committing your changes.

## Pre-Commit Hooks

This project uses `pre-commit` hooks to ensure code quality. The `poetry-pre-commit-plugin` is automatically install and configure Git Hooke when you run `poetry install` based on `.pre-commit-config.yaml` file.

Install and activate the hooks:

```sh
poetry self add poetry-pre-commit-plugin
poetry run pre-commit install
poetry run pre-commit install -t commit-msg -t pre-push
```

Pre-commit will check only the modified files by default. If you want to check all files (recommended after cloning the repository), run:

```sh
poetry run pre-commit run --all-files
```

These hooks will run automatically on every commit to check code formatting, linting, and other quality checks.
