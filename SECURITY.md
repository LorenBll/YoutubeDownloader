# Security Policy

## Supported Versions

This service is provided as-is. Security updates will be provided for this project on a best-effort basis.

| Version | Supported |
| ------- | --------- |
| Latest  | Yes       |
| Older   | No        |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it by:

1. **DO NOT** create a public GitHub issue
2. Email the maintainers (or open a private security advisory)
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if available)

We will acknowledge receipt within 48 hours and provide a timeline for a fix.

## Security Considerations

### Service Modes

**Private Mode (Default):**
- Most secure for development
- Only accessible from localhost
- No authentication required (safe because it's local)
- Recommended for untrusted networks

**Unprivate Mode:**
- Requires API key authentication
- Network-accessible
- API keys transmitted in plaintext (use HTTPS in production!)
- Suitable for internal services

**Public Mode:**
- **WARNING:** No authentication
- Anyone with network access can use the service
- Only use if your service is designed for public access
- Consider rate limiting and input validation

### Best Practices

1. **Never commit API keys to version control**
   - Add `resources/configuration.json` to `.gitignore` if it contains keys
   - Use environment variables for sensitive data
   - Rotate keys regularly

2. **Use HTTPS in production**
   - API keys sent in plain text over HTTP can be intercepted
   - Use a reverse proxy (nginx, Caddy) with TLS/SSL certificates
   - Consider Let's Encrypt for free certificates

3. **Input validation**
   - Always validate user input
   - Sanitize file paths to prevent directory traversal
   - Set maximum request size limits

4. **Rate limiting**
   - Consider adding rate limiting to prevent abuse
   - Use tools like Flask-Limiter
   - Monitor task queue sizes

5. **Monitor and log**
   - Log authentication failures
   - Monitor for unusual patterns
   - Set up alerts for high error rates

6. **Keep dependencies updated**
   - Regularly update Flask and other dependencies
   - Run `pip list --outdated` to check for updates
   - Test updates in a development environment first

7. **Network security**
   - Use firewall rules to restrict access
   - Consider VPN for internal services
   - Don't expose to internet unless necessary

8. **Resource limits**
   - In-memory storage has limits
   - Consider persistent storage for production
   - Monitor memory usage
   - Set task retention limits appropriately

## Known Limitations

1. **In-memory task storage:**
   - All tasks lost on restart
   - Not suitable for critical data
   - Memory usage grows with task count

2. **Flask development server:**
   - Not designed for production
   - Use gunicorn, uWSGI, or similar for production
   - No built-in rate limiting

3. **No built-in HTTPS:**
   - Use a reverse proxy for production
   - Don't expose Flask directly to internet

4. **Thread-based concurrency:**
   - Limited by Python GIL
   - Consider async workers for I/O-bound tasks
   - Use multiple processes for CPU-bound tasks

## Production Deployment Checklist

- [ ] Use HTTPS (reverse proxy)
- [ ] Change default port
- [ ] Use strong API keys (if unprivate mode)
- [ ] Set up proper logging
- [ ] Configure firewall rules
- [ ] Use production WSGI server (gunicorn, uWSGI)
- [ ] Set up monitoring and alerting
- [ ] Configure automatic restarts
- [ ] Set resource limits (memory, CPU)
- [ ] Regular security updates
- [ ] Backup configuration
- [ ] Document your security setup

## Contact

For security concerns, please contact the repository maintainers through the appropriate channels.
