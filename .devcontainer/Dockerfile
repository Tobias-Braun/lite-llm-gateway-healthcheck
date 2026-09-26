# The agent's toolbox: Ubuntu with general command-line tooling. The language runtimes (Node LTS,
# Python 3, Go, Java 21 with Maven and Gradle) come from the features in devcontainer.json. Remove
# what the project doesn't need to speed up the first build, and add project-specific tools here.
FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential make gh jq ripgrep fd-find tree unzip zip xz-utils file less \
      shellcheck sqlite3 dnsutils iputils-ping netcat-openbsd \
 && rm -rf /var/lib/apt/lists/*

# Claude Code is installed for the non-root user: bypassPermissions refuses to run as root.
USER vscode
RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH="/home/vscode/.local/bin:${PATH}"
