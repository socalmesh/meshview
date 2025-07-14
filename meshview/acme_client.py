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
    from certbot.plugins.manual import ManualAuthenticator
    from certbot.plugins.standalone import StandaloneAuthenticator
    from certbot.plugins.webroot import WebrootAuthenticator
    CERTBOT_AVAILABLE = True
except ImportError as e:
    print(f"Certbot not available: {e}")
    CERTBOT_AVAILABLE = False

try:
    import acme
    from acme import client as acme_client
    from acme import challenges
    from acme import messages
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    ACME_AVAILABLE = True
except ImportError as e:
    print(f"ACME library not available: {e}")
    ACME_AVAILABLE = False

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
            
    def _generate_private_key(self) -> bytes:
        """Generate a new private key."""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        return private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
    def _generate_csr(self, private_key_bytes: bytes, domain: str) -> bytes:
        """Generate a Certificate Signing Request."""
        private_key = serialization.load_pem_private_key(private_key_bytes, password=None)
        
        # Create CSR
        csr = x509.CertificateSigningRequestBuilder().subject_name(
            x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, domain),
            ])
        ).add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName(domain),
            ]),
            critical=False,
        ).sign(private_key, hashes.SHA256())
        
        return csr.public_bytes(serialization.Encoding.PEM)
        
    async def obtain_certificate(self) -> bool:
        """Obtain a new SSL certificate using ACME with retry logic for containerized environments."""
        if not ACME_AVAILABLE:
            logger.error("ACME library not available. Install with: pip install acme cryptography")
            return False
            
        if not self.domain:
            logger.error("No domain configured for ACME certificate")
            return False
            
        # Retry logic for containerized environments
        max_retries = 3
        retry_delay = 30  # seconds
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempting to obtain certificate (attempt {attempt + 1}/{max_retries})")
                
                # Generate private key
                private_key_bytes = self._generate_private_key()
                
                # Generate CSR
                csr_bytes = self._generate_csr(private_key_bytes, self.domain)
                
                # Create ACME client
                acme_client_instance = acme_client.ClientV2(
                    directory_url=self.acme_server,
                    key=acme_client.ClientV2._load_key(private_key_bytes)
                )
                
                # Register account
                if self.email:
                    acme_client_instance.new_account(
                        messages.NewRegistration.from_data(email=self.email)
                    )
                
                # Create order
                order = acme_client_instance.new_order(csr_bytes)
                
                # Get HTTP-01 challenge
                authz = order.authorizations[0]
                http_challenge = authz.body.challenges[0]  # HTTP-01 challenge
                
                # Store challenge response
                await self._store_challenge_response(
                    http_challenge.path, 
                    http_challenge.response_and_validation(acme_client_instance.net.key).challenge.path
                )
                
                # Wait for challenge to be validated (longer wait for containers)
                logger.info(f"Waiting for ACME challenge validation for {self.domain}")
                await asyncio.sleep(10)  # Longer wait for containerized environments
                
                # Complete challenge
                acme_client_instance.answer_challenge(http_challenge, http_challenge.response(acme_client_instance.net.key))
                
                # Wait for validation with timeout
                validation_timeout = 60  # seconds
                start_time = asyncio.get_event_loop().time()
                
                while authz.body.status != messages.STATUS_VALID:
                    if asyncio.get_event_loop().time() - start_time > validation_timeout:
                        raise Exception("Challenge validation timeout")
                    await asyncio.sleep(2)
                    authz = acme_client_instance.poll(authz)
                    
                # Finalize order
                order = acme_client_instance.finalize_order(order, csr_bytes)
                
                # Download certificate
                cert_chain = acme_client_instance.download_certificate(order)
                
                # Save certificate and key
                if self.cert_path:
                    with open(self.cert_path, 'wb') as f:
                        f.write(cert_chain)
                        
                if self.key_path:
                    with open(self.key_path, 'wb') as f:
                        f.write(private_key_bytes)
                        
                # Cleanup challenge
                await self._cleanup_challenge_response(http_challenge.path)
                
                logger.info(f"Certificate obtained successfully for {self.domain}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to obtain certificate (attempt {attempt + 1}/{max_retries}): {e}")
                
                # Cleanup on failure
                await self._cleanup_challenge_response(http_challenge.path if 'http_challenge' in locals() else '')
                
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error("All attempts to obtain certificate failed")
                    return False
                    
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


class CertbotACMEClient:
    """ACME client using certbot for certificate management."""
    
    def __init__(self, config_section: Dict[str, Any]):
        self.config = config_section
        self.domain = config_section.get('domain', '').replace('https://', '').replace('http://', '')
        self.email = config_section.get('email', '')
        self.cert_path = config_section.get('cert_path', '')
        self.key_path = config_section.get('key_path', '')

        
    async def obtain_certificate(self) -> bool:
        """Obtain certificate using certbot."""
        if not CERTBOT_AVAILABLE:
            logger.error("Certbot not available. Install with: pip install certbot")
            return False
            
        if not self.domain:
            logger.error("No domain configured for ACME certificate")
            return False
            
        try:
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


def create_acme_client(config_section: Dict[str, Any]) -> Optional[ACMEClient]:
    """Create an appropriate ACME client based on available libraries."""
    if ACME_AVAILABLE:
        return ACMEClient(config_section)
    elif CERTBOT_AVAILABLE:
        return CertbotACMEClient(config_section)
    else:
        logger.warning("No ACME libraries available. Install with: pip install acme cryptography certbot")
        return None 