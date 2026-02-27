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

## Operational Security

### Service Modes

**Private Mode (Default):**
- Most secure for development and personal use
- Only accessible from localhost (127.0.0.1)
- No authentication required (safe because it's local)
- Recommended for untrusted networks
- Cannot be accessed from other devices on your network

**Unprivate Mode:**
- Requires API key authentication
- Network-accessible - can be reached from other devices
- API keys transmitted in plaintext (use HTTPS in production!)
- Suitable for internal services within trusted networks
- Store API keys securely and rotate them regularly

**Public Mode:**
- **WARNING:** No authentication required
- Anyone with network access can use the service
- Only use if you understand the security implications
- Consider rate limiting and access controls
- Not recommended for internet-facing deployments

### Best Practices for Deployment

1. **Never commit API keys to version control**
   - Add API keys to `.gitignore` if stored in configuration files
   - Use environment variables for sensitive data
   - Rotate keys regularly if exposed

2. **Use HTTPS in production**
   - API keys sent over HTTP can be intercepted
   - Use a reverse proxy (nginx, Caddy) with TLS/SSL certificates
   - Consider Let's Encrypt for free certificates

3. **Input validation**
   - Service validates YouTube URLs and rejects playlists
   - Always verify download folder permissions
   - Be cautious with custom file names

4. **Rate limiting**
   - Consider adding rate limiting to prevent abuse
   - Monitor task queue sizes to prevent memory exhaustion
   - Set reasonable task retention limits

5. **Monitor and log**
   - Log authentication failures
   - Monitor for unusual download patterns
   - Set up alerts for high error rates

6. **Keep dependencies updated**
   - Regularly update Flask, pytube/pytubefix, and other dependencies
   - Run `pip list --outdated` to check for updates
   - Test updates in a development environment first
   - Subscribe to security advisories for Flask and dependencies

7. **Network security**
   - Use firewall rules to restrict access to the service port
   - Consider VPN for remote access to private mode
   - Don't expose the service to the internet unless necessary
   - If internet-facing, use unprivate mode with strong API keys

8. **Resource limits**
   - In-memory task storage has limits
   - Monitor memory usage, especially with many concurrent downloads
   - Consider implementing download queue limits
   - Set appropriate task retention periods

9. **File system security**
   - Ensure download directories have appropriate permissions
   - Be careful with world-writable directories
   - Consider disk space monitoring
   - Validate file paths to prevent directory traversal

### Known Limitations

1. **In-memory task storage:**
   - All task history lost on service restart
   - Not suitable for audit trails
   - Memory usage grows with task count

2. **Flask development server:**
   - Not designed for heavy production use
   - Use gunicorn, uWSGI, or similar for production
   - No built-in rate limiting or DDoS protection

3. **No built-in HTTPS:**
   - Use a reverse proxy for production
   - Don't expose Flask directly to the internet

4. **Thread-based concurrency:**
   - Limited by Python GIL for CPU-bound operations
   - Multiple simultaneous downloads can consume bandwidth
   - Consider connection pooling for many concurrent users

5. **External dependencies:**
   - Relies on pytube/pytubefix which may break with YouTube changes
   - No control over upstream services
   - Downloads may fail if YouTube changes their API

## Production Deployment Checklist

Before deploying to production:

- [ ] Use HTTPS (reverse proxy with TLS)
- [ ] Change default port if necessary
- [ ] Use strong API keys (if unprivate mode)
- [ ] Set up proper logging and log rotation
- [ ] Configure firewall rules
- [ ] Use production WSGI server (gunicorn, uWSGI)
- [ ] Set up monitoring and alerting
- [ ] Configure automatic service restarts (systemd, etc.)
- [ ] Set resource limits (memory, CPU, disk space)
- [ ] Regular security updates for OS and dependencies
- [ ] Backup configuration files
- [ ] Document your security setup
- [ ] Test with various video types and error conditions
- [ ] Consider download size limits
- [ ] Monitor disk space on download target

## Security Scanning & Maintenance

We:
- Review code changes for security implications
- Monitor dependencies for known vulnerabilities
- Keep the project actively maintained
- Encourage responsible disclosure

For questions or additional security concerns, please refer to the security reporting methods outlined above.
