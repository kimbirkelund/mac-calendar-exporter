#!/usr/bin/env python3
"""
SFTP Upload Module.

This module handles uploading files to an SFTP server using paramiko.
"""

import logging
import os
from typing import Dict, Optional, Tuple, Union

import paramiko

logger = logging.getLogger(__name__)


class SFTPUploader:
    """Upload files to an SFTP server."""

    def __init__(
        self,
        hostname: str,
        port: int = 22,
        username: str = None,
        password: str = None,
        key_file: str = None,
        key_passphrase: str = None,
        timeout: int = 30,
    ):
        """
        Initialize the SFTP uploader.
        
        Args:
            hostname: SFTP server hostname
            port: SFTP server port
            username: Username for authentication
            password: Password for password authentication
            key_file: Path to SSH private key for key-based authentication
            key_passphrase: Passphrase for encrypted SSH private key (if None, tries Keychain)
            timeout: Connection timeout in seconds
        """
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.key_file = key_file
        self.key_passphrase = key_passphrase
        self.timeout = timeout
        self._transport = None
        self._sftp = None

    def _get_key_passphrase_from_keychain(self) -> Optional[str]:
        """
        Get SSH key passphrase from macOS Keychain.
        
        Returns:
            Optional[str]: Passphrase from Keychain or None if not found
        """
        if not self.key_file:
            return None
            
        key_path = os.path.expanduser(self.key_file)
        
        try:
            import subprocess
            
            # Try to get passphrase using the standard macOS SSH Keychain integration
            # macOS stores SSH key passphrases with the key path as the account
            result = subprocess.run(
                [
                    "security", "find-generic-password",
                    "-a", key_path,
                    "-s", "SSH",
                    "-w"
                ],
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0 and result.stdout.strip():
                logger.debug("Retrieved SSH key passphrase from Keychain (SSH service)")
                return result.stdout.strip()
            
            # Try with "OpenSSH" as service name (some versions use this)
            result = subprocess.run(
                [
                    "security", "find-generic-password",
                    "-a", key_path,
                    "-s", "OpenSSH",
                    "-w"
                ],
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0 and result.stdout.strip():
                logger.debug("Retrieved SSH key passphrase from Keychain (OpenSSH service)")
                return result.stdout.strip()
                
        except Exception as e:
            logger.debug(f"Could not get passphrase from Keychain: {e}")
        
        # Fallback: try to use ssh-add with the key from the agent
        # If the key is already loaded in ssh-agent, paramiko can use it
        try:
            import subprocess
            # Check if key is in agent
            result = subprocess.run(
                ["ssh-add", "-l"],
                capture_output=True,
                text=True,
                check=False
            )
            if key_path in result.stdout or os.path.basename(key_path) in result.stdout:
                logger.debug("SSH key is loaded in ssh-agent, will try agent auth")
                # Return empty string to signal we should try without passphrase
                # (agent will handle it)
                return ""
        except Exception:
            pass
        
        return None

    def connect(self) -> bool:
        """
        Connect to the SFTP server.
        
        Returns:
            bool: True if connection was successful, False otherwise
        """
        try:
            transport = paramiko.Transport((self.hostname, self.port))
            transport.connect()
            
            authenticated = False
            
            # Try ssh-agent first (works with macOS Keychain integration)
            try:
                agent = paramiko.Agent()
                agent_keys = agent.get_keys()
                if agent_keys:
                    for key in agent_keys:
                        try:
                            transport.auth_publickey(self.username, key)
                            logger.info("Authenticated via ssh-agent")
                            authenticated = True
                            break
                        except paramiko.ssh_exception.AuthenticationException:
                            continue
            except Exception as e:
                logger.debug(f"ssh-agent auth not available: {e}")
            
            # Try key file if agent didn't work
            if not authenticated and self.key_file and os.path.isfile(self.key_file):
                passphrase = self.key_passphrase
                if passphrase is None:
                    passphrase = self._get_key_passphrase_from_keychain()
                
                try:
                    private_key = None
                    key_types = [
                        (paramiko.RSAKey, "RSA"),
                        (paramiko.Ed25519Key, "Ed25519"),
                        (paramiko.ECDSAKey, "ECDSA"),
                        (paramiko.DSSKey, "DSS"),
                    ]
                    
                    for key_class, key_name in key_types:
                        try:
                            private_key = key_class.from_private_key_file(
                                self.key_file, password=passphrase if passphrase else None
                            )
                            logger.debug(f"Loaded {key_name} key from {self.key_file}")
                            break
                        except paramiko.ssh_exception.SSHException:
                            continue
                    
                    if private_key:
                        transport.auth_publickey(self.username, private_key)
                        logger.info("Key-based authentication successful")
                        authenticated = True
                except Exception as e:
                    logger.error(f"Key-based authentication failed: {e}")
            
            # Fall back to password
            if not authenticated and self.password:
                transport.auth_password(self.username, self.password)
                logger.info("Password authentication successful")
                authenticated = True
            
            if not authenticated:
                raise ValueError("No authentication method succeeded")

            self._transport = transport
            self._sftp = paramiko.SFTPClient.from_transport(transport)
            
            logger.info(f"Successfully connected to SFTP server {self.hostname}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to SFTP server {self.hostname}: {e}")
            return False

    def disconnect(self) -> None:
        """Close the SFTP connection."""
        if self._sftp:
            self._sftp.close()
            self._sftp = None
            
        if self._transport:
            self._transport.close()
            self._transport = None
            
        logger.info("Disconnected from SFTP server")

    def upload_file(
        self, 
        local_file: str, 
        remote_path: str, 
        create_dirs: bool = True
    ) -> bool:
        """
        Upload a file to the SFTP server.
        
        Args:
            local_file: Path to the local file to upload
            remote_path: Path on the SFTP server to upload the file to
            create_dirs: If True, create remote directories if they don't exist
            
        Returns:
            bool: True if upload was successful, False otherwise
        """
        if not self._sftp:
            if not self.connect():
                return False
                
        try:
            # Check if local file exists
            if not os.path.isfile(local_file):
                logger.error(f"Local file does not exist: {local_file}")
                return False

            # Create remote directories if needed
            if create_dirs:
                remote_dir = os.path.dirname(remote_path)
                if remote_dir:
                    try:
                        self._create_remote_directory(remote_dir)
                    except Exception as e:
                        logger.error(f"Failed to create remote directory {remote_dir}: {e}")
                        return False
            
            # Upload the file
            self._sftp.put(local_file, remote_path)
            logger.info(f"Successfully uploaded {local_file} to {remote_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to upload file {local_file} to {remote_path}: {e}")
            return False
        finally:
            # Keep the connection open for potential future uploads
            pass
            
    def _create_remote_directory(self, directory: str) -> None:
        """
        Create a directory on the SFTP server, including any parent directories.
        
        Args:
            directory: Path to create on the SFTP server
        """
        if not directory:
            return
            
        # Strip trailing slash
        directory = directory.rstrip('/')
        
        try:
            self._sftp.stat(directory)
            # Directory exists
            return
        except IOError:
            # Directory doesn't exist, create parent directory first
            parent = os.path.dirname(directory)
            if parent and parent != directory:
                self._create_remote_directory(parent)
                
            # Create the directory
            self._sftp.mkdir(directory)
            logger.debug(f"Created remote directory: {directory}")


if __name__ == "__main__":
    # Simple test function when run directly
    import tempfile
    
    logging.basicConfig(level=logging.INFO)
    
    # Create a test file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as tmp:
        tmp.write(b"This is a test file for SFTP upload")
    
    # Use environment variables for connection details (for security)
    hostname = os.environ.get('SFTP_HOST', 'example.com')
    username = os.environ.get('SFTP_USER', 'user')
    password = os.environ.get('SFTP_PASS', 'password')
    
    # Initialize uploader
    uploader = SFTPUploader(hostname, username=username, password=password)
    
    # Upload the test file
    remote_path = '/upload/test.txt'
    result = uploader.upload_file(tmp.name, remote_path)
    
    # Cleanup
    uploader.disconnect()
    os.unlink(tmp.name)
    
    print(f"Upload result: {'Success' if result else 'Failed'}")
