# Security Policy

## Reporting Security Vulnerabilities

We take security seriously and appreciate your efforts to responsibly disclose vulnerabilities to us.

### How to Report

**Please do not open a public GitHub issue for security vulnerabilities.** Instead, use one of the following secure reporting methods:

1. **GitHub Security Advisory**: Use GitHub's private vulnerability reporting feature
   - Navigate to the **Security** tab of this repository
   - Click **"Report a vulnerability"** to open a private report

2. **Private Vulnerability Reporting**: If enabled, GitHub will notify maintainers privately

### What to Include

When reporting a security vulnerability, please provide:

- A clear description of the vulnerability
- Steps to reproduce the issue (if applicable)
- Potential impact or severity assessment
- Any proof-of-concept code (if available)
- Version(s) of the YouTube Downloader affected

## Supported Versions

Currently, the project version policy is:

- **Actively Maintained**: Only the latest version (main branch)
- **Security Updates**: When new releases are published, only the latest version receives security patches
- **No Release Cycle**: Until an official release is made, treat the main branch as the development version

## Response & Disclosure Timeline

- **Acknowledgment**: We will acknowledge receipt of your report, but do not guarantee a specific response timeframe
- **Fix & Release**: We will work on fixing confirmed vulnerabilities
- **Disclosure**: Fixed vulnerabilities will be disclosed publicly after a **4-week coordinated disclosure window** from the time a fix is available
  - This allows users time to update before the vulnerability is publicly disclosed
  - The reporter is welcome to request accelerated disclosure if the vulnerability becomes publicly known

## Known Security Considerations

This application interacts with external networks and file systems. Users should be aware of the following potential security considerations:

### Network Requests
- The application communicates with YouTube and related services to download media
- Ensure you are using the application on a secure network and trusted system
- Be cautious about network proxies or monitoring tools that may intercept requests

### File Handling
- Downloaded files are stored on your local file system
- Ensure you have appropriate permissions for the storage location
- Downloaded files may execute if they are executable types; only download from trusted sources
- Be aware of your local storage's security and encryption practices

## Security Best Practices for Users

- **Keep Updated**: Always use the latest version of the application
- **Terms of Service**: Respect the terms of service of content providers and platforms
- **Legal Compliance**: Ensure your use of this tool complies with applicable laws and regulations
- **Trusted Sources**: Only download content from authorized or trusted sources

## Security Scanning & Maintenance

We:
- Review code changes for security implications
- Monitor dependencies for known vulnerabilities
- Keep the project actively maintained

For questions or additional security concerns, please refer to the security reporting methods outlined above.
