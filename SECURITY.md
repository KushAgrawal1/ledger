# Security Policy

## Reporting a vulnerability

Please do not open a public issue for security problems.
Report them privately through GitHub's "Report a vulnerability" option
on the Security tab of this repository.

## Handling of secrets

Secrets such as database credentials and the JWT signing key are loaded
from environment variables (see `.env.example`). Never commit a real `.env` file.
