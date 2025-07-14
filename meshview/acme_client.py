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

try:
    import certbot
    from certbot import main as certbot_main
    
    # Check if certbot binary is available
    import subprocess
    try:
        subprocess.run(['certbot', '--version'], capture_output=True, check=True)
        CERTBOT_AVAILABLE = True
        print("Certbot is available (both Python package and binary)")
    except (subprocess.CalledProcessError, FileNotFoundError):
        CERTBOT_AVAILABLE = False
        print("Certbot Python package available but binary not found")
except ImportError as e:
    print(f"Certbot not available: {e}")
    CERTBOT_AVAILABLE = False

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
        async def acme_challenge_handler(request):
            """Handle ACME challenge requests."""
            token = request.match_info.get('token', '')
            if not token:
                return web.Response(status=404)
                
            # Get the challenge response from storage
            challenge_response = await self._get_challenge_response(token)
            if challenge_response:
                return web.Response(text=challenge_response, content_type='text/plain')
            else:
                return web.Response(status=404)
        
        # Add the challenge route
        app.router.add_get(f'{self.acme_challenge_path}/{{token}}', acme_challenge_handler)
        logger.info(f"ACME challenge route added: {self.acme_challenge_path}/{{token}}")
        
    async def _get_challenge_response(self, token: str) -> Optional[str]:
        """Get the challenge response for a given token."""
        # This would typically be stored in memory or a simple file
        # For now, we'll use a simple file-based approach
        challenge_file = Path(f"acme_challenges/{token}")
        if challenge_file.exists():
            return challenge_file.read_text()
        return None
        
    async def _store_challenge_response(self, token: str, response: str):
        """Store the challenge response for a given token."""
        challenge_dir = Path("acme_challenges")
        challenge_dir.mkdir(exist_ok=True)
        challenge_file = challenge_dir / token
        challenge_file.write_text(response)
        
    async def _cleanup_challenge_response(self, token: str):
        """Clean up the challenge response after verification."""
        challenge_file = Path(f"acme_challenges/{token}")
        if challenge_file.exists():
            challenge_file.unlink()
            
    async def obtain_certificate(self) -> bool:
        """Obtain a new SSL certificate using certbot."""
        if not CERTBOT_AVAILABLE:
            logger.error("Certbot not available. Install with: pip install certbot")
            return False
            
        if not self.domain:
            logger.error("No domain configured for ACME certificate")
            return False
            
        return await self._obtain_certificate_with_certbot()
            
    async def _obtain_certificate_with_certbot(self) -> bool:
        """Obtain certificate using certbot."""
        try:
            logger.info(f"Attempting to obtain certificate for {self.domain} using certbot")
            
            # Prepare certbot arguments
            args = [
                'certonly',
                '--standalone',
                '--email', self.email,
                '--agree-tos',
                '--no-eff-email',
                '--domains', self.domain,
                '--cert-path', self.cert_path,
                '--key-path', self.key_path,
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
    if CERTBOT_AVAILABLE:
        return ACMEClient(config_section)
    else:
        logger.warning("Certbot not available. Install with: pip install certbot")
        return None

def check_certbot_availability():
    """Check if certbot is available and working."""
    if CERTBOT_AVAILABLE:
        print("✅ Certbot is available and ready to use")
        return True
    else:
        print("❌ Certbot is not available")
        return False 