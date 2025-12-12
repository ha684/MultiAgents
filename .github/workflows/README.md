# CI/CD Workflows

## Environment Configuration

This directory contains GitHub Actions workflows for automated testing, building, and deployment.

### Environment Variables

Instead of hard-coding environment variables in the workflow files, we use a centralized configuration file:

- **`config.env.ci`** - Contains all environment variables needed for CI/CD testing

This file is automatically copied to `.env` during the CI/CD pipeline setup phase.

### Why this approach?

✅ **Clean & Maintainable**: All configurations in one place  
✅ **Easy to Update**: Change values without touching workflow YAML  
✅ **Consistent**: Same environment across all test jobs  
✅ **Version Controlled**: Track configuration changes over time  

### Local Testing

To run tests with the same configuration as CI/CD:

```bash
# Copy CI config to your local .env
cp config.env.ci .env

# Run tests
make test
```

### Production/Sensitive Values

For production or sensitive values, use **GitHub Secrets** instead:

1. Go to Repository → Settings → Secrets and variables → Actions
2. Add secrets (e.g., `PRODUCTION_API_KEY`)
3. Reference in workflow: `${{ secrets.PRODUCTION_API_KEY }}`

### Workflow Structure

- **test**: Runs unit, integration, and E2E tests
- **code-quality**: Runs linting and formatting checks
- **security-scan**: Runs security vulnerability scans
- **build-docker**: Builds and pushes Docker images (main branch only)
- **deploy**: Deployment placeholder (main branch only)
- **notify**: Sends notifications about workflow status

