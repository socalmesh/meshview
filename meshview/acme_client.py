import asyncio
import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import ssl
import tempfile
import shutil
from cryptography import x509

# Import subprocess for certbot checks
import subprocess

# Check if certbot binary is available (don't import Python module yet)
try:
    subprocess.run(['certbot', '--version'], capture_output=True, check=True)
    print("Certbot binary is available")
    CERTBOT_BINARY_AVAILABLE = True
except (subprocess.CalledProcessError, FileNotFoundError):
    print("Warning: Certbot binary not found")
    CERTBOT_BINARY_AVAILABLE = False

from aiohttp import web
from meshview import config

logger = logging.getLogger(__name__)

class ACMEClient:
    """ACME client for automatic SSL certificate management with Let's Encrypt."""
    
    def __init__(self, config_section: Dict[str, Any]):
        self.config = config_section
        self.domain = config_section.get('domain', '').replace('https://', '').replace('http://', '')
        self.email = config_section.get('email', '')
        self.acme_challenge_path = config_section.get('acme_challenge', '/.well-known/acme-challenge')
        self.cert_path = config_section.get('cert_path', '')
        self.key_path = config_section.get('key_path', '')
        self.renewal_threshold_days = config_section.get('renewal_threshold_days', 30)
        
        # Always use production ACME server
        self.acme_server = 'https://acme-v02.api.letsencrypt.org/directory'
        
        # Ensure directories exist
        self._ensure_directories()
        
    def _ensure_directories(self):
        """Ensure necessary directories exist."""
        if self.cert_path:
            Path(self.cert_path).parent.mkdir(parents=True, exist_ok=True)
        if self.key_path:
            Path(self.key_path).parent.mkdir(parents=True, exist_ok=True)
            
    async def setup_challenge_routes(self, app: web.Application):
        """Setup ACME challenge routes for HTTP-01 verification."""
        # Ensure webroot directory exists
        webroot_dir = Path('/tmp/acme-webroot')
        webroot_dir.mkdir(parents=True, exist_ok=True)
        
        # Create .well-known/acme-challenge directory
        challenge_dir = webroot_dir / '.well-known' / 'acme-challenge'
        challenge_dir.mkdir(parents=True, exist_ok=True)
        
        async def acme_challenge_handler(request):
            """Handle ACME challenge requests."""
            token = request.match_info.get('token', '')
            logger.info(f"ACME challenge request for token: {token}")
            
            if not token:
                logger.warning("ACME challenge request with no token")
                return web.Response(status=404)
                
            # Look for challenge file in webroot
            challenge_file = challenge_dir / token
            logger.info(f"Looking for challenge file: {challenge_file}")
            
            if challenge_file.exists():
                try:
                    challenge_response = challenge_file.read_text()
                    logger.info(f"Serving ACME challenge response for token: {token}")
                    return web.Response(text=challenge_response, content_type='text/plain')
                except Exception as e:
                    logger.error(f"Error reading challenge file: {e}")
                    return web.Response(status=404)
            else:
                logger.warning(f"ACME challenge file not found: {challenge_file}")
                # List files in challenge directory for debugging
                try:
                    files = list(challenge_dir.iterdir())
                    logger.info(f"Files in challenge directory: {files}")
                except Exception as e:
                    logger.error(f"Error listing challenge directory: {e}")
                return web.Response(status=404)
        
        # Add the challenge route
        app.router.add_get(f'{self.acme_challenge_path}/{{token}}', acme_challenge_handler)
        logger.info(f"ACME challenge route added: {self.acme_challenge_path}/{{token}}")
        logger.info(f"ACME webroot directory: {webroot_dir}")
        
        # Add a test route to verify the endpoint is accessible
        async def acme_test_handler(request):
            return web.Response(text="ACME challenge endpoint is working", content_type='text/plain')
        
        # Add a debug route to list challenge files
        async def acme_debug_handler(request):
            try:
                files = list(challenge_dir.iterdir()) if challenge_dir.exists() else []
                file_list = [f.name for f in files]
                return web.Response(text=f"Challenge files: {file_list}", content_type='text/plain')
            except Exception as e:
                return web.Response(text=f"Error: {e}", content_type='text/plain')
        
        app.router.add_get(f'{self.acme_challenge_path}/test', acme_test_handler)
        app.router.add_get(f'{self.acme_challenge_path}/debug', acme_debug_handler)
        logger.info(f"ACME test route added: {self.acme_challenge_path}/test")
        logger.info(f"ACME debug route added: {self.acme_challenge_path}/debug")

            
    async def obtain_certificate(self) -> bool:
        """Obtain a new SSL certificate using certbot."""
        if not self.domain:
            logger.error("No domain configured for ACME certificate")
            return False
            
        if not self.email:
            logger.error("No email configured for ACME certificate registration")
            return False
            
        # Log domain info for debugging
        logger.info(f"Attempting to obtain certificate for domain: {self.domain}")
        logger.info(f"Using email: {self.email}")
        logger.info(f"Domain should be accessible at: http://{self.domain}/.well-known/acme-challenge/")
        logger.info(f"Note: Let's Encrypt will try both HTTP and HTTPS for the challenge")
        
        return await self._obtain_certificate_with_certbot()
            
    async def _obtain_certificate_with_certbot(self) -> bool:
        """Obtain certificate using certbot."""
        try:
            logger.info(f"Attempting to obtain certificate for {self.domain} using certbot")
            
            # Ensure webroot directory exists and log it
            webroot_dir = Path('/tmp/acme-webroot')
            webroot_dir.mkdir(parents=True, exist_ok=True)
            challenge_dir = webroot_dir / '.well-known' / 'acme-challenge'
            challenge_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"ACME webroot directory: {webroot_dir}")
            logger.info(f"ACME challenge directory: {challenge_dir}")
            
            # Try to import certbot only when needed
            try:
                from certbot import main as certbot_main
            except (ImportError, AttributeError) as e:
                logger.error(f"Failed to import certbot: {e}")
                # Fall back to using certbot binary directly
                return await self._obtain_certificate_with_certbot_binary()
            
            # Prepare certbot arguments for webroot mode
            args = [
                'certonly',
                '--webroot',
                '--webroot-path', '/tmp/acme-webroot',
                '--preferred-challenges', 'http',
                '--email', self.email,
                '--agree-tos',
                '--no-eff-email',
                '--domains', self.domain,
                '--non-interactive',
                '--quiet'
            ]
            
            # Run certbot
            result = certbot_main.main(args)
            
            if result == 0:
                logger.info(f"Certificate obtained successfully for {self.domain}")
                return True
            else:
                logger.error("Certbot failed to obtain certificate")
                return False
                
        except Exception as e:
            logger.error(f"Failed to obtain certificate with certbot: {e}")
            return False
            
    async def _obtain_certificate_with_certbot_binary(self) -> bool:
        """Obtain certificate using certbot binary directly."""
        try:
            logger.info(f"Attempting to obtain certificate for {self.domain} using certbot binary")
            
            if not CERTBOT_BINARY_AVAILABLE:
                logger.error("Certbot binary not available")
                return False
            
            # Prepare certbot command for webroot mode
            cmd = [
                'certbot',
                'certonly',
                '--webroot',
                '--webroot-path', '/tmp/acme-webroot',
                '--preferred-challenges', 'http',
                '--email', self.email,
                '--agree-tos',
                '--no-eff-email',
                '--domains', self.domain,
                '--non-interactive',
                '--quiet'
            ]
            
            # Run certbot binary
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Certificate obtained successfully for {self.domain}")
                return True
            else:
                logger.error(f"Certbot binary failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to obtain certificate with certbot binary: {e}")
            return False
            
    async def renew_certificate_if_needed(self) -> bool:
        """Check if certificate needs renewal and renew if necessary."""
        # In containerized environments, always obtain a new certificate on startup
        # since containers are ephemeral and may run long enough for certs to expire
        logger.info("Containerized environment detected - obtaining new certificate on startup")
        return await self.obtain_certificate()
            
    async def setup_auto_renewal(self):
        """Setup automatic certificate renewal for containerized environments."""
        async def renewal_task():
            while True:
                try:
                    # In containerized environments, check certificate validity
                    # and renew if needed, but don't always obtain new cert
                    if await self._should_renew_certificate():
                        logger.info("Certificate needs renewal, obtaining new one")
                        await self.obtain_certificate()
                    else:
                        logger.info("Certificate is still valid")
                    
                    # Check every 6 hours for containerized environments
                    await asyncio.sleep(6 * 60 * 60)
                except Exception as e:
                    logger.error(f"Certificate renewal failed: {e}")
                    await asyncio.sleep(60 * 60)  # Wait 1 hour on error
                    
        asyncio.create_task(renewal_task())
        logger.info("Automatic certificate renewal enabled for containerized environment")
        
    async def _should_renew_certificate(self) -> bool:
        """Check if certificate should be renewed in containerized environment."""
        if not self.cert_path or not os.path.exists(self.cert_path):
            return True
            
        try:
            # Load certificate
            with open(self.cert_path, 'rb') as f:
                cert_data = f.read()
                
            cert = x509.load_pem_x509_certificate(cert_data)
            
            # Check if renewal is needed
            days_until_expiry = (cert.not_valid_after - datetime.now()).days
            
            # In containerized environments, be more aggressive about renewal
            # since containers may run for extended periods
            if days_until_expiry <= self.renewal_threshold_days:
                logger.info(f"Certificate expires in {days_until_expiry} days, will renew")
                return True
            else:
                logger.info(f"Certificate is valid for {days_until_expiry} more days")
                return False
                
        except Exception as e:
            logger.error(f"Error checking certificate: {e}")
            return True  # Renew on error to be safe


def create_acme_client(config_section: Dict[str, Any]) -> Optional[ACMEClient]:
    """Create a certbot-based ACME client."""
    return ACMEClient(config_section)

def check_certbot_availability():
    """Check if certbot is available and working."""
    try:
        subprocess.run(['certbot', '--version'], capture_output=True, check=True)
        print("✅ Certbot is available and ready to use")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Certbot is not available")
        return False 